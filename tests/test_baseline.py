import unittest

from fixtures import packet, verified_packet
from personal_baseline import PersonalBaseline, DAY
from telemetry_store import ACTIVE_METRICS, TelemetryStore


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.store = TelemetryStore(':memory:')
        self.baseline = PersonalBaseline(self.store)
        self.start = 100000
        self.baseline.start('RPM-NODE-01', 'A person', now=self.start)

    def tearDown(self):
        self.store.close()

    def populate(self, days=7):
        for day in range(days):
            for minute in range(30):
                p = verified_packet()
                p['vitals']['heart_rate'] = 70
                self.store.record(p, now=self.start + day * DAY + minute * 60)

    def test_seven_days_without_measurements_is_not_ready(self):
        result = self.baseline.summary('RPM-NODE-01', now=self.start + 7 * DAY,
                                       force=True)
        self.assertEqual(result['ready_metrics'], 0)
        self.assertEqual(result['active_metric_count'], 4)
        self.assertEqual(result['metrics']['heart_rate']['status'], 'waiting')
        self.assertNotIn('temp_object', result['metrics'])

    def test_coverage_and_elapsed_time_both_required(self):
        self.populate()
        result = self.baseline.summary('RPM-NODE-01',
                                       now=self.start + 6 * DAY + 2000,
                                       force=True)
        self.assertEqual(result['ready_metrics'], 0)
        result = self.baseline.summary('RPM-NODE-01', now=self.start + 7 * DAY,
                                       force=True)
        self.assertEqual(result['ready_metrics'], 4)
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(set(result['metrics']), set(ACTIVE_METRICS))
        self.assertIn('wrist_skin_temperature', result['metrics'])
        self.assertNotIn('temp_object', result['metrics'])

    def test_short_bursts_do_not_count_as_days(self):
        for day in range(7):
            for second in range(40):
                self.store.record(packet(), now=self.start + day * DAY + second)
        result = self.baseline.summary('RPM-NODE-01', now=self.start + 7 * DAY,
                                       force=True)
        self.assertEqual(result['metrics']['heart_rate']['qualified_days'], 0)
        self.assertEqual(result['metrics']['wrist_skin_temperature']['qualified_days'], 0)

    def test_wrist_model_is_not_core_temperature(self):
        self.populate()
        result = self.baseline.summary('RPM-NODE-01', now=self.start + 7 * DAY,
                                       force=True)
        model = result['metrics']['wrist_skin_temperature']['model']
        self.assertAlmostEqual(model['center'], 29.6484375)
        self.assertEqual(result['metrics']['wrist_skin_temperature']['status'], 'ready')
        self.assertNotIn('core', model)

    def test_model_freezes_and_events_require_sustained_departure(self):
        self.populate()
        now = self.start + 7 * DAY
        first = self.baseline.summary(
            'RPM-NODE-01', now=now, force=True)['metrics']['heart_rate']['model']
        self.assertEqual(first['center'], 70)
        for offset in range(2):
            self.baseline.compare(packet(heart_rate=100), now=now + offset)
        self.assertFalse(any(e['kind'] == 'deviation'
                             for e in self.baseline.events('RPM-NODE-01')))
        self.baseline.compare(packet(heart_rate=100), now=now + 2)
        self.assertEqual(sum(e['kind'] == 'deviation'
                             for e in self.baseline.events('RPM-NODE-01')), 1)
        self.store.record(packet(heart_rate=200), now=now + 3)
        second = self.baseline.summary(
            'RPM-NODE-01', now=now + 4, force=True
        )['metrics']['heart_rate']['model']
        self.assertEqual(first, second)

    def test_new_wearer_does_not_inherit_reference(self):
        self.populate()
        self.baseline.summary('RPM-NODE-01', now=self.start + 7 * DAY, force=True)
        self.baseline.end('RPM-NODE-01')
        result = self.baseline.start('RPM-NODE-01', 'Someone else',
                                     now=self.start + 8 * DAY)
        self.assertEqual(result['ready_metrics'], 0)
        self.assertEqual(result['metrics']['heart_rate']['valid_minutes'], 0)

    def test_other_device_and_duplicate_enrollment(self):
        self.assertEqual(self.baseline.summary('board-b', now=self.start)['status'],
                         'not_started')
        with self.assertRaises(ValueError):
            self.baseline.start('RPM-NODE-01', 'Different wearer', now=self.start)

    def test_low_quality_wrist_does_not_join_baseline(self):
        for day in range(7):
            for minute in range(30):
                p = verified_packet()
                p['vitals']['wrist_skin_temperature_status'] = 'low_quality'
                p['vitals']['wrist_skin_temperature_c'] = None
                p['vitals']['wrist_skin_temperature_raw'] = None
                p['vitals']['wrist_skin_temperature_timestamp_ms'] = None
                p['vitals']['fever_screening']['input']['quality'] = 'low_quality'
                self.store.record(p, now=self.start + day * DAY + minute * 60)
        result = self.baseline.summary('RPM-NODE-01', now=self.start + 7 * DAY,
                                       force=True)
        self.assertEqual(result['ready_metrics'], 3)
        self.assertEqual(
            result['metrics']['wrist_skin_temperature']['status'], 'waiting')
        self.assertIsNone(result['metrics']['wrist_skin_temperature']['model'])


if __name__ == '__main__':
    unittest.main()
