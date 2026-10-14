import copy
import json
import time
import unittest
from unittest.mock import patch
import telemetry_bridge as bridge
from ai_decision_engine import evaluate_clinical_status

PACKET = dict(device_id='test-node', uptime_s=1, schema_version=2,
    sensors=dict(oled=True, max=True, mlx=True, mpu=True, active=4),
    vitals=dict(heart_rate=None, spo2=None, finger_on=False, temp_object=0.0,
                temp_amb=-5.0, temp_core=None, motion_g=0.0, steps=0),
    alerts=dict(sos=False, fall=False))

class TelemetryTests(unittest.TestCase):
    def test_parser_preserves_missing_and_real_zero_values(self):
        self.assertEqual(bridge.parse_packet('[JSON] ' + json.dumps(PACKET)), PACKET)

    def test_rejects_nontelemetry_and_nonfinite_values(self):
        for text in ['boot message', '{}', '[JSON] []', '{"device_id":"x","vitals": []}']:
            self.assertIsNone(bridge.parse_packet(text))
        for value in [float('nan'), float('inf'), '72', True]:
            p = copy.deepcopy(PACKET)
            p['vitals']['heart_rate'] = value
            self.assertIsNone(bridge.parse_packet(json.dumps(p)))

    def test_stale_packet_is_not_replayed_to_new_browser(self):
        with patch.object(bridge, 'latest_telemetry', PACKET), patch.object(bridge, 'last_packet_time', time.monotonic()-6), patch.dict(bridge.hardware_status, connected=True):
            state = bridge.snapshot()
            self.assertIsNone(state['telemetry'])
            self.assertFalse(state['status']['connected'])

    def test_missing_vitals_are_not_normal(self):
        summary = evaluate_clinical_status(PACKET)
        self.assertTrue(summary['overall_status'].startswith('UNKNOWN'))
        self.assertEqual(summary['patient_metrics']['motion_g'], 0.0)
        self.assertEqual(summary['patient_metrics']['core_temp_c'], 'NOT MEASURED')

    def test_sos_survives_missing_vitals(self):
        p = copy.deepcopy(PACKET)
        p['alerts']['sos'] = True
        self.assertEqual(evaluate_clinical_status(p)['overall_status'], 'RED (EMERGENCY)')

    def test_sensor_offline_masks_old_values(self):
        p = copy.deepcopy(PACKET)
        p['sensors']['max'] = False
        p['vitals'].update(finger_on=True, heart_rate=72, spo2=98)
        result = evaluate_clinical_status(p)
        self.assertEqual(result['patient_metrics']['heart_rate_bpm'], 'UNAVAILABLE')

if __name__ == '__main__':
    unittest.main()
