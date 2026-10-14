import unittest
from personal_baseline import PersonalBaseline, DAY
from telemetry_store import TelemetryStore


def packet(hr=70, device='board-a'):
    return dict(device_id=device,uptime_s=1,
        sensors=dict(max=True,mlx=False,mpu=True), alerts=dict(sos=False,fall=False),
        vitals=dict(heart_rate=hr,spo2=98,temp_object=None,motion_g=1.02,
                    finger_on=True,raw_ir=70000,raw_red=68000))

class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.store=TelemetryStore(':memory:')
        self.baseline=PersonalBaseline(self.store)
        self.start=100000
        self.baseline.start('board-a','A person',now=self.start)

    def tearDown(self): self.store.close()

    def populate(self,days=7):
        for day in range(days):
            for minute in range(30):
                self.store.record(packet(),now=self.start+day*DAY+minute*60)

    def test_seven_days_without_measurements_is_not_ready(self):
        result=self.baseline.summary('board-a',now=self.start+7*DAY,force=True)
        self.assertEqual(result['ready_metrics'],0)
        self.assertEqual(result['metrics']['heart_rate']['status'],'waiting')

    def test_coverage_and_elapsed_time_both_required(self):
        self.populate()
        result=self.baseline.summary('board-a',now=self.start+6*DAY+2000,force=True)
        self.assertEqual(result['ready_metrics'],0)
        result=self.baseline.summary('board-a',now=self.start+7*DAY,force=True)
        self.assertEqual(result['ready_metrics'],3)
        self.assertEqual(result['status'],'partial')
        self.assertIsNone(result['metrics']['temp_object']['model'])

    def test_short_bursts_do_not_count_as_days(self):
        for day in range(7):
            for second in range(40): self.store.record(packet(),now=self.start+day*DAY+second)
        result=self.baseline.summary('board-a',now=self.start+7*DAY,force=True)
        self.assertEqual(result['metrics']['heart_rate']['qualified_days'],0)

    def test_model_freezes_and_events_require_sustained_departure(self):
        self.populate()
        now=self.start+7*DAY
        first=self.baseline.summary('board-a',now=now,force=True)['metrics']['heart_rate']['model']
        self.assertEqual(first['center'],70)
        for offset in range(2): self.baseline.compare(packet(100),now=now+offset)
        self.assertFalse(any(e['kind']=='deviation' for e in self.baseline.events('board-a')))
        self.baseline.compare(packet(100),now=now+2)
        self.assertEqual(sum(e['kind']=='deviation' for e in self.baseline.events('board-a')),1)
        self.store.record(packet(200),now=now+3)
        second=self.baseline.summary('board-a',now=now+4,force=True)['metrics']['heart_rate']['model']
        self.assertEqual(first,second)

    def test_new_wearer_does_not_inherit_reference(self):
        self.populate()
        self.baseline.summary('board-a',now=self.start+7*DAY,force=True)
        self.baseline.end('board-a')
        result=self.baseline.start('board-a','Someone else',now=self.start+8*DAY)
        self.assertEqual(result['ready_metrics'],0)
        self.assertEqual(result['metrics']['heart_rate']['valid_minutes'],0)

    def test_other_device_and_duplicate_enrollment(self):
        self.assertEqual(self.baseline.summary('board-b',now=self.start)['status'],'not_started')
        with self.assertRaises(ValueError): self.baseline.start('board-a','Different wearer',now=self.start)

if __name__=='__main__': unittest.main()
