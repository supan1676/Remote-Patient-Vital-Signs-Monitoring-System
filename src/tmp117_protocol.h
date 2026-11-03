#pragma once

#include <stdint.h>

// Pure TMP117 protocol definitions and conversion helpers.
//
// Source: Texas Instruments TMP117 datasheet (SNOSD82D, revised September
// 2022), section 7.6. The temperature result register (0x00) is a signed
// 16-bit, big-endian value with one LSB equal to 7.8125 m degC.
// The device identification register (0x0F) reads 0x0117.
namespace tmp117 {

constexpr uint8_t REG_TEMPERATURE = 0x00;
constexpr uint8_t REG_CONFIGURATION = 0x01;
constexpr uint8_t REG_T_HIGH_LIMIT = 0x02;
constexpr uint8_t REG_T_LOW_LIMIT = 0x03;
constexpr uint8_t REG_TEMPERATURE_OFFSET = 0x07;
constexpr uint8_t REG_DEVICE_ID = 0x0F;

constexpr uint16_t DEVICE_ID_TMP117 = 0x0117;
constexpr float LSB_C = 0.0078125f;
constexpr float MIN_SENSOR_C = -55.0f;
constexpr float MAX_SENSOR_C = 150.0f;

// Configuration: continuous conversion (MOD=00), 500 ms conversion cycle
// (CONV=011), and eight-sample averaging (AVG=01). Bits 15..13 are read-only
// status; writing zero to them is ignored by the device. This is the same
// measurement mode previously requested from the Adafruit library, but it is
// applied with checked writes and no unbounded wait loop.
constexpr uint16_t CONFIG_CONTINUOUS_8AVG_500MS = 0x01A0;
constexpr uint16_t CONFIG_WRITABLE_MASK = 0x0FE0;
constexpr uint16_t CONFIG_DATA_READY_MASK = 0x2000;
constexpr uint16_t CONFIG_EEPROM_BUSY_MASK = 0x1000;

constexpr uint16_t wordFromBigEndianBytes(uint8_t msb, uint8_t lsb) {
    return static_cast<uint16_t>((static_cast<uint16_t>(msb) << 8) | lsb);
}

constexpr int16_t signedTemperatureCode(uint16_t raw) {
    return static_cast<int16_t>(raw);
}

constexpr float celsiusFromRawCode(uint16_t raw) {
    // int16_t conversion is required: the high bit is the sign.
    return static_cast<float>(static_cast<int16_t>(raw)) * LSB_C;
}

constexpr bool isStuckBusPattern(uint16_t raw) {
    // 0xFFFF and 0x0000 are the canonical all-ones / all-zeros patterns seen
    // when an I2C bus is released, mis-addressed, or read incompletely. They
    // are rejected as bus faults rather than accepted as a real near-zero
    // measurement.
    return raw == 0xFFFF || raw == 0x0000;
}

constexpr bool isWithinSensorRange(float celsius) {
    return celsius >= MIN_SENSOR_C && celsius <= MAX_SENSOR_C;
}

// Compile-time conversion/register vectors checked by every firmware build.
static_assert(wordFromBigEndianBytes(0x0E, 0xD3) == 0x0ED3, "big-endian byte order");
static_assert(signedTemperatureCode(0xFFFF) == -1, "0xFFFF is signed -1");
static_assert(signedTemperatureCode(0x8000) == -32768, "0x8000 is signed -32768");
static_assert(celsiusFromRawCode(0x0000) == 0.0f, "0x0000 is 0 C");
static_assert(celsiusFromRawCode(0xFFFF) == -0.0078125f,
              "0xFFFF must convert to -0.0078125 C, not +0.0078125 C");
static_assert(celsiusFromRawCode(0x0ED3) == 29.6484375f,
              "0x0ED3 must convert to 29.6484375 C");
static_assert(celsiusFromRawCode(0x7FFF) == 255.9921875f,
              "0x7FFF positive full-scale conversion");
static_assert(celsiusFromRawCode(0x8000) == -256.0f,
              "0x8000 negative full-scale conversion");
static_assert(isStuckBusPattern(0xFFFF), "all-ones must be flagged");
static_assert(isStuckBusPattern(0x0000), "all-zeros must be flagged");
static_assert(!isStuckBusPattern(0x0ED3), "normal reading must not be flagged");
static_assert(isWithinSensorRange(-55.0f) && isWithinSensorRange(150.0f),
              "datasheet sensor range boundaries");
static_assert(!isWithinSensorRange(-55.1f) && !isWithinSensorRange(150.1f),
              "outside datasheet range must be rejected");

}  // namespace tmp117
