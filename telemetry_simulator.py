"""Explicitly synthetic telemetry for the dashboard's isolated demo mode."""
import json
import math
import threading
import time

from temperature_safety import FEVER_MESSAGE

DEVICE_ID = 'SIMULATED-NODE'
# Durations are wall-clock seconds. Recovery allows a full rolling minute to clear.
PHASES = (
    ('Steady readings', 45, 72, 98, True, False),
    ('Oxygen reading needs review', 50, 110, 93, True, False),
    ('Persistent concerning readings', 45, 150, 88, True, False),
    ('Recovery', 75, 75, 98, True, False),
    ('Finger removed / missing pulse data', 15, 72, 98, False, False),
    ('SOS button demonstration', 10, 72, 98, False, True),
    ('Signal restored / recovery', 75, 72, 98, True, False),
)


def scenario(elapsed):
    position = elapsed % sum(row[1] for row in PHASES)
    for row in PHASES:
        if position < row[1]:
            return row
        position -= row[1]
    return PHASES[0]


def make_packet(second, elapsed=0):
    name, _, hr, spo2, usable, sos = scenario(elapsed)
    hr = round(hr + 1.5 * math.sin(second / 7), 1)
    spo2 = round(spo2 + .2 * math.sin(second / 11), 1)
    motion = round(1 + .015 * math.sin(second / 3), 4)
    timestamp = second * 1000
    raw_temperature = round((29.65 + .15 * math.sin(second / 60)) * 128)
    return dict(
        schema_version=2, device_id=DEVICE_ID, uptime_s=second,
        firmware_version='SIMULATION-no-hardware',
        board=dict(flash_bytes=None, psram_bytes=None),
        sensors=dict(oled=False, max=True, mpu=True, tmp117=True,
                     sht40=False, mlx=False, active=3, active_max=3),
        alerts=dict(sos=sos, fall=False), risk='UNKNOWN', urgent=sos,
        status_summary=f'SIMULATED DATA: {name}. No ESP32 or patient is connected.',
        vitals=dict(
            heart_rate=hr if usable else None,
            heart_rate_status='valid' if usable else 'not_available',
            heart_rate_timestamp_ms=timestamp if usable else None,
            spo2=spo2 if usable else None,
            spo2_status='valid' if usable else 'not_available',
            spo2_timestamp_ms=timestamp if usable else None,
            finger_on=usable, optical_signal_quality='good' if usable else 'no_finger',
            optical_perfusion_index=4.4 if usable else 0,
            raw_red=90000 if usable else 100, raw_ir=100000 if usable else 120,
            motion_g=motion, motion_status='valid', motion_timestamp_ms=timestamp,
            acceleration=dict(x_g=0, y_g=0, z_g=motion, magnitude_g=motion),
            gyroscope=dict(x_dps=0, y_dps=0, z_dps=0, magnitude_dps=0),
            activity_state='stationary', orientation='z_up', steps=0,
            tmp117_sensor_temperature_c=raw_temperature / 128,
            tmp117_sensor_temperature_raw=raw_temperature,
            tmp117_sensor_temperature_status='valid',
            tmp117_sensor_temperature_timestamp_ms=timestamp,
            wrist_contact_status='unverified', wrist_skin_temperature_c=None,
            wrist_skin_temperature_status='unverified',
            wrist_skin_temperature_raw=None, wrist_skin_temperature_timestamp_ms=None,
            estimated_core_temperature_c=None, estimated_core_temperature_status='not_available',
            fever_screening=dict(status='not_available', message=FEVER_MESSAGE, rule=None),
        ),
    )


class TelemetrySimulator:
    """Feed the real parser, store, SSE and models, without opening serial ports."""
    def __init__(self, bridge):
        self.bridge = bridge
        self.stop_event = threading.Event()
        self.thread = None
        self.phase = 0.0
        self.sample_seq = 0

    def waveform(self, second, elapsed):
        _, _, hr, _, usable, _ = scenario(elapsed)
        samples = []
        for i in range(25):
            self.phase += 2 * math.pi * hr / 60 / 25
            pulse = math.sin(self.phase)
            red = int(90000 + 2000 * pulse) if usable else 100
            ir = int(100000 + 2300 * pulse) if usable else 120
            samples.append([second * 1000 + i * 40, red, ir])
        result = dict(schema_version=1, device_id=DEVICE_ID, boot_id=1,
                      seq_start=self.sample_seq, sample_rate_hz=25, samples=samples)
        self.sample_seq += 25
        return result

    def step(self, second, elapsed, historical_at=None):
        b = self.bridge
        name = scenario(elapsed)[0]
        raw = self.waveform(second, elapsed)
        parsed_raw = b.parse_raw_packet('[PPG] ' + json.dumps(raw))
        if parsed_raw is None:
            raise ValueError('Simulator emitted an invalid optical packet.')
        b.optical_service.submit(parsed_raw)
        # Serial acquisition is not involved; finish the demo batch before
        # taking its quality snapshot so both models see matching evidence.
        b.optical_service.queue.join()
        packet = b.parse_packet(json.dumps(make_packet(second, elapsed), allow_nan=False))
        if packet is None:
            raise ValueError('Simulator emitted an invalid telemetry packet.')
        with b.state_lock:
            b.hardware_status.update(simulation=True, simulation_phase=name,
                port='In-memory simulator', baud=None)
        if historical_at is not None:
            b.telemetry_store.record(packet, now=historical_at)
            enrollment_id = b.personal_baseline.summary(DEVICE_ID).get('id')
            b.priority_service.submit(packet, b.optical_service.snapshot(), enrollment_id)
        else:
            b._accept_packet(packet)
        b.priority_service.work.join()
        if historical_at is None:
            b.broadcast()

    def start(self):
        # A disclosed synthetic pre-roll provides an immediate model result and
        # a visible minute of chart history without accelerating live device time.
        now = time.time()
        self.bridge.personal_baseline.start(DEVICE_ID, 'Simulated patient — demo only', now=now - 60)
        for second in range(60):
            self.step(second, 0, historical_at=now - 60 + second)
        self.step(60, 0)
        self.thread = threading.Thread(target=self._run, daemon=True, name='telemetry-simulation')
        self.thread.start()

    def _run(self):
        elapsed = 0
        while not self.stop_event.wait(1):
            elapsed += 1
            try:
                self.step(60 + elapsed, elapsed)
            except Exception as exc:
                self.bridge.set_disconnected(f'Simulation stopped: {exc}')
                return

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=10)
