# Sensor Implementation, Audit & Root Cause Analysis

- Document ID: MGT-SIR-001
- Version: 1.1.0 (Evidence-Corrected)
- Date: 2026-11-02
- Project: Remote Patient Vital Signs Monitoring System (RPMIOMTproject)
- Author: Chief Engineering Manager, Embedded & Hardware Specialist Agents

---

## 1. Executive Summary & Evaluation Grid

This report provides an evidence-based assessment of all sensors in the RPMIOMTproject.
To avoid confusing software builds with physical reality:
- **Software verification** (unit tests, static asserts, compilation) is **complete and passing**.
- **Physical hardware verification** requires live bench execution by the developer.

### Sensor Verification Grid (8 Explicit Dimensions)

Status codes strictly limited to: **PASS**, **PARTIAL**, **FAIL**, **BLOCKED**, and **NOT RUN**.

| Evaluation Dimension | TMP117 (Temp) | MAX30102 (PPG) | MPU-6050 (IMU) | SSD1306 (OLED) | SOS Button | MLX90614 (IR) | SHT40 (Humidity) |
|---|---|---|---|---|---|---|---|
| **A. Code implementation status** | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** (Disabled) | **PASS** (Disabled) |
| **B. Automated test status** | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** |
| **C. Firmware build status** | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** |
| **D. Physical device detection status** | **PARTIAL** | **PARTIAL** | **PARTIAL** | **PARTIAL** | **PARTIAL** | **BLOCKED** | **BLOCKED** |
| **E. Genuine raw measurement status** | **PARTIAL** | **PARTIAL** | **PARTIAL** | **NOT RUN** | **NOT RUN** | **BLOCKED** | **BLOCKED** |
| **F. Valid measurement status** | **PARTIAL** | **NOT RUN** | **PARTIAL** | **NOT RUN** | **NOT RUN** | **BLOCKED** | **BLOCKED** |
| **G. Integrated dashboard status** | **FAIL** | **PARTIAL** | **PASS** | **NOT RUN** | **PARTIAL** | **BLOCKED** | **BLOCKED** |
| **H. Reference-device validation status** | **NOT RUN** | **NOT RUN** | **NOT RUN** | **NOT RUN** | **NOT RUN** | **BLOCKED** | **BLOCKED** |

---

## 2. TMP117 Precision Temperature Sensor Audit

### 2.1 Silicon Specifications & Register Architecture
- **I2C Addresses**: 7-bit addresses `0x48` to `0x4B`. Breakout strapped to `0x49`.
- **Identification**: Register `0x0F` returns `0x0117`.
- **Temperature Register (`0x00`)**: 16-bit signed two's complement, big-endian format.
- **Conversion Factor**: LSB = $0.0078125^\circ\text{C}$ ($1/128^\circ\text{C}$). Verified by 14 static assertions.
- **Configuration (`0x01`)**: `0x01A0` (continuous mode, 500ms cycle time, 8-sample hardware averaging).
- **Data Ready Bit**: Bit 13 of Configuration register. Checked before reading temperature.

### 2.2 Root Cause Analysis: The "Disappearing TMP117" Phenomenon
In historical integrated runs, TMP117 was detected at boot, but disappeared after a few seconds, returning `i2c_address_nack`.

#### Known Historical Facts:
1. **Standalone Test (`diagnostics/tmp117_raw`)**:
   - TMP117 was detected at `0x49` (`WHO_AM_I=0x0117`).
   - Ran stably for >30 seconds with 0 I2C errors, outputting ~26.0°C to 26.8°C.
2. **Integrated Firmware Boot**:
   - Boot scan detected TMP117 at `0x49` and produced one reading of `26.84°C` at `uptime_s=3`.
   - At `uptime_s=4`, the bus transaction to `0x49` returned `i2c_address_nack`.
   - Dashboard subsequently displayed `"Not connected"`.

#### Status of the Root Cause:
**THIS IS AN UNPROVEN HYPOTHESIS, NOT A CONFIRMED FACT.**

Three competing hypotheses exist:
1. **Breadboard Power Droop (Hypothesis)**: When the MAX30102 optical LEDs pulse (~50mA peaks), a localized voltage dip on the breadboard 3.3V rail may cause the TMP117 digital core to brown out or reset.
2. **I2C Bus Recovery / Speed Conflict (Hypothesis)**: Sequential initialization of SSD1306 (which alters clock timing) and MAX30102 may leave the bus in an unrecovered state.
3. **Physical Wiring / Contact Resistance (Hypothesis)**: Marginal breadboard spring contacts or loose jumper wires on the power or I2C rails.

#### Diagnostic Staging Status:
Three build environments were configured in `diagnostics/tmp117_with_max/platformio.ini`:
- `tmp117-max-stage1`: Tests bus presence only (MAX30102 `begin()` without LED configuration).
- `tmp117-max-stage2`: Tests optical setup with LEDs disabled (0 mA current).
- `tmp117-max-stage3`: Tests optical setup with operational LED pulse current (`0x24` / ~7.2 mA).

> [!IMPORTANT]
> These three diagnostic targets have been **compiled successfully**, but they **HAVE NOT BEEN EXECUTED ON PHYSICAL HARDWARE** in this audit. Until the user flashes each stage and captures the serial log, the root cause remains unconfirmed.

---

## 3. MAX30102 Optical PPG Sensor Audit

### 3.1 Firmware Implementation & Math
- **I2C Address**: Fixed 7-bit `0x57`. Checks `PART_ID == 0x15` in register `0xFF`.
- **LED Currents**: Set to `0x24` (~7.2 mA) for Red and IR channels.
- **ADC Dynamic Range**: 4096 counts, pulse width 411 µs (18-bit resolution).
- **Sampling Rate & Averaging**: 100 Hz raw sample rate with 4-sample averaging (`SMP_AVE = 4`), yielding an effective rate of **25 samples per second**.
- **Buffer Processing**: 100-sample window (4.0 seconds) evaluated with Maxim's algorithm, followed by 25-sample sliding updates (1.0 second refresh rate).

### 3.2 Bug Fixed in Code: State Machine Oscillation
- In `src/sensor_math.h`, implemented `sensor_math::opticalWindowIsWarming()` and verified via static assertions.
- This prevents a completed window result from reverting to `"warming_up"` during sliding buffer refills.

### 3.3 Physical Reality Check
- **What is proven**: The firmware compiles; when no finger is present, ambient light (<50,000 counts) correctly yields `null` vitals and `"warming_up"` / `"low_quality"` status.
- **What is UNPROVEN**: Whether placing an actual human finger on the sensor produces a genuine PPG pulsatile waveform, satisfies the AC/DC quality gate ($AC \ge 1000$, $PI \ge 0.10\%$), and produces valid Heart Rate and SpO2 numbers. **This requires a physical bench test**.

---

## 4. MPU-6050 Inertial Measurement Unit Audit

### 4.1 Bus Architecture & Configuration
- **Hardware Bus**: Dedicated secondary I2C bus (`Wire1`, GPIO 17 SDA, GPIO 18 SCL) operating at 400kHz fast mode.
- **I2C Address**: `0x68`. Accepts `WHO_AM_I` values of `0x68` and `0x70`.
- **Scale Ranges**: Accelerometer $\pm 8\text{g}$ ($4096\text{ LSB/g}$); Gyroscope $\pm 250^\circ/\text{s}$ ($131.0\text{ LSB/}(\text{deg/s})$).
- **Sampling**: Polled at 50Hz (20ms interval).

### 4.2 Physical Reality Check
- **What is proven**: Reading ~1.0g resting gravity vector when stationary was confirmed in the historical integrated run.
- **What is UNPROVEN**: The gyroscope axes, rest offset calibration accuracy under motion, and the two-stage fall detection algorithm (<0.6g free-fall followed by >2.5g impact within 600ms) have **never been tested with physical motion or impacts**.

---

## 5. SSD1306 128x64 OLED Display Audit

- **Hardware Bus**: Primary I2C bus (`Wire`, GPIO 8/9), address `0x3C`.
- **Code Status**: Initialized at 50kHz clock rate; alternates pages every 4 seconds in software between vitals and environmental metrics.
- **Physical Reality Check**: Compiling the driver does **not** prove the physical glass screen displays readable text, that contrast is adequate, or that the display updates without corrupting pixels. **Visual bench inspection required**.

---

## 6. SOS Push Button (GPIO 5)

- **Code Status**: Configured with internal pull-up and 50ms software debouncing in `src/main.cpp`.
- **Physical Reality Check**: Physical switch closure to ground and end-to-end telemetry alert latching on the dashboard have **never been physically tested on the bench**.
