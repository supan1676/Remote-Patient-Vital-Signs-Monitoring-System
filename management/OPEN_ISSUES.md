# Open Issues & Bench Verification Ledger

- Document ID: MGT-ISS-001
- Version: 1.1.0 (Evidence-Corrected)
- Date: 2026-11-02
- Project: Remote Patient Vital Signs Monitoring System (RPMIOMTproject)
- Author: Chief Engineering Manager

---

## 1. Issue Status Summary

| Issue ID | Category | Severity | Description | Current Status |
|---|---|---|---|---|
| **ISS-001** | Hardware / Power | High | TMP117 I2C NACK in integrated firmware after boot. | **UNCONFIRMED HYPOTHESIS — AWAITING BENCH RUN** |
| **ISS-002** | Sensor / Optical | High | MAX30102 HR/SpO2 vital calculation unverified with finger. | **AWAITING BENCH TEST** |
| **ISS-003** | Sensor / IMU | Medium | MPU-6050 fall detection, gyro, and dynamic range unverified. | **AWAITING BENCH TEST** |
| **ISS-004** | Display / Hardware | Low | SSD1306 OLED physical pixel rendering unverified. | **AWAITING BENCH TEST** |
| **ISS-005** | Input / Hardware | Low | Physical SOS push button to dashboard alert unverified. | **AWAITING BENCH TEST** |
| **ISS-006** | Third-Party Library | Low | SparkFun MAX3010x macro `I2C_BUFFER_LENGTH` redefinition. | **OPEN / NON-FATAL** |

---

## 2. Detailed Issue Ledger

### ISS-001: TMP117 Disappearance in Integrated Firmware
- **Subsystem**: I2C Bus 0 / Electrical Power Distribution
- **Observed Behavior (Historical)**:
  - TMP117 was detected at boot (`0x49`, `WHO_AM_I=0x0117`) and produced one valid reading of `26.84°C` at `uptime_s=3`.
  - At `uptime_s=4`, the bus transaction to `0x49` returned `i2c_address_nack`.
  - The dashboard displayed `"Not connected"`.
- **Root Cause Status**: **UNPROVEN HYPOTHESIS**.
  - *Hypothesis 1 (Electrical)*: Breadboard 3.3V rail voltage droop occurs when the MAX30102 optical pulse LEDs fire (~50mA peaks), causing the TMP117 digital logic to brown out or reset.
  - *Hypothesis 2 (Bus Contention / Timing)*: SSD1306 OLED initialization alters I2C clock timing, or `Wire.setClock(50000)` creates an unrecovered bus state.
  - *Hypothesis 3 (Physical)*: Loose jumper wire or contact resistance on the breadboard power rails.
- **Diagnostic Tool Created**: 3 staged diagnostic targets in `diagnostics/tmp117_with_max/` (`tmp117-max-stage1`, `tmp117-max-stage2`, `tmp117-max-stage3`).
  - *Note*: These targets have been compiled, but **have NOT yet been flashed or executed on physical hardware**.
- **Action Required**: Execute the staged diagnostic sequence on hardware to observe whether Stage 1, 2, or 3 triggers the NACK.

---

### ISS-002: MAX30102 Optical Vital Calculation with Physical Finger
- **Subsystem**: MAX30102 Optical Pipeline & Signal Quality Gate
- **Observed Behavior**:
  - The firmware correctly reports `"warming_up"` when uncontacted, and rejects ambient light signals that fall below the DC floor (<50,000) or AC threshold (<1,000).
  - The state-machine oscillation bug was resolved in `sensor_math.h`.
- **Unverified Status**:
  - The system has **never** been tested with a human finger placed on the optical sensor.
  - It is currently **unproven** whether the sensor will successfully transition from `"warming_up"` to `"valid"` and output genuine BPM and SpO2 numbers on the physical setup.
- **Action Required**: User places an index finger steadily on the sensor for 8 seconds while monitoring serial telemetry or dashboard.

---

### ISS-003: MPU-6050 Dynamic Motion, Gyroscope & Fall Detection
- **Subsystem**: Inertial Measurement Unit (Wire1, GPIO 17/18)
- **Observed Behavior**:
  - Read approximately 1.0g resting acceleration magnitude when stationary on a desk during historical integrated run.
- **Unverified Status**:
  - Stationary ~1.0g does not validate the gyroscope axes, dynamic range, rest offset calibration accuracy, or the two-stage fall detection algorithm (<0.6g free-fall followed by >2.5g impact).
- **Action Required**: Bench tilt/shake test and controlled soft drop test to verify dynamic acceleration and fall alert latching.

---

### ISS-004: SSD1306 OLED Physical Display Operation
- **Subsystem**: Primary I2C Display (Address 0x3C)
- **Observed Behavior**:
  - The Adafruit SSD1306 driver initializes in code and compiles without errors.
- **Unverified Status**:
  - Physical text rendering, page alternation, and display contrast on the glass screen have not been visually verified in this audit session.
- **Action Required**: Visual inspection of the physical OLED screen during boot and runtime.

---

### ISS-005: SOS Push Button Physical Event Pipeline
- **Subsystem**: GPIO 5 Input Pull-Up
- **Observed Behavior**:
  - Software debouncing (50ms) and toggle logic are implemented in `src/main.cpp`. Telemetry bridge correctly parses `sos_active`.
- **Unverified Status**:
  - Physical button depression, circuit continuity to ground, and end-to-end dashboard alert latching have not been triggered on hardware.
- **Action Required**: Depress the physical push button on the breadboard and observe the serial log and dashboard emergency banner.

---

### ISS-006: Third-Party SparkFun Macro Warning
- **Subsystem**: Toolchain (`libdeps`)
- **Observed Behavior**: Preprocessor warning regarding `I2C_BUFFER_LENGTH` redefinition (32 vs 128).
- **Status**: Non-fatal upstream library behavior. Does not affect compilation success or buffer integrity. No code change needed.
