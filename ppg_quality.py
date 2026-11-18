"""Full-rate optical recording and optional, asynchronous research inference.

Predictions annotate a waveform. They never change measured vitals or SOS.
"""
import collections
import json
import math
from pathlib import Path
import queue
import threading
import time

RATE = 25
WINDOW_SAMPLES = 250
FEATURE_VERSION = 1
FEATURE_NAMES = (
    'relative_amplitude', 'skew', 'kurtosis', 'derivative_rms',
    'flat_fraction', 'clipped_fraction', 'periodicity',
    'pulse_band_fraction', 'spectral_concentration', 'dominant_hz', 'drift',
)


def parse_raw_packet(line):
    if not line.startswith('[PPG] ') or len(line) > 8192:
        return None
    try:
        p = json.loads(line[6:])
        if not isinstance(p, dict) or p.get('schema_version') != 1:
            return None
        if not isinstance(p.get('device_id'), str) or not 1 <= len(p['device_id']) <= 128:
            return None
        for key in ('boot_id', 'seq_start'):
            if type(p.get(key)) is not int or not 0 <= p[key] <= 0xffffffff:
                return None
        if p.get('sample_rate_hz') != RATE:
            return None
        samples = p.get('samples')
        if not isinstance(samples, list) or not 1 <= len(samples) <= 50:
            return None
        for row in samples:
            if not isinstance(row, list) or len(row) != 3:
                return None
            if any(type(v) is not int for v in row):
                return None
            if not 0 <= row[0] <= 0xffffffff or any(not 0 <= v <= 262143 for v in row[1:]):
                return None
        return p
    except (ValueError, TypeError, RecursionError, OverflowError):
        return None


def extract_features(red, sample_rate=RATE):
    """Shared training/inference implementation; single red optical channel."""
    import numpy as np

    raw = np.asarray(red, dtype=np.float64)
    if raw.ndim != 1 or len(raw) < 100 or not np.isfinite(raw).all():
        raise ValueError('A finite optical waveform of at least four seconds is required.')
    # BUT PPG stores inverted camera brightness as negative values. Use a
    # consistent DC polarity across that benchmark and positive ADC counts.
    if np.median(raw) < 0:
        raw = -raw
    mean = float(raw.mean())
    centered = raw - mean
    std = float(centered.std())
    scaled = centered / max(std, 1e-12)
    # Remove linear drift for periodicity and frequency features, retaining it
    # as a separate feature rather than hiding it from the classifier.
    t = np.linspace(-1, 1, len(raw))
    slope = float(np.dot(t, centered) / np.dot(t, t))
    ac = centered - slope * t
    power = np.abs(np.fft.rfft(ac * np.hanning(len(ac)))) ** 2
    frequencies = np.fft.rfftfreq(len(ac), 1.0 / sample_rate)
    band = (frequencies >= 0.5) & (frequencies <= 4)
    total = float(power[frequencies >= 0.1].sum())
    band_power = float(power[band].sum())
    dominant = float(frequencies[band][np.argmax(power[band])]) if band_power else 0.0
    correlations = np.correlate(ac, ac, mode='full')[len(ac) - 1:]
    lags = np.arange(max(1, int(sample_rate / 4)), min(len(ac), int(sample_rate * 2)) + 1)
    periodicity = float(max(0, np.max(correlations[lags]) / max(correlations[0], 1e-12)))
    values = [
        float(np.ptp(raw)) / max(abs(mean), 1e-9),
        float(np.mean(scaled ** 3)), float(np.mean(scaled ** 4)),
        float(np.sqrt(np.mean(np.diff(scaled) ** 2))),
        float(np.mean(np.diff(raw) == 0)),
        float(np.mean((raw <= 0) | (raw >= 262143))), periodicity,
        band_power / max(total, 1e-12),
        float(power[band].max()) / max(band_power, 1e-12), dominant,
        abs(slope) / max(std, 1e-12),
    ]
    return np.nan_to_num(values, nan=0.0, posinf=1e6, neginf=-1e6)


class WindowCollector:
    def __init__(self):
        self.samples = collections.deque(maxlen=WINDOW_SAMPLES)
        self.identity = None
        self.expected_seq = None
        self.last_timestamp = None
        self.gaps = 0

    def reset(self):
        self.samples.clear()
        self.expected_seq = None
        self.last_timestamp = None

    def append(self, packet):
        identity = (packet['device_id'], packet['boot_id'])
        if identity != self.identity or packet['seq_start'] != self.expected_seq:
            if self.expected_seq is not None:
                self.gaps += 1
            self.reset()
            self.identity = identity
        for timestamp, red, ir in packet['samples']:
            if self.last_timestamp is not None:
                delta = (timestamp - self.last_timestamp) & 0xffffffff
                if not 20 <= delta <= 60:
                    self.samples.clear()
                    self.gaps += 1
            self.samples.append((timestamp, red, ir))
            self.last_timestamp = timestamp
        self.expected_seq = (packet['seq_start'] + len(packet['samples'])) & 0xffffffff
        return len(self.samples) == WINDOW_SAMPLES


class OpticalQualityService:
    def __init__(self, model_path=None, recording_path=None, participant=None, session=None):
        if recording_path and (not participant or not session):
            raise ValueError('Recording requires --participant and --session aliases.')
        self.model_path = Path(model_path) if model_path else None
        self.model = None
        self.model_error = None
        self.recording_path = Path(recording_path) if recording_path else None
        self.participant = participant
        self.session = session
        self.collector = WindowCollector()
        self.lock = threading.Lock()
        self.queue = queue.Queue(maxsize=16)
        self.dropped_batches = 0
        self.recording_error = None
        self.recording_file = None
        self.result = dict(status='waiting', message='Waiting for continuous optical samples.')
        self.last_received = None
        self.closed = False
        if self.model_path and self.model_path.exists():
            try:
                import joblib
                self.model = joblib.load(self.model_path)
                if (self.model['feature_version'] != FEATURE_VERSION
                        or self.model['feature_names'] != list(FEATURE_NAMES)
                        or self.model['sample_rate_hz'] != RATE
                        or self.model['window_samples'] != WINDOW_SAMPLES
                        or list(self.model['estimator'].classes_) != [0, 1]):
                    raise ValueError('Model feature or window contract does not match this application.')
            except Exception as exc:
                self.model = None
                self.model_error = f'Could not load optical model: {exc}'
        if self.recording_path:
            self.recording_path.parent.mkdir(parents=True, exist_ok=True)
            # Each recording has one owner and one session. Never append a new
            # participant's data to an existing recording accidentally.
            self.recording_file = self.recording_path.open('x', encoding='utf-8')
        self.worker = threading.Thread(target=self._run, daemon=True, name='optical-quality')
        self.worker.start()

    def submit(self, packet):
        if self.closed:
            return
        try:
            self.queue.put_nowait((packet, time.monotonic(), time.time()))
        except queue.Full:
            with self.lock:
                self.dropped_batches += 1

    def _run(self):
        while True:
            item = self.queue.get()
            try:
                if item is None:
                    return
                packet, received, wall_time = item
                self._process(packet, received, wall_time)
            except Exception as exc:
                with self.lock:
                    self.result = dict(status='error', message=f'Optical analysis unavailable: {exc}')
            finally:
                self.queue.task_done()

    def _process(self, packet, received, wall_time):
        if self.recording_file:
            try:
                record = dict(participant=self.participant, session=self.session,
                              received_at=wall_time, packet=packet)
                self.recording_file.write(json.dumps(record, allow_nan=False) + '\n')
                self.recording_file.flush()
            except OSError as exc:
                self.recording_error = str(exc)
        if time.monotonic() - received > 5:
            return
        with self.lock:
            if self.last_received is not None and received - self.last_received > 5:
                self.collector.reset()
            ready = self.collector.append(packet)
            self.last_received = received
            samples = list(self.collector.samples)
        result = dict(status='collecting', message='Collecting a ten-second optical window.')
        if ready:
            result = dict(status='model_missing', message='Waveform ready; no trained model loaded.')
            if self.model:
                score = float(self.model['estimator'].predict_proba(
                    [extract_features([row[1] for row in samples])])[0, 1])
                result = dict(
                    status='prediction', label='usable' if score >= 0.5 else 'unreliable',
                    score=score, mode='shadow', domain=self.model['domain'],
                    model_version=self.model['model_version'],
                    message='Research prediction; measured values are unchanged.',
                    window_start_ms=samples[0][0], window_end_ms=samples[-1][0])
        with self.lock:
            self.result = result

    def snapshot(self):
        with self.lock:
            fresh = self.last_received is not None and time.monotonic() - self.last_received < 5
            result = dict(self.result) if fresh else dict(
                status='waiting', message='No fresh raw waveform. Connect firmware rpm-2.2.0 or newer.')
            result.update(
                samples_collected=len(self.collector.samples) if fresh else 0,
                required_samples=WINDOW_SAMPLES, sample_rate_hz=RATE,
                dropped_batches=self.dropped_batches, gaps=self.collector.gaps,
                recording=bool(self.recording_file) and not self.recording_error,
                recording_error=self.recording_error, model_error=self.model_error,
                waveform=[list(row) for row in self.collector.samples] if fresh else [],
                device_id=self.collector.identity[0] if self.collector.identity else None)
            return result

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.queue.put(None)
        self.worker.join(timeout=10)
        if self.recording_file:
            self.recording_file.close()
