#pragma once

#include <math.h>
#include <stdint.h>

// Pure sensor conversion and signal-quality helpers. Keeping these here makes
// the arithmetic compile-time testable without adding a second implementation.
namespace sensor_math {

// MPU-6050 configured ranges: +/-8 g and +/-250 degrees/second.
constexpr float MPU_ACCEL_LSB_PER_G = 4096.0f;
constexpr float MPU_GYRO_LSB_PER_DPS = 131.0f;

// MAX30102 contact/signal-quality guard. These are engineering thresholds,
// not clinical thresholds.
constexpr float MAX_MIN_DC = 50000.0f;
constexpr float MAX_MAX_DC = 262143.0f;
constexpr float MAX_MIN_AC = 1000.0f;
constexpr float MAX_MIN_PI = 0.10f;

constexpr float accelRawToG(int16_t raw) {
  return static_cast<float>(raw) / MPU_ACCEL_LSB_PER_G;
}

constexpr float gyroRawToDps(int16_t raw) {
  return static_cast<float>(raw) / MPU_GYRO_LSB_PER_DPS;
}

inline float magnitude3(float x, float y, float z) {
  return sqrtf(x * x + y * y + z * z);
}

inline float perfusionIndex(float minimum, float maximum, float mean) {
  if (!(mean > 0.0f)) return NAN;
  return (maximum - minimum) / mean * 100.0f;
}

constexpr bool maxSignalQuality(float mean, float ac, float pi) {
  return mean >= MAX_MIN_DC && mean < MAX_MAX_DC && ac >= MAX_MIN_AC &&
         pi >= MAX_MIN_PI;
}

// Warming is a start-up state, not a state that may overwrite a completed
// low-quality result. Once a window has produced a result, a partially filled
// next window must preserve that result until the next window is evaluated.
constexpr bool opticalWindowIsWarming(uint16_t samples, bool hasWindowResult) {
  return samples < 100 && !hasWindowResult;
}

// Compile-time vectors. They are checked by every firmware build.
static_assert(MPU_ACCEL_LSB_PER_G == 4096.0f, "accel scale must match +/-8 g");
static_assert(MPU_GYRO_LSB_PER_DPS == 131.0f, "gyro scale must match +/-250 dps");
static_assert(accelRawToG(4096) == 1.0f, "4096 counts must be 1 g");
static_assert(accelRawToG(-4096) == -1.0f, "-4096 counts must be -1 g");
static_assert(accelRawToG(2048) == 0.5f, "2048 counts must be 0.5 g");
static_assert(gyroRawToDps(131) == 1.0f, "131 counts must be 1 dps");
static_assert(gyroRawToDps(-262) == -2.0f, "-262 counts must be -2 dps");
static_assert(maxSignalQuality(70000.0f, 1500.0f, 2.0f),
              "valid optical window must pass the quality guard");
static_assert(!maxSignalQuality(40000.0f, 1500.0f, 2.0f),
              "low DC signal must fail the quality guard");
static_assert(!maxSignalQuality(70000.0f, 500.0f, 2.0f),
              "low AC signal must fail the quality guard");
static_assert(!maxSignalQuality(70000.0f, 1500.0f, 0.05f),
              "low perfusion index must fail the quality guard");
static_assert(opticalWindowIsWarming(0, false),
              "an empty first window must report warming");
static_assert(opticalWindowIsWarming(99, false),
              "a partially filled first window must report warming");
static_assert(!opticalWindowIsWarming(100, false),
              "a full first window must be evaluated");
static_assert(!opticalWindowIsWarming(0, true),
              "a completed low-quality result must not become warming");
static_assert(!opticalWindowIsWarming(99, true),
              "a partially filled later window must preserve the result");

}  // namespace sensor_math
