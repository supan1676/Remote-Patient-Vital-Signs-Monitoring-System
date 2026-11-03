import unittest
from pathlib import Path

HEADER = (Path(__file__).resolve().parents[1] / 'src' / 'tmp117_protocol.h').read_text(
    encoding='utf-8')


def celsius(raw):
    signed = raw - 0x10000 if raw & 0x8000 else raw
    return signed * 0.0078125


class Tmp117VectorTests(unittest.TestCase):
    def test_datasheet_conversion_vectors(self):
        vectors = {
            0x0000: 0.0,
            0x0001: 0.0078125,
            0xFFFF: -0.0078125,
            0x8000: -256.0,
            0x7FFF: 255.9921875,
            0x0ED3: 29.6484375,
            0x012C: 2.34375,
            0xFF00: -2.0,
        }
        for raw, expected in vectors.items():
            self.assertAlmostEqual(celsius(raw), expected, places=7, msg=hex(raw))

    def test_the_minus_point_zero_one_anomaly_is_all_ones_hypothesis(self):
        # 0xFFFF converts to -0.0078125 C, which a two-decimal display shows as
        # -0.01 C. This is why it must be rejected rather than accepted as a
        # real near-zero temperature.
        self.assertAlmostEqual(celsius(0xFFFF), -0.0078125)
        self.assertEqual(round(celsius(0xFFFF), 2), -0.01)

    def test_header_encodes_scale_and_compile_time_checks(self):
        self.assertIn('LSB_C = 0.0078125f', HEADER)
        self.assertIn('DEVICE_ID_TMP117 = 0x0117', HEADER)
        self.assertIn('CONFIG_CONTINUOUS_8AVG_500MS = 0x01A0', HEADER)
        self.assertIn('static_assert(celsiusFromRawCode(0x0ED3) == 29.6484375f',
                      HEADER)
        self.assertIn('static_assert(celsiusFromRawCode(0xFFFF) == -0.0078125f',
                      HEADER)
        self.assertIn('0xFFFF must convert to -0.0078125 C, not +0.0078125 C',
                      HEADER)
        self.assertIn('isStuckBusPattern(0xFFFF)', HEADER)
        self.assertIn('isStuckBusPattern(0x0000)', HEADER)

    def test_big_endian_byte_order(self):
        self.assertIn('wordFromBigEndianBytes', HEADER)
        self.assertRegex(HEADER,
                         r'\(static_cast<uint16_t>\(msb\) << 8\) \| lsb')


class SensorMathHeaderTests(unittest.TestCase):
    def test_mpu_scales_and_max_quality_checks_are_compile_time(self):
        header = (Path(__file__).resolve().parents[1] / 'src' / 'sensor_math.h')
        text = header.read_text(encoding='utf-8')
        self.assertIn('MPU_ACCEL_LSB_PER_G = 4096.0f', text)
        self.assertIn('MPU_GYRO_LSB_PER_DPS = 131.0f', text)
        self.assertIn('static_assert(accelRawToG(4096) == 1.0f', text)
        self.assertIn('static_assert(gyroRawToDps(131) == 1.0f', text)
        self.assertIn('static_assert(maxSignalQuality(70000.0f, 1500.0f, 2.0f)',
                      text)
        self.assertIn('static_assert(!maxSignalQuality(40000.0f', text)
        self.assertIn('static_assert(!maxSignalQuality(70000.0f, 500.0f', text)
        self.assertIn('static_assert(!maxSignalQuality(70000.0f, 1500.0f, 0.05f)',
                      text)
        self.assertIn('static_assert(opticalWindowIsWarming(99, false)',
                      text)
        self.assertIn('static_assert(!opticalWindowIsWarming(99, true)',
                      text)


if __name__ == '__main__':
    unittest.main()
