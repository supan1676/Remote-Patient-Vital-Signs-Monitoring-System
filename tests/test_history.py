import tempfile
import unittest
from pathlib import Path
from telemetry_store import TelemetryStore, measurements


def packet(device='board-a', **overrides):
    return dict(device_id=device, uptime_s=1,
        sensors=dict(max=True,mlx=True,mpu=True), alerts=dict(sos=False,fall=False),
        vitals=dict(heart_rate=70,spo2=98,temp_object=0,motion_g=0,
                    finger_on=True,raw_ir=70000,raw_red=68000,**overrides))

class HistoryTests(unittest.TestCase):
    def test_missing_is_not_zero_and_zero_is_not_missing(self):
        p=packet()
        self.assertEqual(measurements(p)['temp_object'],0)
        self.assertEqual(measurements(p)['motion_g'],0)
        p['sensors']['mlx']=False
        p['vitals']['finger_on']=False
        self.assertIsNone(measurements(p)['temp_object'])
        self.assertIsNone(measurements(p)['heart_rate'])

    def test_persistence_and_device_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            file=Path(directory)/'telemetry.sqlite3'
            store=TelemetryStore(file)
            store.record(packet(),now=10000)
            store.record(packet('board-b'),now=10001)
            store.close()
            store=TelemetryStore(file)
            history=store.history('board-a',60,now=10002)
            self.assertEqual(sum(p['samples'] for p in history['points']),1)
            self.assertEqual([p['heart_rate'] for p in history['points'] if p['samples']],[70])
            store.close()

    def test_history_keeps_disconnect_gaps(self):
        store=TelemetryStore(':memory:')
        store.record(packet(),now=10000)
        store.record(packet(),now=10010)
        rows=store.history('board-a',60,now=10010)['points']
        self.assertTrue(any(p['samples']==0 and p['motion_g'] is None for p in rows))
        store.close()

if __name__=='__main__': unittest.main()
