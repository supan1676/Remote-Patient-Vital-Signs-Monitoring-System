# Engineering Toolchain & Build Specification

- Document ID: MGT-TOL-001
- Version: 1.0.0
- Date: 2026-11-01
- Project: Remote Patient Vital Signs Monitoring System (RPMIOMTproject)
- Author: Chief Engineering Manager & Embedded Specialist Agent

---

## 1. Verified Host Environment

- **Operating System**: Microsoft Windows 11 Home / Pro (64-bit)
- **Host System**: ASUS TUF Gaming F15 FX506HC (Intel Core i5-11400H @ 2.70GHz, 16 GB RAM)
- **Primary Shell**: Windows PowerShell (`powershell.exe`)
- **Version Control**: Git version 2.52.0.windows.1

---

## 2. Software Runtime & Language Toolchains

### Python Environment
- **Version**: Python 3.12.10 (64-bit)
- **Package Manager**: pip 26.0
- **Key Installed Dependencies**:
  - `pyserial`: Serial communication bridge to ESP32-S3
  - `pytest`: Automated test runner
  - `ruff`: Python linter and static code analysis
  - `sqlite3`: Native database engine for telemetry persistence

### Node.js JavaScript Environment
- **Version**: Node.js v24.19.0 (64-bit)
- **Built-in Test Runner**: `node --test` (standard ES2022+ module runner)
- **Execution Target**: Headless unit verification of `assets/dashboard_core.js`

### PlatformIO Embedded Toolchain
- **Core Version**: PlatformIO Core 6.2.0 / Home 3.4.4
- **Embedded Platform**: `espressif32` @ version 7.1.0
- **Framework**: `arduino` (framework-arduinoespressif32 @ 3.20017.241212+sha.dcc1105b)
- **Compiler**: `toolchain-xtensa-esp32s3` @ 8.4.0+2021r2-patch5
- **Flash Tool**: `tool-esptoolpy` @ 2.41100.260830 (4.11.0)
- **Embedded Libraries**:
  - `Adafruit SSD1306` @ 2.5.17
  - `Adafruit GFX Library` @ 1.13.0
  - `Adafruit Unified Sensor` @ 1.1.15
  - `SparkFun MAX3010x Pulse and Proximity Sensor Library` @ 1.1.2
  - `Wire` @ 2.0.0

---

## 3. PlatformIO Build Target Profiles

### Production Firmware (`platformio.ini`)
```ini
[env:esp32-s3-devkitc-1]
platform = espressif32
board = esp32-s3-devkitc-1-n16r8
framework = arduino
monitor_speed = 115200
board_build.partitions = default_16MB.csv
build_flags = 
    -DARDUINO_USB_CDC_ON_BOOT=1
    -DARDUINO_USB_MODE=1
lib_deps = 
    adafruit/Adafruit SSD1306 @ ^2.5.13
    sparkfun/SparkFun MAX3010x Pulse and Proximity Sensor Library @ ^1.1.2
```

### Staged Coexistence Diagnostics (`diagnostics/tmp117_with_max/platformio.ini`)
1. `tmp117-max-stage1`: MAX30102 bus presence & PART_ID check only.
2. `tmp117-max-stage2`: Full MAX30102 configuration with pulse amplitude = `0x00` (LEDs off).
3. `tmp117-max-stage3`: Full MAX30102 configuration with pulse amplitude = `0x24` (~7.2mA pulses).

---

## 4. Standard Operational Commands

### Automated Test Execution
```powershell
# Run Python backend and protocol test suite (64 tests)
python -m pytest -q

# Run JavaScript dashboard core headless test suite (10 tests)
node --test tests/dashboard_core.test.js
```

### Firmware Build Commands
```powershell
# Build integrated production firmware
pio run -e esp32-s3-devkitc-1

# Build standalone TMP117 diagnostic firmware
pio run -d diagnostics/tmp117_raw

# Build staged coexistence diagnostic environments
pio run -d diagnostics/tmp117_with_max -e tmp117-max-stage1
pio run -d diagnostics/tmp117_with_max -e tmp117-max-stage2
pio run -d diagnostics/tmp117_with_max -e tmp117-max-stage3
```

