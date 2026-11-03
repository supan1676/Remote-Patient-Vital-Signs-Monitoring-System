import sqlite3
import tempfile
import unittest
from pathlib import Path

from fixtures import packet, verified_packet
from telemetry_store import (ACTIVE_METRICS, TelemetryStore, actual_tmp117_reading,
                             measurements)


class HistoryTests(unittest.TestCase):
    def test_invalid_or_missing_is_not_zero_and_zero_is_not_missing(self):
        p = packet(motion_g=0.0)
        self.assertEqual(measurements(p)['motion_g'], 0.0)
        self.assertIsNone(measurements(p)['wrist_skin_temperature'])
        p['vitals']['motion_status'] = 'not_available'
        p['vitals']['motion_g'] = None
        p['vitals']['finger_on'] = False
        self.assertIsNone(measurements(p)['motion_g'])
        self.assertIsNone(measurements(p)['heart_rate'])

    def test_unverified_contact_is_never_stored_as_a_wrist_value(self):
        p = packet()
        p['vitals'].update(
            wrist_skin_temperature_c=29.6484375,
            wrist_skin_temperature_status='valid',
            wrist_skin_temperature_raw=3795,
            wrist_skin_temperature_timestamp_ms=5000,
        )
        self.assertIsNone(measurements(p)['wrist_skin_temperature'])

    def test_actual_tmp117_is_stored_as_a_diagnostic_not_a_wrist_value(self):
        p = packet()
        self.assertIsNone(measurements(p)['wrist_skin_temperature'])
        actual = actual_tmp117_reading(p)
        self.assertAlmostEqual(actual['value'], 29.6484375)
        self.assertEqual(actual['raw'], 3795)
        self.assertEqual(actual['timestamp_ms'], 5000)
        self.assertEqual(actual['status'], 'valid')

        store = TelemetryStore(':memory:')
        store.record(p, now=10000)
        row = store.db.execute(
            'SELECT wrist_skin_temperature, tmp117_sensor_temperature, '
            'tmp117_sensor_temperature_raw, '
            'tmp117_sensor_temperature_timestamp_ms, '
            'tmp117_sensor_temperature_status FROM observations').fetchone()
        self.assertIsNone(row['wrist_skin_temperature'])
        self.assertAlmostEqual(row['tmp117_sensor_temperature'], 29.6484375)
        self.assertEqual(row['tmp117_sensor_temperature_raw'], 3795)
        self.assertEqual(row['tmp117_sensor_temperature_timestamp_ms'], 5000)
        self.assertEqual(row['tmp117_sensor_temperature_status'], 'valid')
        store.close()

    def test_invalid_actual_tmp117_evidence_is_not_stored_as_a_value(self):
        for overrides in (
            {'tmp117_sensor_temperature_status': 'low_quality'},
            {'tmp117_sensor_temperature_raw': 0xFFFF,
             'tmp117_sensor_temperature_c': -0.0078125},
            {'tmp117_sensor_temperature_raw': 0x0000,
             'tmp117_sensor_temperature_c': 0.0},
            {'tmp117_sensor_temperature_raw': None},
            {'tmp117_sensor_temperature_timestamp_ms': None},
            {'tmp117_sensor_temperature_c': 160.0},
        ):
            p = packet()
            p['vitals'].update(overrides)
            actual = actual_tmp117_reading(p)
            self.assertIsNone(actual['value'], overrides)
            self.assertIsNone(actual['raw'], overrides)
            self.assertIsNone(actual['timestamp_ms'], overrides)

    def test_only_explicitly_valid_verified_statuses_are_stored(self):
        p = verified_packet()
        self.assertAlmostEqual(measurements(p)['wrist_skin_temperature'],
                               29.6484375)
        p['vitals'].update(wrist_skin_temperature_status='low_quality',
                           wrist_skin_temperature_c=None,
                           wrist_skin_temperature_raw=None,
                           wrist_skin_temperature_timestamp_ms=None)
        self.assertIsNone(measurements(p)['wrist_skin_temperature'])
        p = verified_packet()
        p['sensors']['tmp117'] = False
        self.assertIsNone(measurements(p)['wrist_skin_temperature'])
        p = verified_packet()
        p['vitals']['wrist_skin_temperature_raw'] = 0xFFFF
        p['vitals']['wrist_skin_temperature_c'] = -0.0078125
        self.assertIsNone(measurements(p)['wrist_skin_temperature'])
        p = verified_packet()
        p['vitals']['wrist_skin_temperature_c'] = 30.0
        self.assertIsNone(measurements(p)['wrist_skin_temperature'])

    def test_missing_raw_cannot_be_a_valid_wrist_temperature(self):
        p = verified_packet()
        p['vitals']['wrist_skin_temperature_raw'] = None
        self.assertIsNone(measurements(p)['wrist_skin_temperature'])

    def test_persistence_device_isolation_and_wrist_raw(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'telemetry.sqlite3'
            store = TelemetryStore(file)
            store.record(verified_packet(), now=10000)
            store.record(packet(device_id='board-b'), now=10001)
            store.close()
            store = TelemetryStore(file)
            history = store.history('RPM-NODE-01', 60, now=10002)
            self.assertEqual(sum(p['samples'] for p in history['points']), 1)
            values = [p['heart_rate'] for p in history['points'] if p['samples']]
            self.assertEqual(values, [72])
            wrist = [p['wrist_skin_temperature'] for p in history['points']
                     if p['samples']]
            self.assertAlmostEqual(wrist[0], 29.6484375)
            row = store.db.execute(
                'SELECT wrist_skin_temperature_raw FROM observations '
                'WHERE device_id=?', ('RPM-NODE-01',)).fetchone()
            self.assertEqual(row['wrist_skin_temperature_raw'], 3795)
            store.close()

    def test_history_keeps_disconnect_gaps(self):
        store = TelemetryStore(':memory:')
        store.record(packet(device_id='board-a'), now=10000)
        store.record(packet(device_id='board-a'), now=10010)
        rows = store.history('board-a', 60, now=10010)['points']
        self.assertTrue(any(p['samples'] == 0 and p['motion_g'] is None
                            for p in rows))
        self.assertTrue(all(p['wrist_skin_temperature'] is None for p in rows))
        for key in ACTIVE_METRICS:
            self.assertIn(key, rows[0])
        self.assertNotIn('temp_object', ACTIVE_METRICS)
        store.close()

    def test_legacy_database_migrates_additively(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'legacy.sqlite3'
            db = sqlite3.connect(file)
            db.executescript('''
                CREATE TABLE observations (
                    id INTEGER PRIMARY KEY, device_id TEXT NOT NULL,
                    recorded_at REAL NOT NULL, uptime_s REAL,
                    heart_rate REAL, spo2 REAL, temp_object REAL, motion_g REAL,
                    raw_ir REAL, raw_red REAL, finger_on INTEGER,
                    sos INTEGER NOT NULL, fall INTEGER NOT NULL
                );
                INSERT INTO observations
                    (device_id,recorded_at,heart_rate,spo2,temp_object,motion_g,
                     finger_on,sos,fall)
                VALUES ('old', 9000, 70, 98, NULL, 1.0, 1, 0, 0);
            ''')
            db.commit()
            db.close()
            store = TelemetryStore(file)
            columns = {row['name'] for row in
                       store.db.execute('PRAGMA table_info(observations)')}
            self.assertTrue({'wrist_skin_temperature', 'heart_rate_status',
                             'wrist_skin_temperature_status', 'motion_status',
                             'tmp117_sensor_temperature',
                             'tmp117_sensor_temperature_raw',
                             'tmp117_sensor_temperature_timestamp_ms',
                             'tmp117_sensor_temperature_status'} <= columns)
            history = store.history('old', 60, now=9001)
            self.assertTrue(any(p['heart_rate'] == 70 for p in history['points']))
            self.assertTrue(all(p['wrist_skin_temperature'] is None
                                for p in history['points']))
            store.close()

    def test_invalid_wrist_status_does_not_enter_history(self):
        p = verified_packet()
        p['vitals'].update(wrist_skin_temperature_status='stale',
                           wrist_skin_temperature_c=None,
                           wrist_skin_temperature_raw=None,
                           wrist_skin_temperature_timestamp_ms=None)
        p['vitals']['fever_screening']['input']['quality'] = 'stale'
        store = TelemetryStore(':memory:')
        store.record(p, now=10000)
        row = store.db.execute(
            'SELECT wrist_skin_temperature, wrist_skin_temperature_raw, '
            'wrist_skin_temperature_status FROM observations').fetchone()
        self.assertIsNone(row['wrist_skin_temperature'])
        self.assertIsNone(row['wrist_skin_temperature_raw'])
        self.assertEqual(row['wrist_skin_temperature_status'], 'stale')
        store.close()


if __name__ == '__main__':
    unittest.main()
