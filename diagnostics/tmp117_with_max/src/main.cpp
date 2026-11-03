/**
 * Focused TMP117 / MAX30102 coexistence diagnostic.
 *
 * This intentionally mirrors the main firmware's primary-bus setup:
 *   - Wire on GPIO 8/9 at 50 kHz
 *   - MAX30102 initialized with the same SparkFun configuration
 *   - TMP117 discovered by identity, not by a hard-coded address
 *
 * It then keeps polling the MAX30102 FIFO while logging TMP117 transactions.
 * The purpose is to distinguish a TMP117 hardware/power/wiring problem from an
 * interaction with the MAX30102 or OLED. It never fabricates a temperature or
 * a pulse reading.
 *
 * Build/upload from the repository root. The explicit stage environments avoid
 * source edits:
 *   pio run -d diagnostics/tmp117_with_max -e tmp117-max-stage2
 *   pio run -d diagnostics/tmp117_with_max -e tmp117-max-stage2 -t upload --upload-port COM6
 *   pio device monitor -d diagnostics/tmp117_with_max -e tmp117-max-stage2 --port COM6
 *
 * Use tmp117-max-stage1 (identity only) and tmp117-max-stage3 (production LED
 * current) for the other two isolation points.
 */

#include <Arduino.h>
#include <Wire.h>

#include <MAX30105.h>

#include "../../../src/tmp117_protocol.h"

#ifndef DIAG_ENABLE_MAX
#define DIAG_ENABLE_MAX 1
#endif
#ifndef DIAG_ENABLE_OLED
#define DIAG_ENABLE_OLED 0
#endif
#ifndef DIAG_MAX_STAGE
// 1 = begin/identity only; 2 = full setup with LEDs off; 3 = full setup and
// FIFO polling with the production LED current.
#define DIAG_MAX_STAGE 3
#endif

#if DIAG_ENABLE_OLED
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
Adafruit_SSD1306 display(128, 64, &Wire, -1);
#endif

#define DIAG_SDA 8
#define DIAG_SCL 9
#define DIAG_I2C_HZ 50000UL
#define DIAG_SAMPLE_MS 1000UL
#define DIAG_SCAN_MS 5000UL

MAX30105 max30102;

namespace {

enum class ReadResult : uint8_t {
  OK,
  ADDRESS_NACK,
  DATA_NACK,
  OTHER_ERROR,
  SHORT_READ
};

ReadResult resultFromEnd(uint8_t end) {
  switch (end) {
    case 0: return ReadResult::OK;
    case 2: return ReadResult::ADDRESS_NACK;
    case 3: return ReadResult::DATA_NACK;
    default: return ReadResult::OTHER_ERROR;
  }
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

ReadResult readBytes(uint8_t address, uint8_t reg, uint8_t* out, uint8_t len) {
  Wire.beginTransmission(address);
  Wire.write(reg);
  ReadResult result = resultFromEnd(Wire.endTransmission(false));
  if (result != ReadResult::OK) return result;

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

ReadResult readWord(uint8_t address, uint8_t reg, uint16_t& value) {
  uint8_t bytes[2] = {0, 0};
  ReadResult result = readBytes(address, reg, bytes, 2);
  if (result != ReadResult::OK) return result;
  value = tmp117::wordFromBigEndianBytes(bytes[0], bytes[1]);
  return ReadResult::OK;
}

ReadResult writeWord(uint8_t address, uint8_t reg, uint16_t value) {
  Wire.beginTransmission(address);
  Wire.write(reg);
  Wire.write(static_cast<uint8_t>(value >> 8));
  Wire.write(static_cast<uint8_t>(value & 0xFF));
  return resultFromEnd(Wire.endTransmission(true));
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

void scanPrimaryBus() {
  Serial.println(F("\n[SCAN] Primary I2C bus GPIO 8/9 at 50 kHz"));
  uint8_t found = 0;
  for (uint8_t address = 1; address < 127; ++address) {
    if (!responds(address)) continue;
    found++;
    Serial.print(F("  ACK 0x"));
    if (address < 16) Serial.print(F("0"));
    Serial.print(address, HEX);
    if (address == 0x49 || address == 0x48 || address == 0x4A ||
        address == 0x4B) {
      Serial.println(F(" (TMP117 candidate)"));
    } else if (address == 0x57) {
      Serial.println(F(" (MAX30102)"));
    } else if (address == 0x3C) {
      Serial.println(F(" (OLED)"));
    } else {
      Serial.println(F(" (other)"));
    }
  }
  if (found == 0) Serial.println(F("  No device ACKed."));
}

uint8_t findTmp117(uint16_t& deviceId) {
  deviceId = 0;
  for (uint8_t address : {0x48, 0x49, 0x4A, 0x4B}) {
    if (!responds(address)) continue;
    uint16_t id = 0;
    ReadResult result = readWord(address, tmp117::REG_DEVICE_ID, id);
    Serial.print(F("[ID] 0x"));
    if (address < 16) Serial.print(F("0"));
    Serial.print(address, HEX);
    Serial.print(F(" WHO_AM_I="));
    if (result == ReadResult::OK) {
      printHex16(id);
      Serial.println();
    } else {
      Serial.print(F("read_failed("));
      Serial.print(resultName(result));
      Serial.println(F(")"));
    }
    if (result == ReadResult::OK && id == tmp117::DEVICE_ID_TMP117) {
      deviceId = id;
      return address;
    }
  }
  return 0;
}

uint8_t tmp117Address = 0;
uint16_t tmp117Id = 0;
long lastMaxIr = 0;
long lastMaxRed = 0;
uint32_t maxSamples = 0;

void initMax30102() {
#if DIAG_ENABLE_MAX
  Serial.print(F("[MAX] begin: "));
  if (!max30102.begin(Wire, I2C_SPEED_STANDARD)) {
    Serial.println(F("FAILED"));
    return;
  }
  uint8_t partId = max30102.readPartID();
  Serial.print(F("PART_ID=0x"));
  Serial.print(partId, HEX);
  if (partId != 0x15) {
    Serial.println(F(" (unexpected; leaving MAX inactive)"));
    return;
  }
#if DIAG_MAX_STAGE >= 2
  max30102.setup(0x24, 4, 2, 100, 411, 4096);
  Wire.setClock(DIAG_I2C_HZ);
#if DIAG_MAX_STAGE >= 3
  max30102.setPulseAmplitudeRed(0x24);
  max30102.setPulseAmplitudeIR(0x24);
  Serial.println(F(" configured; LEDs at 0x24"));
#else
  max30102.setPulseAmplitudeRed(0x00);
  max30102.setPulseAmplitudeIR(0x00);
  Serial.println(F(" configured; LEDs at 0x00"));
#endif
  max30102.clearFIFO();
#else
  Serial.println(F(" identity only; setup/LEDs untouched"));
#endif
#else
  Serial.println(F("[MAX] disabled by build flag; LEDs are not driven"));
#endif
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println(F("\n=============================================================="));
  Serial.println(F(" TMP117 / MAX30102 COEXISTENCE DIAGNOSTIC"));
  Serial.println(F(" No fabricated temperature or pulse values."));
  Serial.println(F("=============================================================="));
  Serial.print(F(" Firmware build: "));
  Serial.println(F(__DATE__ " " __TIME__));

  Wire.begin(DIAG_SDA, DIAG_SCL, DIAG_I2C_HZ);
  Wire.setClock(DIAG_I2C_HZ);
  Wire.setTimeOut(25);
  scanPrimaryBus();

#if DIAG_ENABLE_OLED
  Serial.print(F("[OLED] begin: "));
  if (display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(0, 0);
    display.println(F("TMP/MAX diagnostic"));
    display.display();
    Serial.println(F("online"));
  } else {
    Serial.println(F("offline"));
  }
  Wire.setClock(DIAG_I2C_HZ);
#endif

  initMax30102();
  scanPrimaryBus();

  tmp117Address = findTmp117(tmp117Id);
  if (tmp117Address == 0) {
    Serial.println(F("[FAIL] TMP117 identity not found at startup."));
  } else {
    uint16_t configuration = 0;
    ReadResult result = readWord(tmp117Address, tmp117::REG_CONFIGURATION,
                                 configuration);
    Serial.print(F("[TMP] address=0x"));
    if (tmp117Address < 16) Serial.print(F("0"));
    Serial.print(tmp117Address, HEX);
    Serial.print(F(" config_before="));
    if (result == ReadResult::OK) printHex16(configuration);
    else Serial.print(resultName(result));
    Serial.println();

    result = writeWord(tmp117Address, tmp117::REG_CONFIGURATION,
                       tmp117::CONFIG_CONTINUOUS_8AVG_500MS);
    if (result != ReadResult::OK) {
      Serial.print(F("[TMP] config write failed: "));
      Serial.println(resultName(result));
    } else {
      delay(5);
      uint16_t readback = 0;
      result = readWord(tmp117Address, tmp117::REG_CONFIGURATION, readback);
      Serial.print(F("[TMP] config_readback="));
      if (result == ReadResult::OK) {
        printHex16(readback);
        Serial.print(F(" writable_mask_match="));
        Serial.println((readback & tmp117::CONFIG_WRITABLE_MASK) ==
                               (tmp117::CONFIG_CONTINUOUS_8AVG_500MS &
                                tmp117::CONFIG_WRITABLE_MASK)
                           ? F("yes") : F("NO"));
      } else {
        Serial.print(resultName(result));
        Serial.println();
      }
    }
    delay(600);
  }

  Serial.println(F("[READY] MAX FIFO polling and TMP117 reads are active."));
}

void loop() {
  static uint32_t lastTmp = 0;
  static uint32_t lastScan = 0;
  static uint32_t lastPrint = 0;
  uint32_t now = millis();

#if DIAG_ENABLE_MAX && DIAG_MAX_STAGE >= 3
  max30102.check();
  while (max30102.available()) {
    lastMaxIr = max30102.getFIFOIR();
    lastMaxRed = max30102.getFIFORed();
    max30102.nextSample();
    maxSamples++;
  }
#endif

  if (now - lastScan >= DIAG_SCAN_MS) {
    lastScan = now;
    Serial.print(F("[STATUS] max_samples="));
    Serial.print(maxSamples);
    Serial.print(F(" last_ir="));
    Serial.print(lastMaxIr);
    Serial.print(F(" last_red="));
    Serial.println(lastMaxRed);
    scanPrimaryBus();
  }

  if (now - lastTmp < DIAG_SAMPLE_MS) return;
  lastTmp = now;

  if (tmp117Address == 0) {
    tmp117Address = findTmp117(tmp117Id);
    if (tmp117Address == 0) {
      Serial.println(F("[TMP] not present with identity 0x0117"));
      return;
    }
  }

  uint16_t configuration = 0;
  ReadResult configResult = readWord(
      tmp117Address, tmp117::REG_CONFIGURATION, configuration);
  bool ready = configResult == ReadResult::OK &&
               (configuration & tmp117::CONFIG_DATA_READY_MASK) != 0;

  uint16_t raw = 0;
  ReadResult rawResult = readWord(
      tmp117Address, tmp117::REG_TEMPERATURE, raw);

  Serial.print(F("[TMP] cfg="));
  if (configResult == ReadResult::OK) printHex16(configuration);
  else Serial.print(resultName(configResult));
  Serial.print(F(" drdy="));
  Serial.print(ready ? F("1") : F("0"));
  Serial.print(F(" raw="));
  if (rawResult == ReadResult::OK) {
    printHex16(raw);
    Serial.print(F(" temp_c="));
    Serial.print(tmp117::celsiusFromRawCode(raw), 5);
  } else {
    Serial.print(F("ERR("));
    Serial.print(resultName(rawResult));
    Serial.print(F(")"));
  }
  Serial.print(F(" | max_ir="));
  Serial.print(lastMaxIr);
  Serial.print(F(" max_red="));
  Serial.println(lastMaxRed);

  if (configResult == ReadResult::ADDRESS_NACK ||
      rawResult == ReadResult::ADDRESS_NACK) {
    Serial.println(F("[TMP] ADDRESS_NACK observed; rescanning at next second."));
    tmp117Address = 0;
  }
}
