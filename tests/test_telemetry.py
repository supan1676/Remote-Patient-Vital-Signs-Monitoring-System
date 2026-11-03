import copy
import json
import time
import unittest
from unittest.mock import patch

import telemetry_bridge as bridge
from ai_decision_engine import evaluate_clinical_status
from fixtures import packet, verified_packet
from temperature_safety import FEVER_MESSAGE


class TelemetryTests(unittest.TestCase):
    def test_high_optical_perfusion_does_not_drop_valid_vitals_or_sos(self):
        p = packet(optical_perfusion_index=25.0)
        p['alerts']['sos'] = True
        parsed = bridge.parse_packet(json.dumps(p))
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed['vitals']['heart_rate'], 72)
        self.assertEqual(parsed['vitals']['spo2'], 98)
        self.assertTrue(parsed['alerts']['sos'])

    def test_optical_perfusion_still_rejects_invalid_ratios(self):
        for value in (-0.1, 10_001, float('inf'), '25', True):
            with self.subTest(value=value):
                self.assertIsNone(bridge.parse_packet(json.dumps(
                    packet(optical_perfusion_index=value))))

    def test_parser_accepts_complete_contract(self):
        p = packet()
        parsed = bridge.parse_packet('[JSON] ' + json.dumps(p))
        self.assertEqual(parsed, p)
        verified = verified_packet()
        self.assertEqual(bridge.parse_packet(json.dumps(verified)), verified)

    def test_rejects_nontelemetry_and_nonfinite_values(self):
        for text in ['boot message', '{}', '[JSON] []',
                     '{"device_id":"x","vitals": []}']:
            self.assertIsNone(bridge.parse_packet(text))
        for value in [float('nan'), float('inf'), '72', True]:
            p = copy.deepcopy(packet())
            p['vitals']['heart_rate'] = value
            self.assertIsNone(bridge.parse_packet(json.dumps(p)))

    def test_rejects_wrong_schema_and_active_count(self):
        p = copy.deepcopy(packet())
        p['schema_version'] = 1
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))
        p = copy.deepcopy(packet())
        p['sensors']['active'] = 2
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))
        p = copy.deepcopy(packet())
        p['sensors']['active_max'] = 4
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))

    def test_rejects_contradictory_status_and_value(self):
        for key, status_key in [
                ('heart_rate', 'heart_rate_status'),
                ('motion_g', 'motion_status')]:
            p = copy.deepcopy(packet())
            p['vitals'][key] = None
            p['vitals'][status_key] = 'valid'
            self.assertIsNone(bridge.parse_packet(json.dumps(p)), key)
        p = copy.deepcopy(packet())
        p['vitals']['wrist_contact_status'] = 'verified'
        p['vitals']['wrist_skin_temperature_status'] = 'low_quality'
        p['vitals']['wrist_skin_temperature_c'] = 29.6
        p['vitals']['wrist_skin_temperature_raw'] = 3795
        p['vitals']['wrist_skin_temperature_timestamp_ms'] = 5000
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))

    def test_rejects_any_core_temperature_or_enabled_screening(self):
        p = copy.deepcopy(packet())
        p['vitals']['estimated_core_temperature_c'] = 37.0
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))
        p = copy.deepcopy(packet())
        p['vitals']['estimated_core_temperature_status'] = 'valid'
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))
        p = copy.deepcopy(packet())
        p['vitals']['fever_screening']['status'] = 'fever'
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))
        p = copy.deepcopy(packet())
        p['vitals']['fever_screening']['screening_supported'] = True
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))
        p = copy.deepcopy(packet())
        p['vitals']['fever_screening']['message'] = 'Fever detected.'
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))

    def test_rejects_stuck_bus_temperature_even_if_marked_valid(self):
        p = copy.deepcopy(packet())
        p['vitals']['tmp117_sensor_temperature_raw'] = 0xFFFF
        p['vitals']['tmp117_sensor_temperature_c'] = -0.0078125
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))
        p['vitals']['tmp117_sensor_temperature_raw'] = 0x0000
        p['vitals']['tmp117_sensor_temperature_c'] = 0.0
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))

        p = verified_packet()
        p['vitals']['wrist_skin_temperature_raw'] = 0xFFFF
        p['vitals']['wrist_skin_temperature_c'] = -0.0078125
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))

    def test_rejects_nan_in_nested_unknown_fields(self):
        p = copy.deepcopy(packet())
        p['vitals']['acceleration']['x_g'] = float('nan')
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))

    def test_rejects_uninstalled_optional_sensors_and_fever_rules(self):
        for key in ('sht40', 'mlx'):
            p = copy.deepcopy(packet())
            p['sensors'][key] = True
            self.assertIsNone(bridge.parse_packet(json.dumps(p)))
        p = copy.deepcopy(packet())
        p['vitals']['fever_screening']['rule'] = 'fixed_offset'
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))
        p = copy.deepcopy(packet())
        p['vitals']['fever_screening']['input']['quality'] = 'low_quality'
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))

    def test_rejects_fever_input_that_contradicts_the_wrist_observation(self):
        p = copy.deepcopy(packet())
        p['vitals']['fever_screening']['input']['quality'] = 'stale'
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))

        p = copy.deepcopy(packet())
        p['vitals']['fever_screening']['input']['value_c'] = 30.0
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))

        p = copy.deepcopy(packet())
        p['vitals']['fever_screening']['input']['timestamp_ms'] = 6000
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))

        p = copy.deepcopy(packet())
        p['vitals']['fever_screening']['input'].update(
            measured=True, value_c=29.6484375, timestamp_ms=5000,
            raw_register=3795)
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))

        p = verified_packet()
        p['vitals']['fever_screening']['input']['raw_register'] = 0x0F00
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))

        p = verified_packet()
        p['vitals']['fever_screening']['input'].update(
            measured=False, value_c=None, timestamp_ms=None, raw_register=None)
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))

    def test_rejects_raw_temperature_that_does_not_match_the_value(self):
        p = copy.deepcopy(packet())
        p['vitals']['tmp117_sensor_temperature_c'] = 30.0
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))
        p = copy.deepcopy(packet())
        p['vitals']['tmp117_sensor_temperature_raw'] = 0x0F00
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))

    def test_rejects_valid_actual_temperature_without_raw_or_timestamp(self):
        for key in ('tmp117_sensor_temperature_raw',
                    'tmp117_sensor_temperature_timestamp_ms'):
            p = copy.deepcopy(packet())
            p['vitals'][key] = None
            self.assertIsNone(bridge.parse_packet(json.dumps(p)), key)

    def test_rejects_offline_sensor_with_valid_status(self):
        p = copy.deepcopy(packet())
        p['sensors']['tmp117'] = False
        p['sensors']['active'] = 2
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))

    def test_actual_sensor_status_cannot_be_contact_unverified(self):
        p = copy.deepcopy(packet())
        p['vitals'].update(
            tmp117_sensor_temperature_c=None,
            tmp117_sensor_temperature_status='unverified',
            tmp117_sensor_temperature_raw=None,
            tmp117_sensor_temperature_timestamp_ms=None,
        )
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))

    def test_actual_sensor_outside_clinical_range_is_valid(self):
        p = copy.deepcopy(packet())
        p['vitals'].update(
            tmp117_sensor_temperature_c=70.0,
            tmp117_sensor_temperature_raw=0x2300,
            tmp117_sensor_temperature_timestamp_ms=6000,
        )
        self.assertIsNotNone(bridge.parse_packet(json.dumps(p)))
        self.assertIsNone(p['vitals']['wrist_skin_temperature_c'])

    def test_unverified_contact_rejects_non_null_wrist_data(self):
        p = copy.deepcopy(packet())
        p['vitals'].update(
            wrist_skin_temperature_c=29.6484375,
            wrist_skin_temperature_status='valid',
            wrist_skin_temperature_raw=3795,
            wrist_skin_temperature_timestamp_ms=5000,
        )
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))

    def test_verified_wrist_requires_matching_actual_reading(self):
        p = verified_packet()
        self.assertIsNotNone(bridge.parse_packet(json.dumps(p)))
        p['vitals']['tmp117_sensor_temperature_raw'] = 0x0F00
        p['vitals']['tmp117_sensor_temperature_c'] = 30.0
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))
        p = verified_packet()
        p['vitals']['tmp117_sensor_temperature_timestamp_ms'] = 6000
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))

    def test_rejects_duplicate_temperature_keys(self):
        p = packet()
        text = json.dumps(p, separators=(',', ':'))
        key = '"tmp117_sensor_temperature_c":29.6484375'
        self.assertIn(key, text)
        text = text.replace(
            key,
            key + ',"tmp117_sensor_temperature_c":0.0',
            1,
        )
        self.assertIsNone(bridge.parse_packet(text))

    def test_non_null_legacy_temperature_alias_is_rejected(self):
        p = copy.deepcopy(packet())
        p['vitals']['tmp117_temp_c'] = 29.6484375
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))
        p['vitals']['tmp117_temp_c'] = None
        self.assertIsNotNone(bridge.parse_packet(json.dumps(p)))

    def test_optional_legacy_modules_are_rejected_in_the_active_build(self):
        for key in ('sht40', 'mlx'):
            p = copy.deepcopy(packet())
            p['sensors'][key] = True
            self.assertIsNone(bridge.parse_packet(json.dumps(p)))
        self.assertEqual(packet()['sensors']['active'], 3)
        self.assertEqual(packet()['sensors']['active_max'], 3)

    def test_duplicate_suppressor_ignores_immediate_repeat_only(self):
        gate = bridge.DuplicateSuppressor(window=1.5)
        self.assertFalse(gate.duplicate('same', now=10.0))
        self.assertTrue(gate.duplicate('same', now=10.5))
        self.assertFalse(gate.duplicate('same', now=12.0))

    def test_stale_packet_is_not_replayed_to_new_browser(self):
        with patch.object(bridge, 'latest_telemetry', packet()), \
                patch.object(bridge, 'last_packet_time', time.monotonic() - 6), \
                patch.dict(bridge.hardware_status, connected=True):
            state = bridge.snapshot()
            self.assertIsNone(state['telemetry'])
            self.assertFalse(state['status']['connected'])

    def test_temperature_semantics_are_sensor_plus_unverified_wrist(self):
        summary = evaluate_clinical_status(packet())
        metrics = summary['patient_metrics']
        self.assertEqual(metrics['wrist_skin_temperature_c'], 'UNAVAILABLE')
        self.assertEqual(metrics['wrist_skin_temperature_status'], 'unverified')
        self.assertEqual(metrics['wrist_contact_status'], 'unverified')
        self.assertAlmostEqual(metrics['tmp117_sensor_temperature_c'], 29.6484375)
        self.assertEqual(metrics['tmp117_sensor_temperature_status'], 'valid')
        self.assertIsNone(metrics['estimated_core_temperature_c'])
        self.assertEqual(metrics['estimated_core_temperature_status'], 'not_available')
        self.assertEqual(metrics['fever_screening_status'], 'not_available')
        self.assertEqual(metrics['fever_screening_message'], FEVER_MESSAGE)
        self.assertIn(FEVER_MESSAGE, summary['findings'])
        self.assertTrue(any(finding.startswith('Wrist skin temperature is unavailable')
                            for finding in summary['findings']))
        self.assertNotIn('core_temp_c', metrics)
        self.assertEqual(summary['overall_status'], 'GREEN (NO OPTICAL ALERT)')

    def test_verified_wrist_semantics_remain_core_unavailable(self):
        summary = evaluate_clinical_status(verified_packet())
        metrics = summary['patient_metrics']
        self.assertAlmostEqual(metrics['wrist_skin_temperature_c'], 29.6484375)
        self.assertEqual(metrics['wrist_skin_temperature_status'], 'valid')
        self.assertEqual(metrics['wrist_contact_status'], 'verified')
        self.assertIsNone(metrics['estimated_core_temperature_c'])
        self.assertEqual(metrics['fever_screening_status'], 'not_available')

    def test_low_quality_wrist_value_is_not_used(self):
        p = verified_packet()
        p['vitals'].update(wrist_skin_temperature_c=None,
                           wrist_skin_temperature_status='low_quality',
                           wrist_skin_temperature_raw=None,
                           wrist_skin_temperature_timestamp_ms=None)
        summary = evaluate_clinical_status(p)
        self.assertEqual(summary['patient_metrics']['wrist_skin_temperature_c'],
                         'UNAVAILABLE')
        self.assertEqual(summary['patient_metrics']['wrist_skin_temperature_status'],
                         'low_quality')
        self.assertIn(FEVER_MESSAGE, summary['findings'])

    def test_optical_sensor_offline_masks_old_values(self):
        p = copy.deepcopy(packet())
        p['sensors']['max'] = False
        p['sensors']['active'] = 2
        p['vitals'].update(finger_on=True, heart_rate=72, spo2=98)
        # The whole packet is rejected because max is offline while its status
        # still says valid; direct engine masking is tested below.
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))
        p['vitals'].update(heart_rate=None, heart_rate_status='not_available',
                           spo2=None, spo2_status='not_available')
        p['vitals']['finger_on'] = False
        self.assertIsNotNone(bridge.parse_packet(json.dumps(p)))
        result = evaluate_clinical_status(p)
        self.assertEqual(result['patient_metrics']['heart_rate_bpm'], 'UNAVAILABLE')
        self.assertEqual(result['patient_metrics']['hardware_health'].split()[0], '2/3')

    def test_absent_legacy_mlx_and_sht40_are_not_inventoried(self):
        p = copy.deepcopy(packet())
        p['vitals'].update(temp_object=99.0, temp_skin=99.0, temp_amb=42.0,
                           sht40_temp_c=24.1, sht40_humidity_pct=45.2)
        self.assertIsNone(bridge.parse_packet(json.dumps(p)))
        result = evaluate_clinical_status(p)
        self.assertEqual(result['patient_metrics']['surface_temp_c'], 'UNAVAILABLE')
        self.assertEqual(result['patient_metrics']['sht40_temp_c'], 'UNAVAILABLE')
        self.assertIn('3/3 measurement sensors online',
                      result['patient_metrics']['hardware_health'])
        self.assertFalse(any('MLX90614' in finding for finding in result['findings']))
        self.assertFalse(any('SHT40' in finding for finding in result['findings']))

    def test_sos_survives_missing_vitals(self):
        p = copy.deepcopy(packet())
        p['alerts']['sos'] = True
        self.assertEqual(evaluate_clinical_status(p)['overall_status'],
                         'RED (EMERGENCY)')

    def test_missing_vitals_are_not_normal(self):
        p = copy.deepcopy(packet())
        p['sensors'].update(max=False, mpu=False, tmp117=False, active=0)
        p['vitals'].update(
            heart_rate=None, heart_rate_status='not_available',
            spo2=None, spo2_status='not_available', finger_on=False,
            tmp117_sensor_temperature_c=None,
            tmp117_sensor_temperature_status='not_available',
            tmp117_sensor_temperature_raw=None,
            tmp117_sensor_temperature_timestamp_ms=None,
            wrist_skin_temperature_c=None,
            wrist_skin_temperature_status='unverified',
            wrist_skin_temperature_raw=None,
            wrist_skin_temperature_timestamp_ms=None,
            wrist_contact_status='unverified',
            motion_g=None, motion_status='not_available')
        self.assertIsNotNone(bridge.parse_packet(json.dumps(p)))
        result = evaluate_clinical_status(p)
        self.assertTrue(result['overall_status'].startswith('UNKNOWN'))
        self.assertEqual(result['patient_metrics']['motion_g'], 'UNAVAILABLE')
        self.assertIsNone(result['patient_metrics']['estimated_core_temperature_c'])

    def test_fever_message_is_exact(self):
        self.assertEqual(FEVER_MESSAGE,
                         'Core temperature unavailable — confirmation required')


if __name__ == '__main__':
    unittest.main()
