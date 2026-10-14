"""Local measurement history. Stores only valid device observations, never demo data."""
import math
import sqlite3
import threading
import time
from pathlib import Path

METRICS = {
    'heart_rate': {'label': 'Heart rate', 'unit': 'bpm', 'sensor': 'max'},
    'spo2': {'label': 'Oxygen saturation', 'unit': '%', 'sensor': 'max'},
    'temp_object': {'label': 'Surface temperature', 'unit': '°C', 'sensor': 'mlx'},
    'motion_g': {'label': 'Motion', 'unit': 'g', 'sensor': 'mpu'},
}


def measurements(packet):
    """Retain physical zero values but exclude missing and offline measurements."""
    values = packet.get('vitals', {})
    sensors = packet.get('sensors', {})
    result = {}
    for key, meta in METRICS.items():
        value = values.get(key)
        valid = (sensors.get(meta['sensor']) is True and isinstance(value, (int, float))
                 and not isinstance(value, bool) and math.isfinite(value))
        if meta['sensor'] == 'max':
            valid = valid and values.get('finger_on') is True and value > 0
        if key == 'spo2':
            valid = valid and value <= 100
        result[key] = value if valid else None
    return result


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
                heart_rate REAL, spo2 REAL, temp_object REAL, motion_g REAL,
                raw_ir REAL, raw_red REAL, finger_on INTEGER,
                sos INTEGER NOT NULL, fall INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS observations_device_time
                ON observations(device_id, recorded_at);
        ''')
        self.db.commit()
        self.last_cleanup = 0

    def record(self, packet, now=None):
        now = time.time() if now is None else now
        values = measurements(packet)
        v, alerts = packet['vitals'], packet['alerts']
        with self.lock, self.db:
            self.db.execute('''INSERT INTO observations
                (device_id,recorded_at,uptime_s,heart_rate,spo2,temp_object,motion_g,
                 raw_ir,raw_red,finger_on,sos,fall) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                (packet['device_id'], now, packet.get('uptime_s'),
                 *values.values(), v.get('raw_ir'), v.get('raw_red'),
                 v.get('finger_on') is True, alerts.get('sos') is True, alerts.get('fall') is True))
            if now - self.last_cleanup >= 3600:
                self.db.execute('DELETE FROM observations WHERE recorded_at < ?', (now-30*86400,))
                self.last_cleanup = now

    def history(self, device_id, seconds=900, now=None):
        now = time.time() if now is None else now
        seconds = max(60, min(int(seconds), 7*86400))
        bucket = max(1, seconds // 450)
        with self.lock:
            rows = self.db.execute('''SELECT CAST(recorded_at / ? AS INTEGER) * ? AS time,
                AVG(heart_rate) AS heart_rate, AVG(spo2) AS spo2,
                AVG(temp_object) AS temp_object, AVG(motion_g) AS motion_g,
                COUNT(*) AS samples, MAX(sos) AS sos, MAX(fall) AS fall
                FROM observations WHERE device_id = ? AND recorded_at >= ?
                GROUP BY CAST(recorded_at / ? AS INTEGER) ORDER BY time''',
                (bucket, bucket, device_id, now-seconds, bucket)).fetchall()
        # Preserve gaps as null points, including bins without any serial packets.
        indexed = {int(row['time']): dict(row) for row in rows}
        start = int((now-seconds)//bucket)*bucket
        end = int(now//bucket)*bucket
        points = [indexed.get(t, dict(time=t, **{key: None for key in METRICS},
                   samples=0, sos=0, fall=0)) for t in range(start,end+1,bucket)]
        return {'device_id': device_id, 'bucket_seconds': bucket, 'points': points}

    def close(self):
        with self.lock:
            self.db.close()
