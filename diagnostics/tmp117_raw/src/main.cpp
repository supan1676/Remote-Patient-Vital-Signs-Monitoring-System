/**
 * Standalone TMP117 raw-register diagnostic
 *
 * This sketch intentionally does not use the Adafruit TMP117 library. It uses
 * checked raw Wire transactions so an I2C error can never be mistaken for a
 * temperature. It prints WHO_AM_I, configuration, offset, raw bytes and the
 * signed conversion for several minutes.
 *
 * Wiring (same as the main node):
 *   TMP117 VIN -> 3.3 V (not 5 V)
 *   TMP117 GND -> GND
 *   TMP117 SDA -> GPIO 8
 *   TMP117 SCL -> GPIO 9
 *   TMP117 ADD -> GND (address 0x48) or leave strapping as fitted
 *
 * Build:   pio run -d diagnostics/tmp117_raw
 * Upload:  pio run -d diagnostics/tmp117_raw -t upload --upload-port COMx
 * Monitor: pio device monitor -d diagnostics/tmp117_raw --port COMx
 *
 * Leave it running for at least five minutes, including a period where the
 * normal firmware previously reported about -0.01 C. Save the complete serial
 * log; it contains only sensor diagnostics, not patient identifiers.
 */

#include <Arduino.h>
#include <Wire.h>

#include "../../../src/tmp117_protocol.h"

#define DIAG_SDA 8
#define DIAG_SCL 9
#define DIAG_I2C_HZ 50000UL
#define DIAG_SAMPLE_MS 1000UL

namespace {

enum class ReadResult : uint8_t {
  OK,
  ADDRESS_NACK,
  DATA_NACK,
  OTHER_ERROR,
  SHORT_READ
};

ReadResult readBytes(uint8_t address, uint8_t reg, uint8_t* out, uint8_t len) {
  Wire.beginTransmission(address);
  Wire.write(reg);
  uint8_t end = Wire.endTransmission(false);
  if (end == 2) return ReadResult::ADDRESS_NACK;
  if (end == 3) return ReadResult::DATA_NACK;
  if (end != 0) return ReadResult::OTHER_ERROR;

  uint8_t received = static_cast<uint8_t>(
      Wire.requestFrom(static_cast<int>(address), static_cast<int>(len)));
  if (received != len) {
    while (Wire.available()) Wire.read();
    return ReadResult::SHORT_READ;
  }
  for (uint8_t i = 0; i < len; ++i) {
    if (!Wire.available()) return ReadResult::SHORT_READ;
    out[i] = static_cast<uint8_t>(Wire.read());
  }
  return ReadResult::OK;
}

const char* resultName(ReadResult result) {
  switch (result) {
    case ReadResult::OK: return "ok";
    case ReadResult::ADDRESS_NACK: return "address_nack";
    case ReadResult::DATA_NACK: return "data_nack";
    case ReadResult::OTHER_ERROR: return "bus_error";
    case ReadResult::SHORT_READ: return "short_read";
    default: return "unknown";
  }
}

bool readWord(uint8_t address, uint8_t reg, uint16_t& value, ReadResult& result) {
  uint8_t bytes[2] = {0, 0};
  result = readBytes(address, reg, bytes, 2);
  if (result != ReadResult::OK) return false;
  value = tmp117::wordFromBigEndianBytes(bytes[0], bytes[1]);
  return true;
}

bool writeWord(uint8_t address, uint8_t reg, uint16_t value, ReadResult& result) {
  Wire.beginTransmission(address);
  Wire.write(reg);
  Wire.write(static_cast<uint8_t>(value >> 8));
  Wire.write(static_cast<uint8_t>(value & 0xFF));
  uint8_t end = Wire.endTransmission(true);
  result = end == 2 ? ReadResult::ADDRESS_NACK
                    : end == 3 ? ReadResult::DATA_NACK
                    : end == 0 ? ReadResult::OK : ReadResult::OTHER_ERROR;
  return result == ReadResult::OK;
}

bool responds(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

void printHex16(uint16_t value) {
  Serial.print(F("0x"));
  if (value < 0x1000) Serial.print(F("0"));
  if (value < 0x0100) Serial.print(F("0"));
  if (value < 0x0010) Serial.print(F("0"));
  Serial.print(value, HEX);
}

void printResult(ReadResult result) {
  Serial.print(resultName(result));
}

void scanBus() {
  Serial.println(F("\n[SCAN] Primary I2C bus GPIO 8 SDA / GPIO 9 SCL at 50 kHz"));
  uint8_t found = 0;
  for (uint8_t address = 1; address < 127; ++address) {
    if (!responds(address)) continue;
    found++;
    Serial.print(F("  ACK 0x"));
    if (address < 16) Serial.print(F("0"));
    Serial.print(address, HEX);
    if (address == 0x48 || address == 0x49 || address == 0x4A ||
        address == 0x4B) {
      Serial.println(F(" (TMP117 address candidate)"));
    } else if (address == 0x3C) {
      Serial.println(F(" (OLED; ignore for this diagnostic)"));
    } else if (address == 0x57) {
      Serial.println(F(" (MAX30102; ignore for this diagnostic)"));
    } else {
      Serial.println(F(" (other/unexpected)"));
    }
  }
  if (found == 0) {
    Serial.println(F("  No ACK. Check 3.3 V, common GND, SDA=GPIO8, SCL=GPIO9."));
  }
}

uint8_t findTmp117(uint16_t& deviceId, ReadResult& lastResult) {
  lastResult = ReadResult::ADDRESS_NACK;
  for (uint8_t address : {0x48, 0x49, 0x4A, 0x4B}) {
    if (!responds(address)) continue;
    ReadResult result = ReadResult::OK;
    uint16_t id = 0;
    if (!readWord(address, tmp117::REG_DEVICE_ID, id, result)) {
      lastResult = result;
      Serial.print(F("[ID] 0x"));
      if (address < 16) Serial.print(F("0"));
      Serial.print(address, HEX);
      Serial.print(F(" WHO_AM_I read failed: "));
      printResult(result);
      Serial.println();
      continue;
    }
    Serial.print(F("[ID] 0x"));
    if (address < 16) Serial.print(F("0"));
    Serial.print(address, HEX);
    Serial.print(F(" WHO_AM_I="));
    printHex16(id);
    if (id == tmp117::DEVICE_ID_TMP117) {
      Serial.println(F(" -> TMP117 confirmed"));
      deviceId = id;
      lastResult = ReadResult::OK;
      return address;
    }
    Serial.println(F(" -> not the expected TMP117 value 0x0117"));
  }
  return 0;
}

uint8_t sensorAddress = 0;
uint16_t sensorId = 0;

void configureSensor(uint8_t address, bool announceBeforeChange) {
  ReadResult result = ReadResult::OK;
  if (announceBeforeChange) {
    Serial.print(F("\n[CONFIG] Reading 0x01 before change: "));
    uint16_t before = 0;
    if (readWord(address, tmp117::REG_CONFIGURATION, before, result)) {
      printHex16(before);
      Serial.println();
    } else {
      Serial.print(F("failed (")); printResult(result); Serial.println(F(")"));
    }
  }

  Serial.print(F("[CONFIG] Writing continuous / 8 averages / 500 ms: "));
  printHex16(tmp117::CONFIG_CONTINUOUS_8AVG_500MS);
  Serial.println();
  if (!writeWord(address, tmp117::REG_CONFIGURATION,
                 tmp117::CONFIG_CONTINUOUS_8AVG_500MS, result)) {
    Serial.print(F("[CONFIG] Write failed: ")); printResult(result);
    Serial.println(F("; will continue with read-only diagnostics."));
    return;
  }
  delay(5);

  uint16_t after = 0;
  if (readWord(address, tmp117::REG_CONFIGURATION, after, result)) {
    Serial.print(F("[CONFIG] Readback: ")); printHex16(after);
    Serial.print(F("  writable_mask_match="));
    Serial.println((after & tmp117::CONFIG_WRITABLE_MASK) ==
                           (tmp117::CONFIG_CONTINUOUS_8AVG_500MS &
                            tmp117::CONFIG_WRITABLE_MASK)
                       ? F("yes") : F("NO"));
  } else {
    Serial.print(F("[CONFIG] Readback failed: ")); printResult(result); Serial.println();
  }

  uint16_t offset = 0;
  if (readWord(address, tmp117::REG_TEMPERATURE_OFFSET, offset, result)) {
    Serial.print(F("[OFFSET] Register 0x07 raw=")); printHex16(offset);
    Serial.print(F(" signed=")); Serial.print(static_cast<int16_t>(offset));
    Serial.print(F(" offset_c=")); Serial.println(tmp117::celsiusFromRawCode(offset), 5);
  }
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println(F("\n=============================================================="));
  Serial.println(F(" TMP117 RAW REGISTER DIAGNOSTIC"));
  Serial.println(F(" No Adafruit TMP117 library; failed reads are shown as errors."));
  Serial.println(F("=============================================================="));
  Serial.print(F(" Firmware build: "));
  Serial.println(F(__DATE__ " " __TIME__));

  Wire.begin(DIAG_SDA, DIAG_SCL, DIAG_I2C_HZ);
  Wire.setClock(DIAG_I2C_HZ);
  Wire.setTimeOut(25);
  scanBus();

  ReadResult result = ReadResult::OK;
  sensorAddress = findTmp117(sensorId, result);
  if (sensorAddress == 0) {
    Serial.println(F("\n[FAIL] No TMP117 responded with WHO_AM_I 0x0117."));
    Serial.println(F("       Check address strapping, power, ground and bus pull-ups."));
    Serial.println(F("       The diagnostic will retry the scan every 5 seconds."));
    return;
  }

  configureSensor(sensorAddress, true);

  Serial.println(F("\n[DECODE] raw is signed 16-bit big-endian, 1 LSB = 0.0078125 C."));
  Serial.println(F("         A raw value of 0xFFFF converts to -0.0078125 C and is flagged below."));
  Serial.println(F("         Leave this sketch running for at least five minutes.\n"));
  delay(600);
}

void loop() {
  static uint32_t lastSample = 0;
  static uint32_t lastScan = 0;
  static uint32_t successful = 0;
  static uint32_t failed = 0;
  static uint32_t allOnes = 0;
  static uint32_t allZeros = 0;
  static uint32_t notReady = 0;
  static float minimumC = 1e9f;
  static float maximumC = -1e9f;
  uint32_t now = millis();

  if (sensorAddress == 0) {
    if (now - lastScan < 5000) return;
    lastScan = now;
    ReadResult result = ReadResult::OK;
    sensorAddress = findTmp117(sensorId, result);
    if (sensorAddress == 0) return;
    Serial.print(F("[RETRY] TMP117 found at 0x"));
    if (sensorAddress < 16) Serial.print(F("0"));
    Serial.println(sensorAddress, HEX);
    configureSensor(sensorAddress, false);
    delay(600);
  }

  if (now - lastSample < DIAG_SAMPLE_MS) return;
  lastSample = now;

  uint16_t configuration = 0;
  ReadResult configResult = ReadResult::OK;
  bool configOk = readWord(sensorAddress, tmp117::REG_CONFIGURATION,
                           configuration, configResult);
  bool dataReady = configOk &&
                   (configuration & tmp117::CONFIG_DATA_READY_MASK) != 0;
  if (!dataReady) notReady++;

  uint16_t raw = 0;
  ReadResult rawResult = ReadResult::OK;
  bool rawOk = readWord(sensorAddress, tmp117::REG_TEMPERATURE, raw, rawResult);

  Serial.print(F("["));
  Serial.print(now);
  Serial.print(F(" ms] addr=0x"));
  if (sensorAddress < 16) Serial.print(F("0"));
  Serial.print(sensorAddress, HEX);
  Serial.print(F(" cfg="));
  if (configOk) printHex16(configuration); else { Serial.print(F("ERR(")); printResult(configResult); Serial.print(F(")")); }
  Serial.print(F(" drdy="));
  Serial.print(dataReady ? F("1") : F("0"));

  if (!rawOk) {
    failed++;
    Serial.print(F(" temp_read=ERR("));
    printResult(rawResult);
    Serial.println(F(")  <-- no conversion; value is NOT zero"));
    if (rawResult == ReadResult::ADDRESS_NACK) {
      Serial.println(F("[RETRY] TMP117 stopped acknowledging; rescanning in 5 s."));
      sensorAddress = 0;
    }
    return;
  }

  successful++;
  int16_t signedRaw = tmp117::signedTemperatureCode(raw);
  float celsius = tmp117::celsiusFromRawCode(raw);
  if (tmp117::isStuckBusPattern(raw)) {
    if (raw == 0xFFFF) allOnes++; else allZeros++;
  }
  if (celsius < minimumC) minimumC = celsius;
  if (celsius > maximumC) maximumC = celsius;

  Serial.print(F(" raw="));
  printHex16(raw);
  // Show the two bytes separately in transfer order (MSB first).
  Serial.print(F(" [msb=0x")); Serial.print(raw >> 8, HEX);
  Serial.print(F(" lsb=0x")); Serial.print(raw & 0xFF, HEX); Serial.print(F("]"));
  Serial.print(F(" signed=")); Serial.print(signedRaw);
  Serial.print(F(" temp_c=")); Serial.print(celsius, 5);

  if (raw == 0xFFFF) {
    Serial.print(F("  <-- ALL_ONES: classic released/failed-bus pattern"));
  } else if (raw == 0x0000) {
    Serial.print(F("  <-- ALL_ZEROS: stuck-low/failed-read pattern"));
  } else if (!tmp117::isWithinSensorRange(celsius)) {
    Serial.print(F("  <-- OUTSIDE TMP117 SENSOR RANGE"));
  } else {
    Serial.print(F("  OK"));
  }
  Serial.println();

  static uint32_t lastSummary = 0;
  if (now - lastSummary >= 30000) {
    lastSummary = now;
    Serial.print(F("[SUMMARY] successful=")); Serial.print(successful);
    Serial.print(F(" read_failures=")); Serial.print(failed);
    Serial.print(F(" all_ones=")); Serial.print(allOnes);
    Serial.print(F(" all_zeros=")); Serial.print(allZeros);
    Serial.print(F(" data_not_ready=")); Serial.print(notReady);
    Serial.print(F(" min_c="));
    if (minimumC < 1e8f) Serial.print(minimumC, 5); else Serial.print(F("n/a"));
    Serial.print(F(" max_c="));
    if (maximumC > -1e8f) Serial.print(maximumC, 5); else Serial.print(F("n/a"));
    Serial.println();
  }
}
