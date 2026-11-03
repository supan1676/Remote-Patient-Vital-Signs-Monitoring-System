import copy
import unittest

from fixtures import FEVER_MESSAGE, packet, verified_packet
from temperature_safety import evaluate_temperature_safety


class TemperatureSafetyTests(unittest.TestCase):
    def test_actual_sensor_is_separate_from_unverified_wrist_contact(self):
        result = evaluate_temperature_safety(packet())
        self.assertAlmostEqual(result['tmp117_sensor_temperature_c'], 29.6484375)
        self.assertEqual(result['tmp117_sensor_temperature_status'], 'valid')
        self.assertEqual(result['tmp117_sensor_temperature_raw'], 3795)
        self.assertEqual(result['tmp117_sensor_temperature_timestamp_ms'], 5000)
        self.assertEqual(result['wrist_contact_status'], 'unverified')
        self.assertIsNone(result['wrist_skin_temperature_c'])
        self.assertEqual(result['wrist_skin_temperature_status'], 'unverified')
        self.assertIsNone(result['wrist_skin_temperature_raw'])
        self.assertIsNone(result['wrist_skin_temperature_timestamp_ms'])
        self.assertIsNone(result['estimated_core_temperature_c'])
        self.assertEqual(result['estimated_core_temperature_status'], 'not_available')
        fever = result['fever_screening']
        self.assertEqual(fever['status'], 'not_available')
        self.assertEqual(fever['message'], FEVER_MESSAGE)
        self.assertIsNone(fever['rule'])
        self.assertFalse(fever['screening_supported'])
        self.assertEqual(fever['input']['measurement'], 'wrist_skin_temperature')
        self.assertEqual(fever['input']['quality'], 'unverified')
        self.assertFalse(fever['input']['measured'])
        self.assertIsNone(fever['input']['value_c'])
        self.assertIsNone(fever['input']['timestamp_ms'])
        self.assertIsNone(fever['input']['raw_register'])
        self.assertIn('limitations', fever)
        self.assertIn('uncertainty', fever)

    def test_actual_sensor_accepts_values_outside_clinical_wrist_range(self):
        p = copy.deepcopy(packet())
        p['vitals'].update(
            tmp117_sensor_temperature_c=70.0,
            tmp117_sensor_temperature_raw=0x2300,
            tmp117_sensor_temperature_timestamp_ms=6000,
        )
        result = evaluate_temperature_safety(p)
        self.assertAlmostEqual(result['tmp117_sensor_temperature_c'], 70.0)
        self.assertEqual(result['tmp117_sensor_temperature_status'], 'valid')
        self.assertEqual(result['tmp117_sensor_temperature_raw'], 0x2300)
        self.assertIsNone(result['wrist_skin_temperature_c'])
        self.assertEqual(result['wrist_contact_status'], 'unverified')

    def test_actual_sensor_outside_hardware_range_is_rejected(self):
        p = copy.deepcopy(packet())
        p['vitals']['tmp117_sensor_temperature_c'] = 160.0
        p['vitals']['tmp117_sensor_temperature_raw'] = 0x5000
        result = evaluate_temperature_safety(p)
        self.assertIsNone(result['tmp117_sensor_temperature_c'])
        self.assertEqual(result['tmp117_sensor_temperature_status'], 'sensor_error')
        self.assertIsNone(result['tmp117_sensor_temperature_raw'])
        self.assertIsNone(result['tmp117_sensor_temperature_timestamp_ms'])

    def test_valid_actual_sensor_requires_raw_timestamp_and_conversion(self):
        for overrides in (
            {'tmp117_sensor_temperature_raw': None},
            {'tmp117_sensor_temperature_timestamp_ms': None},
            {'tmp117_sensor_temperature_raw': 0x0F00},
            {'tmp117_sensor_temperature_raw': 0x0000},
            {'tmp117_sensor_temperature_raw': 0xFFFF,
             'tmp117_sensor_temperature_c': -0.0078125},
        ):
            p = copy.deepcopy(packet())
            p['vitals'].update(overrides)
            result = evaluate_temperature_safety(p)
            self.assertIsNone(result['tmp117_sensor_temperature_c'], overrides)
            self.assertEqual(result['tmp117_sensor_temperature_status'],
                             'sensor_error', overrides)
            self.assertIsNone(result['tmp117_sensor_temperature_raw'], overrides)
            self.assertIsNone(result['tmp117_sensor_temperature_timestamp_ms'],
                             overrides)

    def test_invalid_actual_sensor_status_never_leaves_stale_evidence(self):
        for status in ('warming_up', 'low_quality', 'stale', 'sensor_error',
                       'not_available', 'unverified'):
            p = copy.deepcopy(packet())
            p['vitals']['tmp117_sensor_temperature_status'] = status
            result = evaluate_temperature_safety(p)
            self.assertIsNone(result['tmp117_sensor_temperature_c'], status)
            self.assertIsNone(result['tmp117_sensor_temperature_raw'], status)
            self.assertIsNone(result['tmp117_sensor_temperature_timestamp_ms'],
                             status)
            self.assertIsNone(result['wrist_skin_temperature_c'], status)

    def test_offline_sensor_masks_actual_and_clinical_values(self):
        p = copy.deepcopy(packet())
        p['sensors']['tmp117'] = False
        result = evaluate_temperature_safety(p)
        self.assertIsNone(result['tmp117_sensor_temperature_c'])
        self.assertEqual(result['tmp117_sensor_temperature_status'], 'not_available')
        self.assertIsNone(result['wrist_skin_temperature_c'])
        self.assertEqual(result['wrist_contact_status'], 'unverified')

    def test_verified_contact_requires_consistent_raw_evidence(self):
        result = evaluate_temperature_safety(verified_packet())
        self.assertAlmostEqual(result['wrist_skin_temperature_c'], 29.6484375)
        self.assertEqual(result['wrist_skin_temperature_status'], 'valid')
        self.assertEqual(result['wrist_skin_temperature_raw'], 3795)
        self.assertEqual(result['wrist_skin_temperature_timestamp_ms'], 5000)
        self.assertTrue(result['fever_screening']['input']['measured'])
        self.assertEqual(result['fever_screening']['input']['raw_register'], 3795)

        for overrides in (
            {'wrist_skin_temperature_raw': None},
            {'wrist_skin_temperature_raw': 0x0F00},
            {'wrist_skin_temperature_raw': 0xFFFF,
             'wrist_skin_temperature_c': -0.0078125},
            {'wrist_skin_temperature_c': 70.0},
            {'wrist_skin_temperature_timestamp_ms': 6000},
        ):
            p = verified_packet()
            p['vitals'].update(overrides)
            result = evaluate_temperature_safety(p)
            self.assertIsNone(result['wrist_skin_temperature_c'], overrides)
            self.assertEqual(result['wrist_skin_temperature_status'],
                             'sensor_error', overrides)
            self.assertFalse(result['fever_screening']['input']['measured'],
                             overrides)

    def test_verified_contact_requires_matching_actual_sensor_reading(self):
        p = verified_packet()
        p['vitals']['tmp117_sensor_temperature_raw'] = 0x0F00
        p['vitals']['tmp117_sensor_temperature_c'] = 30.0
        result = evaluate_temperature_safety(p)
        self.assertIsNone(result['wrist_skin_temperature_c'])
        self.assertEqual(result['wrist_skin_temperature_status'], 'sensor_error')
        self.assertIsNone(result['fever_screening']['input']['value_c'])

    def test_unverified_contact_masks_contradictory_wrist_data(self):
        p = copy.deepcopy(packet())
        p['vitals'].update(
            wrist_skin_temperature_c=29.6484375,
            wrist_skin_temperature_status='valid',
            wrist_skin_temperature_raw=3795,
            wrist_skin_temperature_timestamp_ms=5000,
        )
        result = evaluate_temperature_safety(p)
        self.assertIsNone(result['wrist_skin_temperature_c'])
        self.assertEqual(result['wrist_skin_temperature_status'], 'unverified')
        self.assertIsNone(result['wrist_skin_temperature_raw'])
        self.assertIsNone(result['wrist_skin_temperature_timestamp_ms'])
        self.assertFalse(result['fever_screening']['input']['measured'])

    def test_invalid_contact_status_fails_closed(self):
        for contact in ('yes', '', None, [], {}):
            p = copy.deepcopy(packet())
            p['vitals']['wrist_contact_status'] = contact
            result = evaluate_temperature_safety(p)
            self.assertEqual(result['wrist_contact_status'], 'unverified', contact)
            self.assertIsNone(result['wrist_skin_temperature_c'], contact)
            self.assertEqual(result['wrist_skin_temperature_status'],
                             'unverified', contact)

    def test_incoming_core_claim_is_ignored_and_cannot_enable_screening(self):
        p = copy.deepcopy(packet())
        p['vitals']['estimated_core_temperature_c'] = 39.2
        p['vitals']['estimated_core_temperature_status'] = 'valid'
        result = evaluate_temperature_safety(p)
        self.assertIsNone(result['estimated_core_temperature_c'])
        self.assertEqual(result['estimated_core_temperature_status'], 'not_available')
        self.assertEqual(result['fever_screening']['status'], 'not_available')

    def test_nan_and_non_numeric_are_unavailable(self):
        for value in (float('nan'), '29.6', True):
            p = copy.deepcopy(packet())
            p['vitals']['tmp117_sensor_temperature_c'] = value
            result = evaluate_temperature_safety(p)
            self.assertIsNone(result['tmp117_sensor_temperature_c'])
            self.assertEqual(result['tmp117_sensor_temperature_status'],
                             'sensor_error')


if __name__ == '__main__':
    unittest.main()
