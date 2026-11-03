"""Local measurement history. Stores only valid device observations, never demo data."""
import math
import sqlite3
import threading
import time
from pathlib import Path

# The installed measurement channels in the current build. Optional legacy
# modules are deliberately not part of the active baseline.
ACTIVE_METRICS = {
    'heart_rate': {
        'label': 'Heart rate', 'unit': 'bpm', 'sensor': 'max',
        'status': 'heart_rate_status', 'range': (20, 250), 'optical': True,
    },
    'spo2': {
        'label': 'Oxygen saturation', 'unit': '%', 'sensor': 'max',
        'status': 'spo2_status', 'range': (0, 100), 'optical': True,
    },
    'wrist_skin_temperature': {
        'label': 'Wrist skin temperature', 'unit': '°C', 'sensor': 'tmp117',
        'status': 'wrist_skin_temperature_status', 'range': (-10, 60),
        'field': 'wrist_skin_temperature_c',
    },
    'motion_g': {
        'label': 'Movement', 'unit': 'g', 'sensor': 'mpu',
        'status': 'motion_status', 'range': (0, 20),
    },
}
LEGACY_METRICS = {
    'temp_object': {
        'label': 'Legacy surface temperature', 'unit': '°C', 'sensor': 'mlx',
        'status': None, 'range': (-70, 380),
    },
}
METRICS = {**ACTIVE_METRICS, **LEGACY_METRICS}
ACTIVE_METRIC_KEYS = tuple(ACTIVE_METRICS)

# Columns added after the first local database version. The migration is
# additive so existing recordings remain readable.
MIGRATION_COLUMNS = {
    'wrist_skin_temperature': 'REAL',
    'wrist_skin_temperature_raw': 'INTEGER',
    'heart_rate_status': 'TEXT',
    'spo2_status': 'TEXT',
    'wrist_skin_temperature_status': 'TEXT',
    'motion_status': 'TEXT',
    'tmp117_sensor_temperature': 'REAL',
    'tmp117_sensor_temperature_raw': 'INTEGER',
    'tmp117_sensor_temperature_timestamp_ms': 'INTEGER',
    'tmp117_sensor_temperature_status': 'TEXT',
}


def _finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) else None


def _valid_status(packet, meta):
    """A metric is stored only when its explicit status says it is valid."""
    vitals = packet.get('vitals', {})
    status_field = meta.get('status')
    if not status_field:
        return True
    return vitals.get(status_field) == 'valid'


def measurements(packet):
    """Return valid processed values, never a substitute for missing data."""
    values = packet.get('vitals', {})
    sensors = packet.get('sensors', {})
    result = {}
    for key, meta in METRICS.items():
        value = _finite_number(values.get(meta.get('field', key)))
        valid = (sensors.get(meta['sensor']) is True and value is not None
                 and _valid_status(packet, meta))
        if meta.get('optical'):
            valid = valid and values.get('finger_on') is True
        if key == 'wrist_skin_temperature':
            raw = raw_wrist_code(packet)
            timestamp = values.get('wrist_skin_temperature_timestamp_ms')
            actual_status = values.get('tmp117_sensor_temperature_status')
            actual_value = _finite_number(values.get('tmp117_sensor_temperature_c'))
            actual_raw_value = values.get('tmp117_sensor_temperature_raw')
            actual_raw = (actual_raw_value
                          if isinstance(actual_raw_value, int)
                          and not isinstance(actual_raw_value, bool)
                          and 0 <= actual_raw_value <= 0xFFFF else None)
            actual_timestamp = values.get('tmp117_sensor_temperature_timestamp_ms')
            if values.get('wrist_contact_status') != 'verified':
                valid = False
            if raw is None or raw in (0x0000, 0xFFFF):
                valid = False
            elif value is not None:
                signed = raw - 0x10000 if raw & 0x8000 else raw
                if abs(signed * 0.0078125 - value) > 0.02:
                    valid = False
            if (actual_status != 'valid' or value is None
                    or actual_value is None or actual_raw != raw
                    or actual_timestamp != timestamp
                    or abs(actual_value - value) > 0.02):
                valid = False
            if isinstance(timestamp, bool) or not isinstance(timestamp, int) \
                    or timestamp < 0:
                valid = False
        if value is not None:
            low, high = meta['range']
            valid = valid and low <= value <= high
        result[key] = value if valid else None
    return result


def raw_wrist_code(packet):
    """Retain the raw TMP117 register code for audit when present."""
    value = packet.get('vitals', {}).get('wrist_skin_temperature_raw')
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 <= value <= 0xFFFF else None


def actual_tmp117_reading(packet):
    """Validate the actual TMP117 sensor value for diagnostic storage.

    This is deliberately not a clinical metric and is never copied into the
    wrist history. The bridge already validates the packet; this second check
    keeps a legacy or malformed packet from putting an inconsistent value in
    local history.
    """
    vitals = packet.get('vitals', {})
    sensors = packet.get('sensors', {})
    status = vitals.get('tmp117_sensor_temperature_status')
    value = _finite_number(vitals.get('tmp117_sensor_temperature_c'))
    raw = vitals.get('tmp117_sensor_temperature_raw')
    timestamp = vitals.get('tmp117_sensor_temperature_timestamp_ms')
    raw_valid = (isinstance(raw, int) and not isinstance(raw, bool)
                 and 0 <= raw <= 0xFFFF)
    timestamp_valid = (isinstance(timestamp, int)
                       and not isinstance(timestamp, bool)
                       and timestamp >= 0)
    valid = (sensors.get('tmp117') is True and status == 'valid'
             and value is not None and raw_valid and raw not in (0x0000, 0xFFFF)
             and timestamp_valid and -55.0 <= value <= 150.0)
    if valid:
        signed = raw - 0x10000 if raw & 0x8000 else raw
        if abs(signed * 0.0078125 - value) > 0.02:
            valid = False
    return {
        'value': value if valid else None,
        'raw': raw if valid else None,
        'timestamp_ms': timestamp if valid else None,
        'status': status if isinstance(status, str) else None,
    }


class TelemetryStore:
    def __init__(self, path):
        self.path = str(path)
        if self.path != ':memory:':
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY, device_id TEXT NOT NULL,
                recorded_at REAL NOT NULL, uptime_s REAL,
                heart_rate REAL, spo2 REAL,
                wrist_skin_temperature REAL,
                wrist_skin_temperature_raw INTEGER,
                temp_object REAL, motion_g REAL,
                raw_ir REAL, raw_red REAL, finger_on INTEGER,
                sos INTEGER NOT NULL, fall INTEGER NOT NULL,
                heart_rate_status TEXT, spo2_status TEXT,
                wrist_skin_temperature_status TEXT, motion_status TEXT,
                tmp117_sensor_temperature REAL,
                tmp117_sensor_temperature_raw INTEGER,
                tmp117_sensor_temperature_timestamp_ms INTEGER,
                tmp117_sensor_temperature_status TEXT
            );
            CREATE INDEX IF NOT EXISTS observations_device_time
                ON observations(device_id, recorded_at);
        ''')
        self._migrate()
        self.db.commit()
        self.last_cleanup = 0

    def _migrate(self):
        """Add new columns to databases created by an earlier build."""
        existing = {row['name'] for row in
                    self.db.execute('PRAGMA table_info(observations)').fetchall()}
        for name, sql_type in MIGRATION_COLUMNS.items():
            if name not in existing:
                self.db.execute(f'ALTER TABLE observations ADD COLUMN {name} {sql_type}')
        self.db.execute('CREATE INDEX IF NOT EXISTS observations_device_time '
                        'ON observations(device_id, recorded_at)')

    def record(self, packet, now=None):
        now = time.time() if now is None else now
        values = measurements(packet)
        vitals, alerts = packet['vitals'], packet['alerts']
        stored_wrist_raw = (raw_wrist_code(packet)
                            if values['wrist_skin_temperature'] is not None
                            else None)
        actual_tmp117 = actual_tmp117_reading(packet)
        with self.lock, self.db:
            self.db.execute('''INSERT INTO observations
                (device_id,recorded_at,uptime_s,heart_rate,spo2,
                 wrist_skin_temperature,wrist_skin_temperature_raw,temp_object,
                 motion_g,raw_ir,raw_red,finger_on,sos,fall,
                 heart_rate_status,spo2_status,wrist_skin_temperature_status,
                 motion_status,tmp117_sensor_temperature,
                 tmp117_sensor_temperature_raw,
                 tmp117_sensor_temperature_timestamp_ms,
                 tmp117_sensor_temperature_status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (packet['device_id'], now, packet.get('uptime_s'),
                 values['heart_rate'], values['spo2'],
                 values['wrist_skin_temperature'], stored_wrist_raw,
                 values['temp_object'], values['motion_g'],
                 vitals.get('raw_ir'), vitals.get('raw_red'),
                 vitals.get('finger_on') is True,
                 alerts.get('sos') is True, alerts.get('fall') is True,
                 vitals.get('heart_rate_status'), vitals.get('spo2_status'),
                 vitals.get('wrist_skin_temperature_status'),
                 vitals.get('motion_status'), actual_tmp117['value'],
                 actual_tmp117['raw'], actual_tmp117['timestamp_ms'],
                 actual_tmp117['status']))
            if now - self.last_cleanup >= 3600:
                self.db.execute('DELETE FROM observations WHERE recorded_at < ?',
                                (now - 30 * 86400,))
                self.last_cleanup = now

    def history(self, device_id, seconds=900, now=None):
        now = time.time() if now is None else now
        seconds = max(60, min(int(seconds), 7 * 86400))
        bucket = max(1, seconds // 450)
        with self.lock:
            rows = self.db.execute('''SELECT CAST(recorded_at / ? AS INTEGER) * ? AS time,
                AVG(heart_rate) AS heart_rate, AVG(spo2) AS spo2,
                AVG(wrist_skin_temperature) AS wrist_skin_temperature,
                AVG(temp_object) AS temp_object, AVG(motion_g) AS motion_g,
                COUNT(CASE WHEN heart_rate IS NOT NULL OR spo2 IS NOT NULL
                    OR wrist_skin_temperature IS NOT NULL OR motion_g IS NOT NULL
                    THEN 1 END) AS samples,
                MAX(sos) AS sos, MAX(fall) AS fall
                FROM observations WHERE device_id = ? AND recorded_at >= ?
                GROUP BY CAST(recorded_at / ? AS INTEGER) ORDER BY time''',
                (bucket, bucket, device_id, now - seconds, bucket)).fetchall()
        # Preserve gaps as null points, including bins without any serial packets.
        indexed = {int(row['time']): dict(row) for row in rows}
        start = int((now - seconds) // bucket) * bucket
        end = int(now // bucket) * bucket
        points = [indexed.get(t, dict(time=t, **{key: None for key in METRICS},
                                      samples=0, sos=0, fall=0))
                  for t in range(start, end + 1, bucket)]
        return {'device_id': device_id, 'bucket_seconds': bucket, 'points': points}

    def close(self):
        with self.lock:
            self.db.close()
