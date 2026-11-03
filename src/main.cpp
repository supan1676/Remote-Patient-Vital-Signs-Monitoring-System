/**
 * IoMT Patient Monitoring & Real-Time Telemetry Node
 * Target: ESP32-S3 N16R8 development board (16 MB flash, 8 MB octal PSRAM)
 *
 * Installed hardware used by this build:
 *   - SSD1306 128x64 OLED          I2C bus 0, 0x3C, SDA=8, SCL=9
 *   - TECHTONICS MAX30102           I2C bus 0, 0x57, SDA=8, SCL=9
 *   - 7SEMI TMP117 ES-12132         I2C bus 0, 0x48-0x4B, SDA=8, SCL=9
 *   - GY-521 MPU-6050/MPU-6500      I2C bus 1, 0x68/0x69, SDA=17, SCL=18
 *   - SOS pushbutton                GPIO 5 to GND, active LOW
 *
 * No SHT40 or MLX90614 is installed. Their optional legacy code paths are
 * compiled out by default and they are never counted as installed sensors.
 *
 * Temperature policy:
 *   - The TMP117 sensor temperature is reported as tmp117_sensor_temperature_c.
 *   - The clinical wrist-skin value is wrist_skin_temperature_c and requires
 *     verified wrist contact.
 *   - Contact verification is currently unverified, so wrist_skin_temperature_c
 *     remains null and fever screening remains unavailable.
 *   - No core-temperature estimate is produced.
 *   - Fever screening is unavailable until a validated core reference exists.
 */

#include <Arduino.h>
#include <Wire.h>
#include <math.h>
#include <string.h>

#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#if RPM_ENABLE_OPTIONAL_MLX90614
#include <Adafruit_MLX90614.h>
#endif
#if RPM_ENABLE_OPTIONAL_SHT40
#include <Adafruit_SHT4x.h>
#endif
#include <MAX30105.h>
#include <spo2_algorithm.h>

#include "sensor_math.h"
#include "tmp117_protocol.h"

#ifndef RPM_ENABLE_OPTIONAL_SHT40
#define RPM_ENABLE_OPTIONAL_SHT40 0
#endif
#ifndef RPM_ENABLE_OPTIONAL_MLX90614
#define RPM_ENABLE_OPTIONAL_MLX90614 0
#endif

// ---------------------------------------------------------------------------
// Wiring and timing
// ---------------------------------------------------------------------------
#define I2C_SDA_PIN       8
#define I2C_SCL_PIN       9
#define I2C_PRIMARY_HZ    50000UL

#define MPU_SDA_PIN       17
#define MPU_SCL_PIN       18
#define I2C_IMU_HZ        400000UL

#define BUTTON_PIN        5
#define SCREEN_WIDTH      128
#define SCREEN_HEIGHT     64
#define OLED_RESET        -1

constexpr uint32_t TMP117_READ_INTERVAL_MS = 2000;
constexpr uint32_t TMP117_STALE_MS = 6000;
constexpr uint32_t MPU_READ_INTERVAL_MS = 20;
constexpr uint32_t MPU_STALE_MS = 1500;
constexpr uint32_t OPTICAL_SAMPLE_GAP_MS = 150;
constexpr uint32_t OPTICAL_STALE_MS = 2000;
constexpr uint32_t SENSOR_RETRY_MS = 3000;
// A ~3-4 KB JSON report takes >250 ms on the 115200-baud UART. Without a
// TX ring buffer, Serial.print blocks the acquisition loop and trips the
// 150 ms optical gap guard every second, before a 100-sample window can fill.
constexpr size_t TELEMETRY_TX_BUFFER_BYTES = 8192;

constexpr uint8_t TMP117_CANDIDATE_ADDRESSES[] = {0x48, 0x49, 0x4A, 0x4B};
constexpr uint8_t SHT40_ADDRESS = 0x44;
constexpr uint8_t MLX90614_ADDRESS = 0x5A;

// Only the sensors actually installed and independently tested on this bus are
// counted. Optional legacy modules never change this denominator.
constexpr uint8_t VITAL_SENSOR_MAX = 3;

constexpr float TMP117_MAX_STEP_C = 5.0f;
constexpr float TMP117_CONFIRM_STEP_C = 0.5f;
constexpr float MPU_ACCEL_LSB_PER_G = sensor_math::MPU_ACCEL_LSB_PER_G;
constexpr float MPU_GYRO_LSB_PER_DPS = sensor_math::MPU_GYRO_LSB_PER_DPS;
constexpr float MPU_GRAVITY_G = 1.0f;

const char* const SENSOR_VALID = "valid";
const char* const SENSOR_WARMING = "warming_up";
const char* const SENSOR_LOW_QUALITY = "low_quality";
const char* const SENSOR_STALE = "stale";
const char* const SENSOR_ERROR = "sensor_error";
const char* const SENSOR_NOT_AVAILABLE = "not_available";

// ---------------------------------------------------------------------------
// Global hardware state
// ---------------------------------------------------------------------------
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);
MAX30105 max30102;
#if RPM_ENABLE_OPTIONAL_MLX90614
Adafruit_MLX90614 mlx;
#endif
#if RPM_ENABLE_OPTIONAL_SHT40
Adafruit_SHT4x sht40;
#endif

bool oledOK = false;
bool mpuPresent = false;
bool maxPresent = false;
bool tmp117Present = false;
#if RPM_ENABLE_OPTIONAL_MLX90614
bool mlxPresent = false;
#endif
#if RPM_ENABLE_OPTIONAL_SHT40
bool sht40Present = false;
#endif

uint8_t mpuAddress = 0x68;
uint8_t mpuWhoAmI = 0;
uint8_t tmp117Address = 0;
uint16_t tmp117WhoAmI = 0;
uint16_t tmp117Configuration = 0;
uint16_t tmp117OffsetRaw = 0;
bool tmp117OffsetValid = false;
uint16_t tmp117Raw = 0;
bool tmp117RawValid = false;
float tmp117TempC = NAN;
float tmp117LastAcceptedC = NAN;
float tmp117CandidateC = NAN;
bool tmp117CandidatePending = false;
uint32_t tmp117LastAttemptMs = 0;
uint32_t tmp117LastValidMs = 0;
uint8_t tmp117ConsecutiveErrors = 0;
uint16_t tmp117ErrorCount = 0;
const char* tmp117Status = SENSOR_NOT_AVAILABLE;
const char* tmp117Error = "none";

const char* mpuStatus = SENSOR_NOT_AVAILABLE;
const char* mpuError = "none";
const char* activityState = SENSOR_NOT_AVAILABLE;
const char* orientationName = SENSOR_NOT_AVAILABLE;
uint32_t mpuLastAttemptMs = 0;
uint32_t mpuLastValidMs = 0;
uint8_t mpuConsecutiveErrors = 0;
uint16_t mpuErrorCount = 0;
float accelXG = NAN, accelYG = NAN, accelZG = NAN;
float gyroXDps = NAN, gyroYDps = NAN, gyroZDps = NAN;
float currentMotionG = NAN;
float currentGyroDps = NAN;
int16_t mpuLastAccelRaw[3] = {0, 0, 0};
int16_t mpuLastGyroRaw[3] = {0, 0, 0};
bool mpuRawValid = false;

const char* maxStatus = SENSOR_NOT_AVAILABLE;
const char* heartRateStatus = SENSOR_NOT_AVAILABLE;
const char* spo2Status = SENSOR_NOT_AVAILABLE;
const char* opticalQuality = SENSOR_NOT_AVAILABLE;
const char* maxError = "none";
uint32_t maxInitMs = 0;
uint32_t lastOpticalSampleMs = 0;
uint32_t lastOpticalResultMs = 0;
uint32_t lastHeartRateValidMs = 0;
uint32_t lastSpo2ValidMs = 0;
uint16_t opticalErrorCount = 0;
uint32_t opticalSamplesReceived = 0;
uint32_t opticalWindowsCompleted = 0;
uint32_t opticalGapResets = 0;
uint32_t opticalMaxSampleGapMs = 0;
bool fingerDetected = false;
int currentBpm = 0;
int currentSpO2 = 0;
long lastIR = 0;
long lastRed = 0;
float opticalPerfusionIndex = NAN;

float objectTempC = NAN;
float ambientTempC = NAN;
float sht40TempC = NAN;
float sht40HumidityPct = NAN;
const char* sht40Status = SENSOR_NOT_AVAILABLE;
const char* mlxStatus = SENSOR_NOT_AVAILABLE;
uint32_t mlxLastValidMs = 0;

// MAX30102 algorithm buffers: 100 Hz FIFO with 4x averaging gives 25 samples/s.
uint32_t irSamples[100];
uint32_t redSamples[100];
uint16_t sampleCount = 0;

// SOS and fall alerts
bool sosActive = false;
uint32_t sosClearTime = 0;
bool fallActive = false;
uint32_t fallClearTime = 0;
uint32_t freeFallTime = 0;
int stepCount = 0;
float lastMag = 1.0f;
uint32_t lastStepTime = 0;

uint32_t lastReportTime = 0;
uint32_t lastFastTick = 0;
uint32_t lastSensorRetry = 0;

// ---------------------------------------------------------------------------
// IMU calibration state (basic stationary bias, not a full six-face calibration)
// ---------------------------------------------------------------------------
struct ImuCalibration {
    const char* status = "not_available";
    bool gyroBiasValid = false;
    bool accelBiasValid = false;
    bool stationary = false;
    uint16_t samples = 0;
    uint8_t attempts = 0;
    float gyroBiasDps[3] = {0.0f, 0.0f, 0.0f};
    float accelBiasG[3] = {0.0f, 0.0f, 0.0f};
    const char* accelBiasStatus = "not_available";
    const char* method = "80 samples at 50 Hz; stationarity range checks; single-orientation gravity reference";
    uint32_t completedAtMs = 0;
    char orientation[12] = "unknown";
};
ImuCalibration imuCalibration;

// Forward declarations used by the fast acquisition path.
void outputTelemetry(bool urgent = false);
void updateOLED();

// ---------------------------------------------------------------------------
// Small checked I2C helpers
// ---------------------------------------------------------------------------
enum class I2CResult : uint8_t {
    OK,
    ADDRESS_NACK,
    DATA_NACK,
    OTHER_ERROR,
    SHORT_READ
};

I2CResult i2cResultFromEndTransmission(uint8_t code) {
    switch (code) {
        case 0: return I2CResult::OK;
        case 2: return I2CResult::ADDRESS_NACK;
        case 3: return I2CResult::DATA_NACK;
        case 1: return I2CResult::OTHER_ERROR;
        default: return I2CResult::OTHER_ERROR;
    }
}

const char* i2cResultName(I2CResult result) {
    switch (result) {
        case I2CResult::OK: return "ok";
        case I2CResult::ADDRESS_NACK: return "i2c_address_nack";
        case I2CResult::DATA_NACK: return "i2c_data_nack";
        case I2CResult::OTHER_ERROR: return "i2c_bus_error";
        case I2CResult::SHORT_READ: return "i2c_short_read";
        default: return "i2c_unknown_error";
    }
}

I2CResult readRegisterBytes(TwoWire& bus, uint8_t address, uint8_t reg,
                            uint8_t* destination, uint8_t length) {
    bus.beginTransmission(address);
    bus.write(reg);
    I2CResult result = i2cResultFromEndTransmission(bus.endTransmission(false));
    if (result != I2CResult::OK) return result;

    uint8_t received = static_cast<uint8_t>(bus.requestFrom(static_cast<int>(address),
                                                            static_cast<int>(length)));
    if (received != length) {
        while (bus.available()) bus.read();
        return I2CResult::SHORT_READ;
    }
    for (uint8_t i = 0; i < length; ++i) {
        if (!bus.available()) return I2CResult::SHORT_READ;
        destination[i] = static_cast<uint8_t>(bus.read());
    }
    return I2CResult::OK;
}

I2CResult readRegisterWord(TwoWire& bus, uint8_t address, uint8_t reg,
                           uint16_t& value) {
    uint8_t bytes[2] = {0, 0};
    I2CResult result = readRegisterBytes(bus, address, reg, bytes, 2);
    if (result != I2CResult::OK) return result;
    value = tmp117::wordFromBigEndianBytes(bytes[0], bytes[1]);
    return I2CResult::OK;
}

I2CResult writeRegisterWord(TwoWire& bus, uint8_t address, uint8_t reg,
                            uint16_t value) {
    bus.beginTransmission(address);
    bus.write(reg);
    bus.write(static_cast<uint8_t>(value >> 8));
    bus.write(static_cast<uint8_t>(value & 0xFF));
    return i2cResultFromEndTransmission(bus.endTransmission(true));
}

I2CResult writeRegisterByte(TwoWire& bus, uint8_t address, uint8_t reg,
                            uint8_t value) {
    bus.beginTransmission(address);
    bus.write(reg);
    bus.write(value);
    return i2cResultFromEndTransmission(bus.endTransmission(true));
}

I2CResult readRegisterByte(TwoWire& bus, uint8_t address, uint8_t reg,
                           uint8_t& value) {
    return readRegisterBytes(bus, address, reg, &value, 1);
}

bool sensorResponds(TwoWire& bus, uint8_t address) {
    bus.beginTransmission(address);
    return bus.endTransmission() == 0;
}

void printNullable(float value, uint8_t decimals = 2) {
    if (isfinite(value)) Serial.print(value, decimals);
    else Serial.print(F("null"));
}

bool isStatusValid(const char* status) {
    return status != nullptr && strcmp(status, SENSOR_VALID) == 0;
}

bool tmp117ValueValid() {
    return tmp117Present && tmp117RawValid && isStatusValid(tmp117Status) &&
           isfinite(tmp117TempC);
}

bool mpuValueValid() {
    return mpuPresent && isStatusValid(mpuStatus) &&
           isfinite(accelXG) && isfinite(accelYG) && isfinite(accelZG) &&
           isfinite(gyroXDps) && isfinite(gyroYDps) && isfinite(gyroZDps);
}

bool heartRateValueValid() {
    return maxPresent && isStatusValid(heartRateStatus) && fingerDetected &&
           currentBpm > 0;
}

bool spo2ValueValid() {
    return maxPresent && isStatusValid(spo2Status) && fingerDetected &&
           currentSpO2 > 0 && currentSpO2 <= 100;
}

uint8_t activeVitalSensorCount() {
    return static_cast<uint8_t>((mpuPresent ? 1 : 0) + (maxPresent ? 1 : 0) +
                                (tmp117Present ? 1 : 0));
}

// ---------------------------------------------------------------------------
// TMP117 raw acquisition
// ---------------------------------------------------------------------------
void markTmp117CommunicationError(I2CResult result, bool addressFailed = false) {
    tmp117ConsecutiveErrors++;
    tmp117ErrorCount++;
    tmp117Status = SENSOR_ERROR;
    tmp117Error = i2cResultName(result);
    tmp117TempC = NAN;
    tmp117RawValid = false;
    tmp117CandidatePending = false;
    if (addressFailed) {
        tmp117Present = false;
        tmp117Status = SENSOR_NOT_AVAILABLE;
    }
}

void markTmp117Rejected(const char* error, const char* status,
                        bool keepCandidate = false) {
    tmp117ConsecutiveErrors++;
    tmp117ErrorCount++;
    tmp117Status = status;
    tmp117Error = error;
    tmp117TempC = NAN;
    if (!keepCandidate) tmp117CandidatePending = false;
}

bool readTmp117(uint32_t now) {
    if (!tmp117Present) {
        tmp117Status = SENSOR_NOT_AVAILABLE;
        tmp117TempC = NAN;
        return false;
    }

    tmp117LastAttemptMs = now;
    Wire.setClock(I2C_PRIMARY_HZ);

    uint16_t configuration = 0;
    I2CResult result = readRegisterWord(Wire, tmp117Address,
                                        tmp117::REG_CONFIGURATION,
                                        configuration);
    if (result != I2CResult::OK) {
        markTmp117CommunicationError(result, result == I2CResult::ADDRESS_NACK);
        return false;
    }
    tmp117Configuration = configuration;

    if ((configuration & tmp117::CONFIG_EEPROM_BUSY_MASK) != 0) {
        tmp117Status = SENSOR_WARMING;
        tmp117Error = "eeprom_busy";
        tmp117TempC = NAN;
        return false;
    }

    // Reading the configuration register clears DATA_READY. Check it first and
    // never reuse an old result if the sensor has stopped converting.
    if ((configuration & tmp117::CONFIG_DATA_READY_MASK) == 0) {
        tmp117Status = SENSOR_WARMING;
        tmp117Error = "data_not_ready";
        tmp117TempC = NAN;
        return false;
    }

    uint16_t raw = 0;
    result = readRegisterWord(Wire, tmp117Address, tmp117::REG_TEMPERATURE, raw);
    if (result != I2CResult::OK) {
        markTmp117CommunicationError(result, result == I2CResult::ADDRESS_NACK);
        return false;
    }

    tmp117Raw = raw;
    tmp117RawValid = true;

    if (tmp117::isStuckBusPattern(raw)) {
        markTmp117Rejected("stuck_bus_raw_pattern", SENSOR_ERROR);
        return false;
    }

    float celsius = tmp117::celsiusFromRawCode(raw);
    if (!tmp117::isWithinSensorRange(celsius)) {
        markTmp117Rejected("outside_sensor_range", SENSOR_ERROR);
        return false;
    }

    if (isfinite(tmp117LastAcceptedC) &&
        fabs(celsius - tmp117LastAcceptedC) > TMP117_MAX_STEP_C) {
        if (tmp117CandidatePending &&
            fabs(celsius - tmp117CandidateC) <= TMP117_CONFIRM_STEP_C) {
            // A sustained new value is allowed after one confirmation sample.
        } else {
            tmp117CandidateC = celsius;
            tmp117CandidatePending = true;
            markTmp117Rejected("abrupt_change_pending_confirmation",
                               SENSOR_LOW_QUALITY, true);
            return false;
        }
    }

    tmp117CandidatePending = false;
    tmp117LastAcceptedC = celsius;
    tmp117TempC = celsius;
    tmp117LastValidMs = now;
    tmp117ConsecutiveErrors = 0;
    tmp117Status = SENSOR_VALID;
    tmp117Error = "none";
    return true;
}

bool initTmp117() {
    Wire.setClock(I2C_PRIMARY_HZ);
    tmp117TempC = NAN;
    tmp117Status = SENSOR_NOT_AVAILABLE;
    tmp117Error = "not_initialized";
    tmp117RawValid = false;
    tmp117OffsetValid = false;

    for (uint8_t address : TMP117_CANDIDATE_ADDRESSES) {
        if (!sensorResponds(Wire, address)) continue;

        uint8_t idBytes[2] = {0, 0};
        I2CResult result = readRegisterBytes(Wire, address, tmp117::REG_DEVICE_ID,
                                             idBytes, 2);
        if (result != I2CResult::OK) continue;
        uint16_t id = tmp117::wordFromBigEndianBytes(idBytes[0], idBytes[1]);
        if (id != tmp117::DEVICE_ID_TMP117) continue;

        uint16_t configuration = 0;
        result = readRegisterWord(Wire, address, tmp117::REG_CONFIGURATION,
                                  configuration);
        if (result != I2CResult::OK) continue;

        result = writeRegisterWord(Wire, address, tmp117::REG_CONFIGURATION,
                                   tmp117::CONFIG_CONTINUOUS_8AVG_500MS);
        if (result != I2CResult::OK) continue;
        delay(5);

        uint16_t readback = 0;
        result = readRegisterWord(Wire, address, tmp117::REG_CONFIGURATION,
                                  readback);
        if (result != I2CResult::OK) continue;
        if ((readback & tmp117::CONFIG_WRITABLE_MASK) !=
            (tmp117::CONFIG_CONTINUOUS_8AVG_500MS & tmp117::CONFIG_WRITABLE_MASK)) {
            Serial.print(F("    [TMP117] Configuration readback mismatch: 0x"));
            Serial.println(readback, HEX);
            continue;
        }

        uint16_t offset = 0;
        bool offsetValid = readRegisterWord(
            Wire, address, tmp117::REG_TEMPERATURE_OFFSET, offset) == I2CResult::OK;

        tmp117Address = address;
        tmp117WhoAmI = id;
        tmp117Configuration = readback;
        tmp117OffsetRaw = offsetValid ? offset : 0;
        tmp117OffsetValid = offsetValid;
        tmp117Present = true;
        tmp117ConsecutiveErrors = 0;
        tmp117Status = SENSOR_WARMING;
        tmp117Error = "waiting_for_first_conversion";
        tmp117LastValidMs = 0;
        tmp117LastAcceptedC = NAN;
        tmp117CandidatePending = false;
        tmp117RawValid = false;

        Serial.print(F("    Found TMP117 at 0x"));
        if (tmp117Address < 16) Serial.print(F("0"));
        Serial.print(tmp117Address, HEX);
        Serial.print(F(", WHO_AM_I=0x"));
        Serial.print(tmp117WhoAmI, HEX);
        Serial.print(F(", config=0x"));
        Serial.print(tmp117Configuration, HEX);
        Serial.print(F(", offset_raw="));
        if (tmp117OffsetValid) {
            Serial.print(static_cast<int16_t>(tmp117OffsetRaw));
            if (tmp117OffsetRaw != 0) {
                Serial.print(F(" [WARNING: nonzero hardware offset; no software offset is applied]"));
            }
            Serial.println();
        } else {
            Serial.println(F("unavailable (read failed)"));
        }

        // The configured cycle is 500 ms; wait once for the first completed
        // conversion without an unbounded data-ready loop.
        delay(600);
        readTmp117(millis());
        // Discovery and configuration succeeded, but the first transaction
        // after the conversion wait may still have lost the address. Report
        // discovery only while the device is still present.
        return tmp117Present;
    }

    tmp117Present = false;
    tmp117Status = SENSOR_NOT_AVAILABLE;
    tmp117Error = "not_found_or_identity_mismatch";
    return false;
}

void updateTmp117(uint32_t now) {
    if (tmp117Present && (now - tmp117LastAttemptMs >= TMP117_READ_INTERVAL_MS)) {
        readTmp117(now);
    }
}

// ---------------------------------------------------------------------------
// MPU-6050 / MPU-6500 raw acquisition and calibration
// ---------------------------------------------------------------------------
#define MPU_REG_SMPLRT_DIV   0x19
#define MPU_REG_CONFIG       0x1A
#define MPU_REG_GYRO_CONFIG  0x1B
#define MPU_REG_ACCEL_CONFIG 0x1C
#define MPU_REG_ACCEL_XOUT_H 0x3B
#define MPU_REG_PWR_MGMT_1   0x6B
#define MPU_REG_WHO_AM_I     0x75

bool mpuRawRead(int16_t accelRaw[3], int16_t gyroRaw[3]) {
    uint8_t data[14] = {0};
    I2CResult result = readRegisterBytes(Wire1, mpuAddress,
                                         MPU_REG_ACCEL_XOUT_H, data, 14);
    if (result != I2CResult::OK) {
        mpuError = i2cResultName(result);
        return false;
    }
    for (int i = 0; i < 3; ++i) {
        accelRaw[i] = static_cast<int16_t>(
            tmp117::wordFromBigEndianBytes(data[i * 2], data[i * 2 + 1]));
    }
    // Bytes 6 and 7 are the on-die temperature and are not used here.
    for (int i = 0; i < 3; ++i) {
        gyroRaw[i] = static_cast<int16_t>(
            tmp117::wordFromBigEndianBytes(data[8 + i * 2], data[9 + i * 2]));
    }
    return true;
}

bool initMpuRaw(uint8_t address) {
    Wire1.setClock(I2C_IMU_HZ);
    uint8_t who = 0;
    I2CResult result = readRegisterByte(Wire1, address, MPU_REG_WHO_AM_I, who);
    if (result != I2CResult::OK) return false;
    if (who != 0x68 && who != 0x70) {
        Serial.print(F("    [MPU] Unsupported WHO_AM_I 0x"));
        Serial.println(who, HEX);
        return false;
    }

    if (writeRegisterByte(Wire1, address, MPU_REG_PWR_MGMT_1, 0x80) != I2CResult::OK) {
        return false;
    }
    delay(50);
    if (writeRegisterByte(Wire1, address, MPU_REG_PWR_MGMT_1, 0x00) != I2CResult::OK) {
        return false;
    }
    delay(10);

    uint8_t power = 0xFF;
    if (readRegisterByte(Wire1, address, MPU_REG_PWR_MGMT_1, power) != I2CResult::OK ||
        (power & 0x40) != 0) {
        return false;
    }

    // 200 Hz sample rate, 44 Hz DLPF, +/-250 dps gyro, +/-8 g accelerometer.
    if (writeRegisterByte(Wire1, address, MPU_REG_SMPLRT_DIV, 0x04) != I2CResult::OK) return false;
    if (writeRegisterByte(Wire1, address, MPU_REG_CONFIG, 0x03) != I2CResult::OK) return false;
    if (writeRegisterByte(Wire1, address, MPU_REG_GYRO_CONFIG, 0x00) != I2CResult::OK) return false;
    if (writeRegisterByte(Wire1, address, MPU_REG_ACCEL_CONFIG, 0x10) != I2CResult::OK) return false;
    delay(20);

    uint8_t accelConfig = 0, gyroConfig = 0;
    if (readRegisterByte(Wire1, address, MPU_REG_ACCEL_CONFIG, accelConfig) != I2CResult::OK) return false;
    if (readRegisterByte(Wire1, address, MPU_REG_GYRO_CONFIG, gyroConfig) != I2CResult::OK) return false;
    if ((accelConfig & 0x18) != 0x10 || (gyroConfig & 0x18) != 0x00) {
        return false;
    }

    mpuAddress = address;
    mpuWhoAmI = who;
    mpuPresent = true;
    mpuStatus = SENSOR_WARMING;
    mpuError = "waiting_for_first_sample";
    mpuLastValidMs = 0;
    mpuConsecutiveErrors = 0;
    return true;
}

bool initMpu() {
    Wire1.setClock(I2C_IMU_HZ);
    for (uint8_t address : {0x68, 0x69}) {
        if (!sensorResponds(Wire1, address)) continue;
        if (initMpuRaw(address)) return true;
    }
    mpuPresent = false;
    mpuStatus = SENSOR_NOT_AVAILABLE;
    mpuError = "not_found_or_unsupported";
    return false;
}

const char* orientationFromVector(float x, float y, float z) {
    float ax = fabs(x), ay = fabs(y), az = fabs(z);
    if (az >= ax && az >= ay) return z >= 0 ? "z_up" : "z_down";
    if (ax >= ay) return x >= 0 ? "x_up" : "x_down";
    return y >= 0 ? "y_up" : "y_down";
}

bool collectMpuCalibrationWindow(ImuCalibration& calibration) {
    constexpr uint16_t sampleTarget = 80;
    float accelSums[3] = {0, 0, 0};
    float gyroSums[3] = {0, 0, 0};
    float accelMin[3] = {1e9f, 1e9f, 1e9f};
    float accelMax[3] = {-1e9f, -1e9f, -1e9f};
    float gyroMin[3] = {1e9f, 1e9f, 1e9f};
    float gyroMax[3] = {-1e9f, -1e9f, -1e9f};
    int16_t accelRaw[3];
    int16_t gyroRaw[3];

    for (uint16_t i = 0; i < sampleTarget; ++i) {
        if (!mpuRawRead(accelRaw, gyroRaw)) return false;
        for (int axis = 0; axis < 3; ++axis) {
            float a = sensor_math::accelRawToG(accelRaw[axis]);
            float g = sensor_math::gyroRawToDps(gyroRaw[axis]);
            accelSums[axis] += a;
            gyroSums[axis] += g;
            if (a < accelMin[axis]) accelMin[axis] = a;
            if (a > accelMax[axis]) accelMax[axis] = a;
            if (g < gyroMin[axis]) gyroMin[axis] = g;
            if (g > gyroMax[axis]) gyroMax[axis] = g;
        }
        delay(MPU_READ_INTERVAL_MS);
    }

    float accelMean[3], gyroMean[3];
    bool stationary = true;
    for (int axis = 0; axis < 3; ++axis) {
        accelMean[axis] = accelSums[axis] / sampleTarget;
        gyroMean[axis] = gyroSums[axis] / sampleTarget;
        if ((accelMax[axis] - accelMin[axis]) > 0.15f) stationary = false;
        if ((gyroMax[axis] - gyroMin[axis]) > 4.0f) stationary = false;
    }
    float meanMagnitude = sqrtf(accelMean[0] * accelMean[0] +
                                accelMean[1] * accelMean[1] +
                                accelMean[2] * accelMean[2]);
    if (meanMagnitude < 0.7f || meanMagnitude > 1.3f) stationary = false;

    calibration.samples = sampleTarget;
    calibration.stationary = stationary;
    if (!stationary) return false;

    for (int axis = 0; axis < 3; ++axis) {
        calibration.gyroBiasDps[axis] = gyroMean[axis];
        calibration.accelBiasG[axis] = 0.0f;
    }
    calibration.gyroBiasValid = true;

    int dominantAxis = 0;
    for (int axis = 1; axis < 3; ++axis) {
        if (fabsf(accelMean[axis]) > fabsf(accelMean[dominantAxis])) dominantAxis = axis;
    }
    float expected[3] = {0.0f, 0.0f, 0.0f};
    expected[dominantAxis] = accelMean[dominantAxis] >= 0 ? 1.0f : -1.0f;
    bool nearKnownAxis = fabsf(accelMean[dominantAxis]) >= 0.8f &&
                         fabsf(accelMean[dominantAxis]) <= 1.2f;
    for (int axis = 0; axis < 3; ++axis) {
        if (axis != dominantAxis && fabsf(accelMean[axis]) > 0.20f) {
            nearKnownAxis = false;
        }
    }

    if (nearKnownAxis) {
        for (int axis = 0; axis < 3; ++axis) {
            calibration.accelBiasG[axis] = accelMean[axis] - expected[axis];
        }
        calibration.accelBiasValid = true;
        calibration.accelBiasStatus = "estimated_single_orientation";
        calibration.status = "basic_complete";
    } else {
        calibration.accelBiasStatus = "not_estimated_orientation_unknown";
        calibration.status = "gyro_complete";
    }

    calibration.orientation[0] = '\0';
    strncpy(calibration.orientation, orientationFromVector(accelMean[0], accelMean[1], accelMean[2]),
            sizeof(calibration.orientation) - 1);
    calibration.orientation[sizeof(calibration.orientation) - 1] = '\0';
    calibration.method = "80 samples at 50 Hz; stationarity range checks; single-orientation gravity reference";
    calibration.completedAtMs = millis();
    return true;
}

void calibrateMpu() {
    imuCalibration = ImuCalibration();
    imuCalibration.status = "failed";
    imuCalibration.accelBiasStatus = "not_estimated";
    if (!mpuPresent) {
        imuCalibration.status = "not_available";
        return;
    }

    Serial.println(F("    Keep the MPU-6050 still: collecting stationary bias..."));
    for (uint8_t attempt = 0; attempt < 2; ++attempt) {
        imuCalibration.attempts = attempt + 1;
        if (collectMpuCalibrationWindow(imuCalibration)) {
            Serial.print(F("    MPU calibration: "));
            Serial.print(imuCalibration.status);
            Serial.print(F(" (gyro bias "));
            Serial.print(imuCalibration.gyroBiasDps[0], 2);
            Serial.print(F(", "));
            Serial.print(imuCalibration.gyroBiasDps[1], 2);
            Serial.print(F(", "));
            Serial.print(imuCalibration.gyroBiasDps[2], 2);
            Serial.print(F(" dps; accel bias "));
            Serial.print(imuCalibration.accelBiasStatus);
            Serial.println(F(")"));
            return;
        }
        delay(250);
    }
    imuCalibration.status = "failed";
    imuCalibration.accelBiasStatus = "not_estimated_device_moved";
    Serial.println(F("    MPU calibration failed: device did not remain stationary."));
}

void updateMpu(uint32_t now) {
    if (!mpuPresent) return;
    mpuLastAttemptMs = now;
    int16_t accelRaw[3], gyroRaw[3];
    if (!mpuRawRead(accelRaw, gyroRaw)) {
        mpuConsecutiveErrors++;
        mpuErrorCount++;
        mpuStatus = SENSOR_ERROR;
        mpuError = "i2c_read_failed";
        accelXG = accelYG = accelZG = NAN;
        gyroXDps = gyroYDps = gyroZDps = NAN;
        currentMotionG = NAN;
        currentGyroDps = NAN;
        mpuRawValid = false;
        activityState = SENSOR_NOT_AVAILABLE;
        orientationName = SENSOR_NOT_AVAILABLE;
        if (mpuConsecutiveErrors >= 5) {
            mpuPresent = false;
            mpuStatus = SENSOR_NOT_AVAILABLE;
        }
        return;
    }

    mpuConsecutiveErrors = 0;
    mpuError = "none";
    mpuStatus = SENSOR_VALID;
    mpuLastValidMs = now;
    for (int i = 0; i < 3; ++i) {
        mpuLastAccelRaw[i] = accelRaw[i];
        mpuLastGyroRaw[i] = gyroRaw[i];
    }
    mpuRawValid = true;

    float ax = sensor_math::accelRawToG(accelRaw[0]);
    float ay = sensor_math::accelRawToG(accelRaw[1]);
    float az = sensor_math::accelRawToG(accelRaw[2]);
    float gx = sensor_math::gyroRawToDps(gyroRaw[0]);
    float gy = sensor_math::gyroRawToDps(gyroRaw[1]);
    float gz = sensor_math::gyroRawToDps(gyroRaw[2]);

    if (imuCalibration.accelBiasValid) {
        ax -= imuCalibration.accelBiasG[0];
        ay -= imuCalibration.accelBiasG[1];
        az -= imuCalibration.accelBiasG[2];
    }
    if (imuCalibration.gyroBiasValid) {
        gx -= imuCalibration.gyroBiasDps[0];
        gy -= imuCalibration.gyroBiasDps[1];
        gz -= imuCalibration.gyroBiasDps[2];
    }

    accelXG = ax;
    accelYG = ay;
    accelZG = az;
    gyroXDps = gx;
    gyroYDps = gy;
    gyroZDps = gz;
    currentMotionG = sensor_math::magnitude3(ax, ay, az);
    currentGyroDps = sensor_math::magnitude3(gx, gy, gz);
    orientationName = orientationFromVector(ax, ay, az);
    activityState = (currentGyroDps < 1.2f && fabsf(currentMotionG - MPU_GRAVITY_G) < 0.12f)
                        ? "stationary" : "moving";

    float delta = fabsf(currentMotionG - MPU_GRAVITY_G);
    if (delta > 0.40f && lastMag <= 0.40f && (now - lastStepTime > 380)) {
        stepCount++;
        lastStepTime = now;
    }
    lastMag = delta;

    if (currentMotionG < 0.6f) freeFallTime = now;
    if (freeFallTime > 0 && now - freeFallTime > 1000) freeFallTime = 0;

    if (currentMotionG > 2.5f && !fallActive) {
        if (freeFallTime > 0 && now - freeFallTime <= 600 &&
            now - freeFallTime >= 60) {
            fallActive = true;
            fallClearTime = now + 6000;
            freeFallTime = 0;
            Serial.print(F("\n>>> [2-STAGE FALL DETECTED] Force: "));
            Serial.print(currentMotionG, 2);
            Serial.println(F(" g after free-fall; possible fall, check the patient. <<<"));
            outputTelemetry(true);
            updateOLED();
        }
    }
}

// ---------------------------------------------------------------------------
// MAX30102 acquisition and validity
// ---------------------------------------------------------------------------
void resetOpticalState(const char* sensorStatus, const char* measurementStatus) {
    currentBpm = 0;
    currentSpO2 = 0;
    fingerDetected = false;
    sampleCount = 0;
    opticalPerfusionIndex = NAN;
    opticalQuality = SENSOR_NOT_AVAILABLE;
    maxStatus = sensorStatus;
    heartRateStatus = measurementStatus;
    spo2Status = measurementStatus;
    lastOpticalResultMs = 0;
    lastHeartRateValidMs = 0;
    lastSpo2ValidMs = 0;
}

void finishOpticalWindow(uint32_t now) {
    ++opticalWindowsCompleted;
    uint32_t minimum = irSamples[0];
    uint32_t maximum = irSamples[0];
    double sum = 0.0;
    for (uint16_t i = 0; i < 100; ++i) {
        if (irSamples[i] < minimum) minimum = irSamples[i];
        if (irSamples[i] > maximum) maximum = irSamples[i];
        sum += irSamples[i];
    }
    double mean = sum / 100.0;
    double ac = static_cast<double>(maximum) - static_cast<double>(minimum);
    opticalPerfusionIndex = sensor_math::perfusionIndex(
        static_cast<float>(minimum), static_cast<float>(maximum),
        static_cast<float>(mean));

    // This is a contact/signal-quality guard, not a clinical threshold. It
    // rejects DC-only or saturated windows before publishing algorithm output.
    bool qualityGood = sensor_math::maxSignalQuality(
        static_cast<float>(mean), static_cast<float>(ac),
        opticalPerfusionIndex);
    opticalQuality = qualityGood ? "good" : "low";

    int32_t bpm = 0;
    int32_t spo2 = 0;
    int8_t bpmValid = 0;
    int8_t spo2Valid = 0;
    maxim_heart_rate_and_oxygen_saturation(irSamples, 100, redSamples,
                                           &spo2, &spo2Valid, &bpm, &bpmValid);

    bool hrAccepted = qualityGood && bpmValid && bpm >= 30 && bpm <= 240;
    bool spo2Accepted = qualityGood && spo2Valid && spo2 > 0 && spo2 <= 100;

    currentBpm = hrAccepted ? static_cast<int>(bpm) : 0;
    currentSpO2 = spo2Accepted ? static_cast<int>(spo2) : 0;
    heartRateStatus = hrAccepted ? SENSOR_VALID : SENSOR_LOW_QUALITY;
    spo2Status = spo2Accepted ? SENSOR_VALID : SENSOR_LOW_QUALITY;
    if (hrAccepted) lastHeartRateValidMs = now;
    if (spo2Accepted) lastSpo2ValidMs = now;
    maxStatus = (hrAccepted || spo2Accepted) ? SENSOR_VALID : SENSOR_LOW_QUALITY;
    lastOpticalResultMs = now;

    memmove(irSamples, irSamples + 25, 75 * sizeof(uint32_t));
    memmove(redSamples, redSamples + 25, 75 * sizeof(uint32_t));
    sampleCount = 75;
}

void sampleOptical(uint32_t now) {
    if (!maxPresent) return;

    if (lastOpticalSampleMs > 0) {
        const uint32_t gap = now - lastOpticalSampleMs;
        if (gap > opticalMaxSampleGapMs) opticalMaxSampleGapMs = gap;
    }
    if (lastOpticalSampleMs > 0 && now - lastOpticalSampleMs > OPTICAL_SAMPLE_GAP_MS) {
        ++opticalGapResets;
        resetOpticalState(SENSOR_LOW_QUALITY, SENSOR_LOW_QUALITY);
        lastOpticalSampleMs = now;
        max30102.clearFIFO();
    }

    max30102.check();
    while (max30102.available()) {
        long ir = max30102.getFIFOIR();
        long red = max30102.getFIFORed();
        max30102.nextSample();
        lastIR = ir;
        lastRed = red;
        ++opticalSamplesReceived;
        maxError = "none";

        if (ir < 50000 || red < 50000 ||
            ir >= 262143 || red >= 262143) {
            // No finger, ADC saturation or an invalid optical sample. Never
            // carry the previous pulse estimate through this condition.
            bool noContact = ir < 50000 || red < 50000;
            resetOpticalState(noContact ? SENSOR_NOT_AVAILABLE : SENSOR_LOW_QUALITY,
                              noContact ? SENSOR_NOT_AVAILABLE : SENSOR_LOW_QUALITY);
            lastOpticalSampleMs = now;
            continue;
        }

        fingerDetected = true;
        lastOpticalSampleMs = now;
        irSamples[sampleCount] = static_cast<uint32_t>(ir);
        redSamples[sampleCount] = static_cast<uint32_t>(red);
        sampleCount++;
        if (sensor_math::opticalWindowIsWarming(sampleCount,
                                                lastOpticalResultMs > 0)) {
            maxStatus = SENSOR_WARMING;
            heartRateStatus = SENSOR_WARMING;
            spo2Status = SENSOR_WARMING;
        } else if (sampleCount >= 100) {
            finishOpticalWindow(now);
        }
    }
}

bool initMax30102() {
    Wire.setClock(I2C_PRIMARY_HZ);
    if (!max30102.begin(Wire, I2C_SPEED_STANDARD)) {
        maxPresent = false;
        maxStatus = SENSOR_NOT_AVAILABLE;
        maxError = "init_failed";
        return false;
    }
    uint8_t partId = max30102.readPartID();
    Serial.print(F("    MAX30102 PART_ID=0x"));
    Serial.println(partId, HEX);
    if (partId != 0x15) {
        maxPresent = false;
        maxStatus = SENSOR_ERROR;
        maxError = "unexpected_part_id";
        return false;
    }

    max30102.setup(0x24, 4, 2, 100, 411, 4096);
    Wire.setClock(I2C_PRIMARY_HZ);
    max30102.setPulseAmplitudeRed(0x24);
    max30102.setPulseAmplitudeIR(0x24);
    max30102.clearFIFO();
    maxPresent = true;
    maxError = "none";
    maxInitMs = millis();
    lastOpticalSampleMs = 0;
    lastOpticalResultMs = 0;
    resetOpticalState(SENSOR_WARMING, SENSOR_NOT_AVAILABLE);
    maxStatus = SENSOR_WARMING;
    return true;
}

// ---------------------------------------------------------------------------
// Optional legacy sensors (compiled out by default; never counted)
// ---------------------------------------------------------------------------
#if RPM_ENABLE_OPTIONAL_SHT40
bool initSht40Optional() {
    sht40Status = SENSOR_NOT_AVAILABLE;
    sht40TempC = NAN;
    sht40HumidityPct = NAN;
    if (!sensorResponds(Wire, SHT40_ADDRESS)) return false;
    if (!sht40.begin(&Wire)) return false;
    sht40.setPrecision(SHT4X_HIGH_PRECISION);
    sht40.setHeater(SHT4X_NO_HEATER);
    sensors_event_t humidityEvent, tempEvent;
    if (!sht40.getEvent(&humidityEvent, &tempEvent)) return false;
    if (!isfinite(tempEvent.temperature) ||
        tempEvent.temperature < -40.0f || tempEvent.temperature > 125.0f ||
        !isfinite(humidityEvent.relative_humidity) ||
        humidityEvent.relative_humidity < 0.0f ||
        humidityEvent.relative_humidity > 100.0f) {
        return false;
    }
    sht40TempC = tempEvent.temperature;
    sht40HumidityPct = humidityEvent.relative_humidity;
    sht40Present = true;
    sht40Status = SENSOR_VALID;
    return true;
}

void updateSht40Optional() {
    if (!sht40Present) return;
    sensors_event_t humidityEvent, tempEvent;
    if (!sht40.getEvent(&humidityEvent, &tempEvent) ||
        !isfinite(tempEvent.temperature) ||
        !isfinite(humidityEvent.relative_humidity)) {
        sht40Present = false;
        sht40Status = SENSOR_ERROR;
        sht40TempC = NAN;
        sht40HumidityPct = NAN;
        return;
    }
    sht40TempC = tempEvent.temperature;
    sht40HumidityPct = humidityEvent.relative_humidity;
    sht40Status = SENSOR_VALID;
}
#endif

#if RPM_ENABLE_OPTIONAL_MLX90614
bool initMlxOptional() {
    mlxStatus = SENSOR_NOT_AVAILABLE;
    objectTempC = NAN;
    ambientTempC = NAN;
    if (!mlx.begin(MLX90614_ADDRESS, &Wire)) return false;
    mlxPresent = true;
    mlxStatus = SENSOR_WARMING;
    return true;
}

void updateMlxOptional(uint32_t now) {
    if (!mlxPresent) return;
    float object = mlx.readObjectTempC();
    float ambient = mlx.readAmbientTempC();
    if (!isfinite(object) || !isfinite(ambient) ||
        object < -70.0f || object > 380.0f ||
        ambient < -40.0f || ambient > 125.0f) {
        mlxPresent = false;
        mlxStatus = SENSOR_ERROR;
        objectTempC = NAN;
        ambientTempC = NAN;
        return;
    }
    objectTempC = object;
    ambientTempC = ambient;
    mlxStatus = SENSOR_VALID;
    mlxLastValidMs = now;
}
#endif

// ---------------------------------------------------------------------------
// Status freshness
// ---------------------------------------------------------------------------
void refreshSensorStatuses(uint32_t now) {
    if (!tmp117Present) {
        tmp117Status = SENSOR_NOT_AVAILABLE;
        tmp117TempC = NAN;
    } else if (tmp117LastValidMs > 0 && now - tmp117LastValidMs > TMP117_STALE_MS) {
        tmp117Status = SENSOR_STALE;
        tmp117TempC = NAN;
    }
    if (!isStatusValid(tmp117Status)) tmp117TempC = NAN;

    if (!maxPresent) {
        // Preserve an identity/init fault so the dashboard does not collapse a
        // wrong PART_ID into an indistinguishable "not connected" state.
        if (maxStatus != SENSOR_ERROR) maxStatus = SENSOR_NOT_AVAILABLE;
        heartRateStatus = SENSOR_NOT_AVAILABLE;
        spo2Status = SENSOR_NOT_AVAILABLE;
        opticalQuality = SENSOR_NOT_AVAILABLE;
        currentBpm = 0;
        currentSpO2 = 0;
        fingerDetected = false;
        lastIR = 0;
        lastRed = 0;
        opticalPerfusionIndex = NAN;
    } else if (fingerDetected && lastOpticalSampleMs > 0 &&
               now - lastOpticalSampleMs > OPTICAL_STALE_MS) {
        resetOpticalState(SENSOR_STALE, SENSOR_STALE);
    } else if (fingerDetected && lastOpticalResultMs > 0 &&
               now - lastOpticalResultMs > OPTICAL_STALE_MS + 4000) {
        resetOpticalState(SENSOR_STALE, SENSOR_STALE);
    } else if (lastOpticalSampleMs == 0 && maxInitMs > 0 &&
               now - maxInitMs > 5000) {
        // A configured MAX30102 produces FIFO samples even without a finger.
        // No samples at all therefore indicates a sensor/FIFO fault, not just
        // absence of contact.
        resetOpticalState(SENSOR_ERROR, SENSOR_ERROR);
        maxError = "no_fifo_samples";
    }
    if (!isStatusValid(heartRateStatus)) currentBpm = 0;
    if (!isStatusValid(spo2Status)) currentSpO2 = 0;

    if (!mpuPresent) {
        mpuStatus = SENSOR_NOT_AVAILABLE;
        accelXG = accelYG = accelZG = NAN;
        gyroXDps = gyroYDps = gyroZDps = NAN;
        currentMotionG = NAN;
        currentGyroDps = NAN;
        mpuRawValid = false;
        activityState = SENSOR_NOT_AVAILABLE;
        orientationName = SENSOR_NOT_AVAILABLE;
    } else if (mpuLastValidMs > 0 && now - mpuLastValidMs > MPU_STALE_MS) {
        mpuStatus = SENSOR_STALE;
        accelXG = accelYG = accelZG = NAN;
        gyroXDps = gyroYDps = gyroZDps = NAN;
        currentMotionG = NAN;
        currentGyroDps = NAN;
        mpuRawValid = false;
        activityState = SENSOR_NOT_AVAILABLE;
        orientationName = SENSOR_NOT_AVAILABLE;
    }
}

// ---------------------------------------------------------------------------
// Telemetry
// ---------------------------------------------------------------------------
const char* overallRisk() {
    if (sosActive || fallActive) return "EMERGENCY";
    if (heartRateValueValid() && (currentBpm < 50 || currentBpm > 120)) return "WARNING";
    if (spo2ValueValid() && currentSpO2 < 90) return "WARNING";
    if (heartRateValueValid() && spo2ValueValid()) return "NORMAL";
    return "UNKNOWN";
}

const char* clinicalSummary() {
    if (sosActive) return "PATIENT SOS BUTTON PRESSED. Immediate caregiver response required.";
    if (fallActive) return "POSSIBLE FALL DETECTED. Check on the patient; this is not a clinical diagnosis.";
    if (spo2ValueValid() && currentSpO2 < 90) return "LOW SPO2 ALERT: optical estimate below 90%. Check placement and notify a caregiver. Core temperature unavailable \xE2\x80\x94 confirmation required.";
    if (heartRateValueValid() && (currentBpm < 50 || currentBpm > 120)) return "OPTICAL HEART-RATE THRESHOLD CROSSED. Check the patient if it persists. Core temperature unavailable \xE2\x80\x94 confirmation required.";
    if (heartRateValueValid() && spo2ValueValid()) return "No configured optical alert threshold crossed. Wrist skin temperature is not core temperature; core temperature unavailable \xE2\x80\x94 confirmation required.";
    return "Waiting for valid optical readings; unavailable measurements are null. Core temperature unavailable \xE2\x80\x94 confirmation required.";
}

void printStatus(const char* value) {
    if (value == nullptr) Serial.print(F("not_available"));
    else Serial.print(value);
}

void outputTelemetry(bool urgent) {
    uint32_t now = millis();
    // Emergency and fall paths can call this outside the one-second report
    // cadence. Re-evaluate freshness first so stale values are never published
    // as valid during those paths.
    refreshSensorStatuses(now);
    const bool tmpValid = tmp117ValueValid();
    const bool imuValid = mpuValueValid();
    const bool hrValid = heartRateValueValid();
    const bool spo2Valid = spo2ValueValid();

    Serial.print(F("[JSON] {"));
    Serial.print(F("\"uptime_s\":")); Serial.print(now / 1000);
    Serial.print(F(",\"device_id\":\"RPM-NODE-01\""));
    Serial.print(F(",\"firmware_version\":\"rpm-2.1.1\""));
    Serial.print(F(",\"schema_version\":2"));
    Serial.printf(",\"board\":{\"flash_bytes\":%u,\"psram_bytes\":%u}",
                  static_cast<unsigned>(ESP.getFlashChipSize()),
                  static_cast<unsigned>(ESP.getPsramSize()));
    Serial.print(F(",\"risk\":\"")); Serial.print(overallRisk()); Serial.print(F("\""));
    Serial.print(F(",\"urgent\":")); Serial.print(urgent ? F("true") : F("false"));

    Serial.print(F(",\"sensors\":{"));
    Serial.print(F("\"oled\":")); Serial.print(oledOK ? F("true") : F("false"));
    Serial.print(F(",\"max\":")); Serial.print(maxPresent ? F("true") : F("false"));
    Serial.print(F(",\"mpu\":")); Serial.print(mpuPresent ? F("true") : F("false"));
    Serial.print(F(",\"tmp117\":")); Serial.print(tmp117Present ? F("true") : F("false"));
    // Compatibility fields. Optional legacy modules are compiled out and never
    // counted; if deliberately enabled they still do not change active_max.
    Serial.print(F(",\"sht40\":"));
#if RPM_ENABLE_OPTIONAL_SHT40
    Serial.print(sht40Present ? F("true") : F("false"));
#else
    Serial.print(F("false"));
#endif
    Serial.print(F(",\"mlx\":"));
#if RPM_ENABLE_OPTIONAL_MLX90614
    Serial.print(mlxPresent ? F("true") : F("false"));
#else
    Serial.print(F("false"));
#endif
    Serial.print(F(",\"active\":")); Serial.print(activeVitalSensorCount());
    Serial.print(F(",\"active_max\":")); Serial.print(VITAL_SENSOR_MAX);
    Serial.print(F("}"));

    Serial.print(F(",\"sensor_health\":{"));
    Serial.print(F("\"max\":{\"present\":"));
    Serial.print(maxPresent ? F("true") : F("false"));
    Serial.print(F(",\"status\":\"")); printStatus(maxStatus);
    Serial.print(F("\",\"error\":\""));
    Serial.print(maxError);
    Serial.print(F("\",\"window_samples\":")); Serial.print(sampleCount);
    Serial.print(F(",\"samples_received\":")); Serial.print(opticalSamplesReceived);
    Serial.print(F(",\"windows_completed\":")); Serial.print(opticalWindowsCompleted);
    Serial.print(F(",\"sample_gap_resets\":")); Serial.print(opticalGapResets);
    Serial.print(F(",\"max_sample_gap_ms\":")); Serial.print(opticalMaxSampleGapMs);
    Serial.print(F("}"));
    Serial.print(F(",\"mpu\":{\"present\":"));
    Serial.print(mpuPresent ? F("true") : F("false"));
    Serial.print(F(",\"status\":\"")); printStatus(mpuStatus);
    Serial.print(F("\",\"error\":\"")); Serial.print(mpuError);
    Serial.print(F("\",\"calibration_status\":\"")); printStatus(imuCalibration.status);
    Serial.print(F("\",\"calibration\":{\"status\":\"")); printStatus(imuCalibration.status);
    Serial.print(F("\",\"samples\":")); Serial.print(imuCalibration.samples);
    Serial.print(F(",\"attempts\":")); Serial.print(imuCalibration.attempts);
    Serial.print(F(",\"stationary\":")); Serial.print(imuCalibration.stationary ? F("true") : F("false"));
    Serial.print(F(",\"orientation\":\"")); Serial.print(imuCalibration.orientation);
    Serial.print(F("\",\"gyro_bias_valid\":")); Serial.print(imuCalibration.gyroBiasValid ? F("true") : F("false"));
    Serial.print(F(",\"accel_bias_valid\":")); Serial.print(imuCalibration.accelBiasValid ? F("true") : F("false"));
    Serial.print(F(",\"gyro_bias_dps\":"));
    if (imuCalibration.gyroBiasValid) {
        Serial.print(F("["));
        Serial.print(imuCalibration.gyroBiasDps[0], 4); Serial.print(F(","));
        Serial.print(imuCalibration.gyroBiasDps[1], 4); Serial.print(F(","));
        Serial.print(imuCalibration.gyroBiasDps[2], 4);
        Serial.print(F("]"));
    } else {
        Serial.print(F("null"));
    }
    Serial.print(F(",\"accel_bias_g\":"));
    if (imuCalibration.accelBiasValid) {
        Serial.print(F("["));
        Serial.print(imuCalibration.accelBiasG[0], 4); Serial.print(F(","));
        Serial.print(imuCalibration.accelBiasG[1], 4); Serial.print(F(","));
        Serial.print(imuCalibration.accelBiasG[2], 4);
        Serial.print(F("]"));
    } else {
        Serial.print(F("null"));
    }
    Serial.print(F(",\"accel_bias_status\":\"")); Serial.print(imuCalibration.accelBiasStatus);
    Serial.print(F("\",\"method\":\"")); Serial.print(imuCalibration.method);
    Serial.print(F("\",\"timestamp_ms\":"));
    if (imuCalibration.completedAtMs > 0) Serial.print(imuCalibration.completedAtMs);
    else Serial.print(F("null"));
    Serial.print(F("}}"));
    Serial.print(F(",\"tmp117\":{\"present\":"));
    Serial.print(tmp117Present ? F("true") : F("false"));
    Serial.print(F(",\"status\":\"")); printStatus(tmp117Status);
    Serial.print(F("\",\"error\":\"")); Serial.print(tmp117Error);
    Serial.print(F("\",\"address\":"));
    if (tmp117Present) { Serial.print(F("\"0x")); Serial.print(tmp117Address, HEX); Serial.print(F("\"")); }
    else Serial.print(F("null"));
    Serial.print(F(",\"who_am_i\":"));
    if (tmp117Present) Serial.print(tmp117WhoAmI);
    else Serial.print(F("null"));
    Serial.print(F(",\"configuration\":"));
    if (tmp117Present) Serial.print(tmp117Configuration);
    else Serial.print(F("null"));
    Serial.print(F(",\"offset_raw\":"));
    if (tmp117Present && tmp117OffsetValid) {
        Serial.print(static_cast<int16_t>(tmp117OffsetRaw));
    } else {
        Serial.print(F("null"));
    }
    Serial.print(F(",\"error_count\":")); Serial.print(tmp117ErrorCount);
    Serial.print(F("}"));
    Serial.print(F("}"));

    Serial.print(F(",\"vitals\":{"));
    Serial.print(F("\"heart_rate\":"));
    printNullable(hrValid ? static_cast<float>(currentBpm) : NAN, 0);
    Serial.print(F(",\"heart_rate_status\":\"")); printStatus(heartRateStatus);
    Serial.print(F("\",\"heart_rate_timestamp_ms\":"));
    if (lastHeartRateValidMs > 0) Serial.print(lastHeartRateValidMs); else Serial.print(F("null"));

    Serial.print(F(",\"spo2\":"));
    printNullable(spo2Valid ? static_cast<float>(currentSpO2) : NAN, 0);
    Serial.print(F(",\"spo2_status\":\"")); printStatus(spo2Status);
    Serial.print(F("\",\"spo2_timestamp_ms\":"));
    if (lastSpo2ValidMs > 0) Serial.print(lastSpo2ValidMs); else Serial.print(F("null"));
    Serial.print(F(",\"finger_on\":")); Serial.print(fingerDetected ? F("true") : F("false"));
    Serial.print(F(",\"raw_ir\":"));
    printNullable(maxPresent && lastOpticalSampleMs > 0 && now - lastOpticalSampleMs <= 2000
                      ? static_cast<float>(lastIR) : NAN, 0);
    Serial.print(F(",\"raw_red\":"));
    printNullable(maxPresent && lastOpticalSampleMs > 0 && now - lastOpticalSampleMs <= 2000
                      ? static_cast<float>(lastRed) : NAN, 0);
    Serial.print(F(",\"optical_signal_quality\":\"")); printStatus(opticalQuality);
    Serial.print(F("\",\"optical_perfusion_index\":"));
    printNullable(opticalQuality != nullptr && strcmp(opticalQuality, "good") == 0
                      ? opticalPerfusionIndex : NAN, 2);

    Serial.print(F(",\"tmp117_sensor_temperature_c\":"));
    printNullable(tmpValid ? tmp117TempC : NAN, 2);
    Serial.print(F(",\"tmp117_sensor_temperature_status\":\"")); printStatus(tmp117Status);
    Serial.print(F("\",\"tmp117_sensor_temperature_raw\":"));
    if (tmpValid) Serial.print(tmp117Raw); else Serial.print(F("null"));
    Serial.print(F(",\"tmp117_sensor_temperature_timestamp_ms\":"));
    if (tmpValid) Serial.print(tmp117LastValidMs); else Serial.print(F("null"));

    Serial.print(F(",\"wrist_contact_status\":\"unverified\""));
    Serial.print(F(",\"wrist_skin_temperature_c\":null"));
    Serial.print(F(",\"wrist_skin_temperature_status\":\"unverified\""));
    Serial.print(F(",\"wrist_skin_temperature_raw\":null"));
    Serial.print(F(",\"wrist_skin_temperature_timestamp_ms\":null"));

    Serial.print(F(",\"estimated_core_temperature_c\":null"));
    Serial.print(F(",\"estimated_core_temperature_status\":\"not_available\""));
    Serial.print(F(",\"temp_core\":null"));
    Serial.print(F(",\"temp_skin\":"));
#if RPM_ENABLE_OPTIONAL_MLX90614
    printNullable(mlxPresent && isStatusValid(mlxStatus) ? objectTempC : NAN);
#else
    Serial.print(F("null"));
#endif
    Serial.print(F(",\"temp_object\":"));
#if RPM_ENABLE_OPTIONAL_MLX90614
    printNullable(mlxPresent && isStatusValid(mlxStatus) ? objectTempC : NAN);
#else
    Serial.print(F("null"));
#endif
    Serial.print(F(",\"temp_amb\":"));
#if RPM_ENABLE_OPTIONAL_MLX90614
    printNullable(mlxPresent && isStatusValid(mlxStatus) ? ambientTempC : NAN);
#else
    Serial.print(F("null"));
#endif
    Serial.print(F(",\"sht40_temp_c\":"));
#if RPM_ENABLE_OPTIONAL_SHT40
    printNullable(sht40Present && isStatusValid(sht40Status) ? sht40TempC : NAN);
#else
    Serial.print(F("null"));
#endif
    Serial.print(F(",\"sht40_humidity_pct\":"));
#if RPM_ENABLE_OPTIONAL_SHT40
    printNullable(sht40Present && isStatusValid(sht40Status) ? sht40HumidityPct : NAN);
#else
    Serial.print(F("null"));
#endif

    Serial.print(F(",\"acceleration\":{\"x_g\":"));
    printNullable(imuValid ? accelXG : NAN);
    Serial.print(F(",\"y_g\":")); printNullable(imuValid ? accelYG : NAN);
    Serial.print(F(",\"z_g\":")); printNullable(imuValid ? accelZG : NAN);
    Serial.print(F(",\"magnitude_g\":")); printNullable(imuValid ? currentMotionG : NAN);
    Serial.print(F("}"));
    Serial.print(F(",\"gyroscope\":{\"x_dps\":"));
    printNullable(imuValid ? gyroXDps : NAN);
    Serial.print(F(",\"y_dps\":")); printNullable(imuValid ? gyroYDps : NAN);
    Serial.print(F(",\"z_dps\":")); printNullable(imuValid ? gyroZDps : NAN);
    Serial.print(F(",\"magnitude_dps\":")); printNullable(imuValid ? currentGyroDps : NAN);
    Serial.print(F("}"));
    Serial.print(F(",\"imu_raw\":"));
    if (mpuRawValid) {
        Serial.print(F("{\"accel_counts\":["));
        Serial.print(mpuLastAccelRaw[0]); Serial.print(F(","));
        Serial.print(mpuLastAccelRaw[1]); Serial.print(F(","));
        Serial.print(mpuLastAccelRaw[2]);
        Serial.print(F("],\"gyro_counts\":["));
        Serial.print(mpuLastGyroRaw[0]); Serial.print(F(","));
        Serial.print(mpuLastGyroRaw[1]); Serial.print(F(","));
        Serial.print(mpuLastGyroRaw[2]);
        Serial.print(F("],\"accel_lsb_per_g\":")); Serial.print(MPU_ACCEL_LSB_PER_G, 0);
        Serial.print(F(",\"gyro_lsb_per_dps\":")); Serial.print(MPU_GYRO_LSB_PER_DPS, 0);
        Serial.print(F("}"));
    } else {
        Serial.print(F("null"));
    }
    Serial.print(F(",\"motion_g\":")); printNullable(imuValid ? currentMotionG : NAN);
    Serial.print(F(",\"motion_status\":\"")); printStatus(mpuStatus);
    Serial.print(F("\",\"motion_timestamp_ms\":"));
    if (mpuLastValidMs > 0) Serial.print(mpuLastValidMs); else Serial.print(F("null"));
    Serial.print(F(",\"activity_state\":\"")); printStatus(imuValid ? activityState : SENSOR_NOT_AVAILABLE);
    Serial.print(F("\",\"orientation\":\"")); printStatus(imuValid ? orientationName : SENSOR_NOT_AVAILABLE);
    Serial.print(F("\",\"steps\":"));
    if (imuValid) Serial.print(stepCount); else Serial.print(F("null"));

    Serial.print(F(",\"fever_screening\":{"));
    Serial.print(F("\"status\":\"not_available\""));
    Serial.print(F(",\"message\":\"Core temperature unavailable \xE2\x80\x94 confirmation required\""));
    Serial.print(F(",\"rule\":null"));
    Serial.print(F(",\"input\":{"));
    Serial.print(F("\"measurement\":\"wrist_skin_temperature\""));
    Serial.print(F(",\"value_c\":null"));
    Serial.print(F(",\"unit\":\"C\""));
    Serial.print(F(",\"quality\":\"unverified"));
    Serial.print(F("\",\"measured\":false"));
    Serial.print(F(",\"timestamp_ms\":null"));
    Serial.print(F(",\"raw_register\":null"));
    Serial.print(F("}"));
    Serial.print(F(",\"uncertainty\":\"No validated core-temperature estimate or core reference is available.\""));
    Serial.print(F(",\"limitations\":\"Wrist skin temperature is affected by ambient conditions, blood flow, contact pressure and activity. A wrist reading alone cannot confirm or rule out fever.\""));
    Serial.print(F("}"));
    Serial.print(F("}"));

    Serial.print(F(",\"alerts\":{"));
    Serial.print(F("\"sos\":")); Serial.print(sosActive ? F("true") : F("false"));
    Serial.print(F(",\"fall\":")); Serial.print(fallActive ? F("true") : F("false"));
    Serial.print(F("}"));

    Serial.print(F(",\"status_summary\":\"")); Serial.print(clinicalSummary()); Serial.print(F("\""));
    Serial.println(F("}"));

#if RPM_VERBOSE_TELEMETRY
    Serial.println(F("=============================================================="));
    Serial.print(F(" [RPM PATIENT TELEMETRY | Up: "));
    Serial.print(now / 1000);
    Serial.print(F("s | Risk: "));
    Serial.print(overallRisk());
    Serial.print(F(" | Installed sensors: "));
    Serial.print(activeVitalSensorCount());
    Serial.print(F("/"));
    Serial.print(VITAL_SENSOR_MAX);
    Serial.println(F("]"));
    Serial.print(F("  [MAX30102] HR "));
    if (hrValid) { Serial.print(currentBpm); Serial.print(F(" bpm")); } else Serial.print(F("--"));
    Serial.print(F(" | SpO2 "));
    if (spo2Valid) { Serial.print(currentSpO2); Serial.print(F("%")); } else Serial.print(F("--"));
    Serial.print(F(" | status ")); Serial.print(heartRateStatus);
    Serial.print(F("/")); Serial.println(spo2Status);
    Serial.print(F("  [TMP117] "));
    if (tmpValid) { Serial.print(tmp117TempC, 2); Serial.print(F(" C")); } else Serial.print(F("--"));
    Serial.print(F(" | raw 0x"));
    if (tmp117RawValid) Serial.print(tmp117Raw, HEX); else Serial.print(F("----"));
    Serial.print(F(" | status ")); Serial.print(tmp117Status);
    Serial.print(F(" | error ")); Serial.println(tmp117Error);
    Serial.print(F("  [MPU] accel "));
    if (imuValid) Serial.print(currentMotionG, 2); else Serial.print(F("--"));
    Serial.print(F(" g | gyro "));
    if (imuValid) Serial.print(currentGyroDps, 2); else Serial.print(F("--"));
    Serial.print(F(" dps | ")); Serial.print(activityState);
    Serial.print(F(" | calibration ")); Serial.println(imuCalibration.status);
    Serial.println(F("==============================================================\n"));
#endif
}

// ---------------------------------------------------------------------------
// OLED
// ---------------------------------------------------------------------------
void updateOLED() {
    if (!oledOK) return;
    const bool tmpValid = tmp117ValueValid();
    const bool imuValid = mpuValueValid();
    const bool hrValid = heartRateValueValid();
    const bool spo2Valid = spo2ValueValid();

    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(1);

    if (sosActive || fallActive) {
        display.fillRect(0, 0, SCREEN_WIDTH, 14, SSD1306_WHITE);
        display.setTextColor(SSD1306_BLACK);
        display.setCursor(7, 3);
        display.println(F("! EMERGENCY ALERT !"));
        display.setTextColor(SSD1306_WHITE);
        display.setTextSize(2);
        display.setCursor(6, 22);
        display.println(sosActive ? F("SOS CALL") : F("FALL ALERT"));
        display.setTextSize(1);
        display.setCursor(10, 48);
        display.println(F("ALERT ACTIVE!"));
        display.display();
        Wire.setClock(I2C_PRIMARY_HZ);
        return;
    }

    display.setCursor(0, 0);
    display.print(F("RPM MONITOR  "));
    display.print(activeVitalSensorCount());
    display.print(F("/"));
    display.print(VITAL_SENSOR_MAX);
    display.drawLine(0, 9, SCREEN_WIDTH, 9, SSD1306_WHITE);

    display.setCursor(0, 13);
    display.print(F("HR:"));
    if (hrValid) { display.print(currentBpm); display.print(F("bpm")); }
    else display.print(F("--"));
    display.setCursor(68, 13);
    display.print(F("SpO2:"));
    if (spo2Valid) { display.print(currentSpO2); display.print(F("%")); }
    else display.print(F("--"));

    const bool motionPage = ((millis() / 4000) % 2) != 0;
    if (motionPage) {
        display.setCursor(0, 26);
        display.print(F("Motion:"));
        if (imuValid) { display.print(currentMotionG, 2); display.print(F("g")); }
        else display.print(F("--.-g"));
        display.setCursor(0, 38);
        display.print(F("Gyro:"));
        if (imuValid) { display.print(currentGyroDps, 1); display.print(F("dps")); }
        else display.print(F("--.-dps"));
        display.setCursor(0, 48);
        display.print(F("Steps:"));
        if (imuValid) display.print(stepCount); else display.print(F("--"));
    } else {
        display.setCursor(0, 26);
        display.print(F("TMP:"));
        if (tmpValid) { display.print(tmp117TempC, 1); display.print(F("C")); }
        else display.print(F("--.-C"));
        display.setCursor(0, 38);
        display.print(F("Wrist:"));
        display.print(F("--.-C "));
        display.print(F("UNVERIFIED"));
        display.setCursor(0, 48);
        display.print(F("Core temp unavailable"));
        display.setCursor(0, 56);
        display.print(F("confirmation required"));
    }

    if (motionPage) {
        display.setCursor(0, 56);
        display.print(F("IMU:"));
        display.print(imuValid ? F("OK") : F("ERR"));
        display.setCursor(82, 56);
        display.print(F("SOS:"));
        display.print(digitalRead(BUTTON_PIN) == LOW ? F("ALRT") : F("OK"));
    }

    display.display();
    Wire.setClock(I2C_PRIMARY_HZ);
}

// ---------------------------------------------------------------------------
// I2C scan and hot-plug
// ---------------------------------------------------------------------------
void scanI2CBus() {
    Wire.setClock(I2C_PRIMARY_HZ);
    Serial.println(F("\n[I2C BUS 0 SCAN] GPIO 8 SDA / GPIO 9 SCL at 50 kHz"));
    int count0 = 0;
    for (uint8_t address = 1; address < 127; ++address) {
        Wire.beginTransmission(address);
        if (Wire.endTransmission() == 0) {
            count0++;
            Serial.print(F("    -> 0x"));
            if (address < 16) Serial.print(F("0"));
            Serial.print(address, HEX);
            if (address == 0x3C) Serial.println(F(" : SSD1306 OLED"));
            else if (address == 0x57) Serial.println(F(" : MAX30102"));
            else if (address >= 0x48 && address <= 0x4B) Serial.println(F(" : TMP117 candidate (identity checked)"));
            else if (address == 0x44) Serial.println(F(" : optional/not-installed SHT4x candidate"));
            else if (address == 0x5A) Serial.println(F(" : optional/not-installed MLX90614"));
            else Serial.println(F(" : unknown device"));
        }
    }
    if (count0 == 0) {
        Serial.println(F("    [WARNING] No devices ACKed. Check 3.3 V, GND and GPIO 8/9."));
    }
    Serial.println(F("    Installed expectation: 0x3C OLED, 0x57 MAX30102, one TMP117 in 0x48-0x4B."));

    Serial.println(F("\n[I2C BUS 1 SCAN] GPIO 17 SDA / GPIO 18 SCL at 400 kHz"));
    int count1 = 0;
    Wire1.setClock(I2C_IMU_HZ);
    for (uint8_t address = 1; address < 127; ++address) {
        Wire1.beginTransmission(address);
        if (Wire1.endTransmission() == 0) {
            count1++;
            Serial.print(F("    -> 0x"));
            if (address < 16) Serial.print(F("0"));
            Serial.print(address, HEX);
            if (address == 0x68 || address == 0x69) Serial.println(F(" : MPU-6050/MPU-6500 candidate"));
            else Serial.println(F(" : unknown device"));
        }
    }
    if (count1 == 0) {
        Serial.println(F("    [WARNING] No MPU ACK. Check 3.3 V, GND, SDA=17, SCL=18 and AD0."));
    }
}

void updateSensorsHotplug(uint32_t now) {
    if (now - lastSensorRetry < SENSOR_RETRY_MS) return;
    lastSensorRetry = now;

    Wire.setClock(I2C_PRIMARY_HZ);
    if (!oledOK && sensorResponds(Wire, 0x3C)) {
        if (display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
            oledOK = true;
            Wire.setClock(I2C_PRIMARY_HZ);
            Serial.println(F(">>> [HOT-PLUG] SSD1306 online <<<"));
        }
    }
    if (!mpuPresent) {
        if (initMpu()) {
            Serial.print(F(">>> [HOT-PLUG] MPU online at 0x"));
            Serial.println(mpuAddress, HEX);
            calibrateMpu();
        }
    }
    if (!maxPresent && initMax30102()) {
        Serial.println(F(">>> [HOT-PLUG] MAX30102 online <<<"));
    }
    if (!tmp117Present && initTmp117()) {
        Serial.print(F(">>> [HOT-PLUG] TMP117 online at 0x"));
        Serial.print(tmp117Address, HEX);
        Serial.println(F(" <<<"));
    }
#if RPM_ENABLE_OPTIONAL_SHT40
    if (!sht40Present && initSht40Optional()) {
        Serial.println(F(">>> [HOT-PLUG] optional SHT40 online <<<"));
    }
#endif
#if RPM_ENABLE_OPTIONAL_MLX90614
    if (!mlxPresent && initMlxOptional()) {
        Serial.println(F(">>> [HOT-PLUG] optional MLX90614 online <<<"));
    }
#endif
}

// ---------------------------------------------------------------------------
// Setup and loop
// ---------------------------------------------------------------------------
void setup() {
    // HardwareSerial requires buffer configuration before begin(). Keep the
    // wire baud rate unchanged so the existing bridge/monitor still works.
    Serial.setTxBufferSize(TELEMETRY_TX_BUFFER_BYTES);
    Serial.begin(115200);
    delay(500);

    Serial.println(F("\n=============================================================="));
    Serial.println(F(" IoMT Smart Patient Monitoring Node (ESP32-S3 N16R8)"));
    Serial.println(F(" Real sensors only. Missing values are null, never fabricated."));
    Serial.println(F("=============================================================="));
    Serial.printf("[BOARD] model=%s flash=%u psram=%u bytes\n",
                  ESP.getChipModel(), static_cast<unsigned>(ESP.getFlashChipSize()),
                  static_cast<unsigned>(ESP.getPsramSize()));
    Serial.printf("[SERIAL] TX buffer=%u bytes; telemetry must not block optical sampling\n",
                  static_cast<unsigned>(TELEMETRY_TX_BUFFER_BYTES));
    Serial.print(F("[POLICY] Wrist skin temperature is not core temperature. "));
    Serial.println(F("Core estimate and fever diagnosis are unavailable."));

    Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN, I2C_PRIMARY_HZ);
    Wire.setTimeOut(25);
    Wire1.begin(MPU_SDA_PIN, MPU_SCL_PIN, I2C_IMU_HZ);
    Wire1.setTimeOut(25);

    pinMode(BUTTON_PIN, INPUT_PULLUP);
    Serial.print(F("\n[1] SOS button GPIO 5: "));
    Serial.println(digitalRead(BUTTON_PIN) == HIGH ? F("released/idle") : F("pressed/LOW"));

    scanI2CBus();

    Serial.print(F("\n[2] OLED 0x3C: "));
    if (sensorResponds(Wire, 0x3C) &&
        display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
        oledOK = true;
        Wire.setClock(I2C_PRIMARY_HZ);
        display.clearDisplay();
        display.setTextColor(SSD1306_WHITE);
        display.setTextSize(1);
        display.setCursor(12, 14);
        display.println(F("IoMT Patient Node"));
        display.setCursor(18, 30);
        display.println(F("SYSTEM BOOT OK"));
        display.setCursor(14, 46);
        display.println(F("Live telemetry on"));
        display.display();
        Wire.setClock(I2C_PRIMARY_HZ);
        Serial.println(F("online"));
    } else {
        Serial.println(F("offline (not fatal)"));
    }

    Serial.print(F("    MPU-6050/6500 (GPIO 17/18): "));
    if (initMpu()) {
        Serial.print(F("online at 0x"));
        Serial.print(mpuAddress, HEX);
        Serial.print(F(", WHO_AM_I=0x"));
        Serial.println(mpuWhoAmI, HEX);
        calibrateMpu();
    } else {
        Serial.println(F("offline (check SDA=17, SCL=18, AD0, 3.3 V)"));
    }

    Serial.print(F("    MAX30102 0x57: "));
    Serial.println(initMax30102() ? F("online") : F("offline (check 3.3 V and GPIO 8/9)"));

    Serial.print(F("    TMP117 0x48-0x4B: "));
    if (initTmp117()) {
        Serial.print(F("online at 0x"));
        Serial.print(tmp117Address, HEX);
        Serial.println(F("; raw register conversion is active"));
    } else {
        Serial.println(F("offline (check VIN=3.3 V, GND, SDA=8, SCL=9, ADD)"));
    }

#if RPM_ENABLE_OPTIONAL_SHT40
    Serial.print(F("    optional SHT40 0x44: "));
    Serial.println(initSht40Optional() ? F("online (not counted)") : F("not fitted"));
#else
    Serial.println(F("    optional SHT40: disabled in this build (not installed)"));
#endif
#if RPM_ENABLE_OPTIONAL_MLX90614
    Serial.print(F("    optional MLX90614 0x5A: "));
    Serial.println(initMlxOptional() ? F("online (not counted)") : F("not fitted"));
#else
    Serial.println(F("    optional MLX90614: disabled in this build (not installed)"));
#endif

    Serial.print(F("\n[3] Installed measurement sensors: "));
    Serial.print(activeVitalSensorCount());
    Serial.print(F("/"));
    Serial.print(VITAL_SENSOR_MAX);
    Serial.println(F(" online"));
    Serial.print(F("    MAX30102=")); Serial.print(maxPresent ? F("ONLINE") : F("OFFLINE"));
    Serial.print(F("  MPU=")); Serial.print(mpuPresent ? F("ONLINE") : F("OFFLINE"));
    Serial.print(F("  TMP117=")); Serial.println(tmp117Present ? F("ONLINE") : F("OFFLINE"));
    Serial.println(F("    OLED is a display, not a measurement sensor."));
    Serial.println(F("    SHT40 and MLX90614 are not installed and are not counted."));
    Serial.println(F("\n SYSTEM READY. Press SOS on GPIO 5 for an emergency event.\n"));

    lastReportTime = millis();
    lastFastTick = millis();
    lastSensorRetry = millis();
    outputTelemetry();
}

void loop() {
    uint32_t now = millis();

    if (sosActive && now >= sosClearTime) sosActive = false;
    if (fallActive && now >= fallClearTime) fallActive = false;

    static int lastButtonState = HIGH;
    static uint32_t lastButtonPress = 0;
    int buttonState = digitalRead(BUTTON_PIN);
    if (buttonState == LOW && lastButtonState == HIGH &&
        now - lastButtonPress > 300) {
        lastButtonPress = now;
        if (!sosActive) {
            sosActive = true;
            sosClearTime = now + 15000;
            Serial.println(F("\n>>> [EMERGENCY SOS] Patient pressed the button. <<<"));
            outputTelemetry(true);
            updateOLED();
        } else {
            sosActive = false;
            sosClearTime = 0;
            Serial.println(F("\n>>> [SOS CANCELLED] Button pressed again. <<<"));
            outputTelemetry(true);
            updateOLED();
        }
    }
    lastButtonState = buttonState;

    if (now - lastFastTick >= MPU_READ_INTERVAL_MS) {
        lastFastTick = now;
        updateMpu(now);
    }

    sampleOptical(now);
    updateTmp117(now);
#if RPM_ENABLE_OPTIONAL_SHT40
    static uint32_t lastShtRead = 0;
    if (sht40Present && now - lastShtRead >= 3000) {
        lastShtRead = now;
        updateSht40Optional();
    }
#endif
#if RPM_ENABLE_OPTIONAL_MLX90614
    static uint32_t lastMlxRead = 0;
    if (mlxPresent && now - lastMlxRead >= 1000) {
        lastMlxRead = now;
        updateMlxOptional(now);
    }
#endif

    if (now - lastReportTime >= 1000) {
        lastReportTime = now;
        refreshSensorStatuses(now);
        updateSensorsHotplug(now);

        Wire.setClock(I2C_PRIMARY_HZ);
        if (oledOK && !sensorResponds(Wire, 0x3C)) oledOK = false;
        if (maxPresent && !sensorResponds(Wire, 0x57)) {
            maxPresent = false;
            maxError = "i2c_address_nack";
            resetOpticalState(SENSOR_NOT_AVAILABLE, SENSOR_NOT_AVAILABLE);
        }

        // Promptly reflect a removed TMP117 before its next 2 s sample is due.
        if (tmp117Present && !sensorResponds(Wire, tmp117Address)) {
            tmp117Present = false;
            tmp117Status = SENSOR_NOT_AVAILABLE;
            tmp117Error = "i2c_address_nack";
            tmp117TempC = NAN;
            tmp117RawValid = false;
            tmp117OffsetValid = false;
        }

        outputTelemetry();
        updateOLED();
    }
}
