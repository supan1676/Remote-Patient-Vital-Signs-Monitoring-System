"""Synthetic-policy alert prioritization; no clinical-risk claim or temperature input."""
from collections import deque
from pathlib import Path
import queue
import threading
import time

import numpy as np

WINDOW = 60
FEATURE_VERSION = 1
POLICY_VERSION = 'engineering-alert-policy-v1'
LABELS = ('green', 'yellow', 'red')
FEATURE_NAMES = (
    'hr_current', 'spo2_current', 'hr_mean', 'spo2_mean', 'hr_std', 'spo2_std',
    'hr_min', 'hr_max', 'spo2_min', 'hr_change', 'spo2_change',
    'hr_slope_per_min', 'spo2_slope_per_min', 'movement_mean', 'movement_current',
    'active_fraction', 'motion_coverage', 'valid_fraction', 'recent_valid_fraction',
    'hr_low_run_s', 'hr_high_rest_run_s', 'hr_very_high_run_s',
    'spo2_low_run_s', 'spo2_warn_fraction', 'hr_warn_fraction',
    'combined_warn_run_s', 'rest_or_unknown_current',
)


def _mean(x, mask):
    count = mask.sum(axis=1)
    return np.divide(np.where(mask, x, 0).sum(axis=1), count,
                     out=np.full(len(x), np.nan), where=count > 0)


def _suffix(mask):
    return np.cumprod(mask[:, ::-1], axis=1).sum(axis=1)


def extract_features(signals, quality):
    """Identical batch/runtime features, from observed HR, SpO2, motion only.

    signals: [scenario, 60 seconds, 3 channels]; quality: optical usable mask.
    Missing measurements remain NaN. No label, profile ID or scenario ID enters.
    """
    x = np.asarray(signals, dtype=np.float64)
    q = np.asarray(quality, dtype=bool)
    if x.ndim != 3 or x.shape[1:] != (WINDOW, 3) or q.shape != x.shape[:2]:
        raise ValueError('Expected sixty one-second HR/SpO2/motion observations.')
    hr, spo2, motion = (x[:, :, i] for i in range(3))
    valid = q & np.isfinite(hr) & np.isfinite(spo2) & (hr >= 20) & (hr <= 250) & (spo2 > 0) & (spo2 <= 100)
    motion_valid = np.isfinite(motion) & (motion >= 0) & (motion <= 20)
    movement = np.abs(motion - 1)
    rest = ~motion_valid | (movement < .12)
    hr_mean, spo2_mean = _mean(hr, valid), _mean(spo2, valid)
    hr_std = np.sqrt(_mean((hr - hr_mean[:, None]) ** 2, valid))
    spo2_std = np.sqrt(_mean((spo2 - spo2_mean[:, None]) ** 2, valid))
    count = valid.sum(axis=1)
    t = np.broadcast_to(np.arange(WINDOW), hr.shape)
    t_mean = _mean(t, valid)
    centered_t = t - t_mean[:, None]
    denominator = np.where(valid, centered_t ** 2, 0).sum(axis=1)
    slopes = []
    for channel, mean in ((hr, hr_mean), (spo2, spo2_mean)):
        numerator = np.where(valid, (channel - mean[:, None]) * centered_t, 0).sum(axis=1)
        slopes.append(np.divide(numerator * 60, denominator,
                      out=np.zeros(len(x)), where=denominator > 0))
    def extreme(channel, minimum):
        values = np.where(valid, channel, np.inf if minimum else -np.inf)
        result = values.min(axis=1) if minimum else values.max(axis=1)
        return np.where(count > 0, result, np.nan)
    recent = valid[:, -30:]
    hr_warning = (hr < 50) | ((hr > 120) & rest)
    values = (
        np.where(valid[:, -1], hr[:, -1], np.nan),
        np.where(valid[:, -1], spo2[:, -1], np.nan), hr_mean, spo2_mean, hr_std, spo2_std,
        extreme(hr, True), extreme(hr, False), extreme(spo2, True),
        _mean(hr[:, -10:], valid[:, -10:]) - _mean(hr[:, :10], valid[:, :10]),
        _mean(spo2[:, -10:], valid[:, -10:]) - _mean(spo2[:, :10], valid[:, :10]),
        *slopes, _mean(movement, motion_valid),
        np.where(motion_valid[:, -1], movement[:, -1], np.nan),
        (motion_valid & (movement >= .12)).mean(axis=1), motion_valid.mean(axis=1),
        valid.mean(axis=1), valid[:, -3:].mean(axis=1),
        _suffix(valid & (hr <= 40)), _suffix(valid & (hr >= 140) & rest),
        _suffix(valid & (hr >= 190)), _suffix(valid & (spo2 <= 90)),
        _mean((spo2[:, -30:] < 95).astype(float), recent),
        _mean(hr_warning[:, -30:].astype(float), recent),
        _suffix(valid & (spo2 < 93) & (hr > 120) & rest), rest[:, -1].astype(float),
    )
    return np.column_stack(values).astype(np.float32)


def policy_labels(features):
    """Documented, unreviewed engineering assumptions; not NEWS2 or clinical truth.

    -1 = unknown. All other labels express the synthetic rulebook's priority.
    """
    f = {name: features[:, i] for i, name in enumerate(FEATURE_NAMES)}
    eligible = (f['valid_fraction'] >= .9) & (f['recent_valid_fraction'] == 1)
    eligible &= np.isfinite(f['hr_current']) & np.isfinite(f['spo2_current'])
    red = ((f['spo2_low_run_s'] >= 10) | (f['hr_low_run_s'] >= 10)
           | (f['hr_high_rest_run_s'] >= 15) | (f['hr_very_high_run_s'] >= 15)
           | (f['combined_warn_run_s'] >= 20))
    yellow = ((f['spo2_current'] < 95) | (f['hr_current'] < 50)
              | ((f['hr_current'] > 120) & (f['rest_or_unknown_current'] == 1))
              | (f['spo2_warn_fraction'] >= .2) | (f['hr_warn_fraction'] >= .2)
              | ((f['spo2_change'] <= -3) & (f['spo2_current'] < 96))
              | ((f['hr_change'] >= 25) & (f['hr_current'] >= 100)
                 & (f['rest_or_unknown_current'] == 1)))
    labels = np.where(red, 2, np.where(yellow, 1, 0)).astype(np.int8)
    labels[~eligible] = -1
    return labels


def _unknown(message, **extra):
    return dict(zone='unknown', source='insufficient_evidence', message=message,
                synthetic_training=True, clinically_validated=False, **extra)


def _usable(packet, optical=None):
    v = packet['vitals']
    valid = (packet['sensors'].get('max') is True and v.get('finger_on') is True
             and v.get('heart_rate_status') == 'valid' and v.get('spo2_status') == 'valid'
             and v.get('optical_signal_quality') == 'good')
    if (optical and optical.get('device_id') == packet['device_id']
            and optical.get('status') == 'prediction' and optical.get('label') == 'unreliable'):
        valid = False
    return valid


class AlertPriorityService:
    """One-minute rolling observations and bounded background prediction."""
    def __init__(self, model_path):
        self.model = None
        self.error = None
        path = Path(model_path)
        if path.exists():
            try:
                import joblib
                self.model = joblib.load(path)
                if (self.model['feature_names'] != list(FEATURE_NAMES)
                        or self.model['feature_version'] != FEATURE_VERSION
                        or self.model['policy_version'] != POLICY_VERSION
                        or list(self.model['estimator'].classes_) != [0, 1, 2]
                        or self.model.get('training_source') != 'synthetic'):
                    raise ValueError('Incompatible priority model contract.')
            except Exception as exc:
                self.model = None
                self.error = str(exc)
        self.lock = threading.Lock()
        self.rows = deque(maxlen=WINDOW)
        self.context = None
        self.last_second = None
        self.last_received = None
        self.result = _unknown('Collecting one minute of usable observations.')
        self.work = queue.Queue(maxsize=8)
        self.dropped = 0
        self.closed = False
        self.thread = threading.Thread(target=self._run, daemon=True, name='alert-priority')
        self.thread.start()

    def submit(self, packet, optical=None, enrollment_id=None):
        if self.closed:
            return
        sample = dict(device_id=packet['device_id'], uptime_s=packet['uptime_s'],
                      vitals=packet['vitals'].copy(), alerts=packet['alerts'].copy(),
                      sensors=packet['sensors'].copy())
        try:
            self.work.put_nowait((sample, optical, enrollment_id, time.monotonic()))
        except queue.Full:
            with self.lock:
                self.dropped += 1

    def _run(self):
        while True:
            item = self.work.get()
            try:
                if item is None:
                    return
                self._process(*item)
            except Exception as exc:
                with self.lock:
                    self.result = _unknown('Priority analysis unavailable.', error=str(exc))
            finally:
                self.work.task_done()

    def _process(self, packet, optical, enrollment_id, received):
        if time.monotonic() - received > 5:
            return
        context = (packet['device_id'], enrollment_id)
        second = int(packet['uptime_s'])
        v = packet['vitals']
        good = _usable(packet, optical)
        hr, spo2 = (v.get('heart_rate'), v.get('spo2')) if good else (np.nan, np.nan)
        motion = v.get('motion_g') if v.get('motion_status') == 'valid' else np.nan
        row = (hr, spo2, motion, good)
        with self.lock:
            if (context != self.context or self.last_second is None
                    or second < self.last_second or second - self.last_second > 5
                    or (self.last_received is not None and received - self.last_received > 5)):
                self.rows.clear()
                self.last_second = None
                self.context = context
            if self.last_second == second:
                self.rows[-1] = row
            else:
                if self.last_second is not None:
                    for _ in range(second - self.last_second - 1):
                        self.rows.append((np.nan, np.nan, np.nan, False))
                self.rows.append(row)
            self.last_second = second
            self.last_received = received
            rows = list(self.rows)
        result = _unknown('Collecting one minute of usable observations.', observations=len(rows))
        if len(rows) == WINDOW:
            array = np.asarray(rows, dtype=np.float64)
            features = extract_features(array[None, :, :3], array[None, :, 3].astype(bool))
            eligible = policy_labels(features)[0] >= 0
            if not eligible:
                result = _unknown('Recent pulse readings are missing or unreliable.', observations=WINDOW)
            elif self.model is None:
                result = _unknown('No trained priority model loaded.', observations=WINDOW)
            else:
                # Histogram boosting uses OpenMP; avoid a large CPU pool on a
                # one-row prediction that shares a host with serial ingestion.
                from threadpoolctl import threadpool_limits
                with threadpool_limits(limits=1):
                    scores = self.model['estimator'].predict_proba(features)[0]
                zone = LABELS[int(np.argmax(scores))]
                result = dict(zone=zone, source='trained_model', observations=WINDOW,
                    synthetic_training=True, clinically_validated=False,
                    model_version=self.model['model_version'], policy_version=POLICY_VERSION,
                    class_scores=dict(zip(LABELS, map(float, scores))),
                    message={'green': 'No configured concerning pattern in the available signals.',
                             'yellow': 'Review the readings and recent changes.',
                             'red': 'Promptly check on the person and review the readings.'}[zone])
        with self.lock:
            self.result = result

    def snapshot(self, packet, optical=None):
        # Manual alarms bypass inference and missing-data gates immediately.
        if packet and (packet['alerts'].get('sos') or packet['alerts'].get('fall')):
            return dict(zone='red', source='device_alert', synthetic_training=True,
                        clinically_validated=False,
                        message='SOS active: check on the person.' if packet['alerts'].get('sos')
                        else 'Possible fall reported: check on the person.')
        with self.lock:
            fresh = self.last_received is not None and time.monotonic() - self.last_received < 5
            matches = packet and self.context and packet['device_id'] == self.context[0]
            result = dict(self.result) if fresh and matches else _unknown('No fresh observations available.')
            if packet and not _usable(packet, optical):
                result = _unknown('Current pulse readings are missing or unreliable.')
            result.update(required_observations=WINDOW, model_error=self.error,
                          observations=len(self.rows) if fresh and matches else 0,
                          dropped_batches=self.dropped, training_source='synthetic')
            return result

    def close(self):
        if not self.closed:
            self.closed = True
            self.work.put(None)
            self.thread.join(timeout=10)
