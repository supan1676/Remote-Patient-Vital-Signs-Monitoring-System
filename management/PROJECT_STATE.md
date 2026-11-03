# PROJECT STATE — Remote Patient Vital Signs Monitoring System
> Audit & Engineering Evidence Baseline: 2026-11-02

---

## 1. Executive Status & Ground Rules

This project state reflects **verified evidence only**. 

To maintain strict scientific and engineering integrity:
1. **Compilation != Physical Execution**: Compiling firmware or diagnostic code cleanly proves syntax, type safety, and symbol resolution; it does **not** prove physical execution on hardware.
2. **Unit Tests != Physical Hardware Operation**: 64 passing Python tests and 10 passing Node.js tests prove mathematical conversions, JSON serialization, database schema rules, and UI masking logic; they do **not** prove physical sensor operation.
3. **No-Finger Detection != Vital Sign Measurement**: A MAX30102 reporting "warming up" or "low quality" when bare only proves the DC floor gate works on ambient light; it does **not** prove that heart rate or SpO2 can be extracted from a human finger.
4. **Resting 1g != Fall Detection Validation**: An accelerometer reporting ~1g when lying stationary on a desk proves rest gravity alignment; it does **not** prove gyroscope accuracy, dynamic calibration, or the two-stage fall detection algorithm.
5. **Firmware Frame Buffering != Physical OLED Operation**: Initializing the SSD1306 driver and cycling memory pages in RAM does **not** prove that pixels are rendered on the physical glass display.
6. **Debounce Logic != Physical SOS Switch**: Software debouncing on GPIO 5 does **not** prove the physical button, wiring, or end-to-end alert latching works.
7. **Voltage Droop is a Hypothesis**: Breadboard supply droop under optical LED pulse current is an **unconfirmed hypothesis**. It has not been verified with an oscilloscope, logic analyzer, or multi-stage bench runs.

---

## 2. Sensor-by-Sensor Comprehensive Status Grid

Status values are strictly restricted to: **PASS**, **PARTIAL**, **FAIL**, **BLOCKED**, and **NOT RUN**.

| Evaluation Dimension | TMP117 (Temp) | MAX30102 (PPG) | MPU-6050 (IMU) | SSD1306 (OLED) | SOS Button | MLX90614 (IR Temp) | SHT40 (Humidity) |
|---|---|---|---|---|---|---|---|
| **A. Code implementation status** | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** (Disabled) | **PASS** (Disabled) |
| **B. Automated test status** | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** |
| **C. Firmware build status** | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** |
| **D. Physical device detection status** | **PARTIAL** | **PARTIAL** | **PARTIAL** | **PARTIAL** | **PARTIAL** | **BLOCKED** | **BLOCKED** |
| **E. Genuine raw measurement status** | **PARTIAL** | **PARTIAL** | **PARTIAL** | **NOT RUN** | **NOT RUN** | **BLOCKED** | **BLOCKED** |
| **F. Valid measurement status** | **PARTIAL** | **NOT RUN** | **PARTIAL** | **NOT RUN** | **NOT RUN** | **BLOCKED** | **BLOCKED** |
| **G. Integrated dashboard status** | **FAIL** | **PARTIAL** | **PASS** | **NOT RUN** | **PARTIAL** | **BLOCKED** | **BLOCKED** |
| **H. Reference-device validation status** | **NOT RUN** | **NOT RUN** | **NOT RUN** | **NOT RUN** | **NOT RUN** | **BLOCKED** | **BLOCKED** |

### Evidence Notes for Status Classifications:

- **TMP117**:
  - *D. Detection (PARTIAL)*: Detected at `0x49` in historical standalone test and at boot `uptime_s=3`; but returned I2C address NACK at `uptime_s=4` in integrated firmware. Not run on hardware in current session.
  - *E. Raw Measurements (PARTIAL)*: Historical raw readings `0x0CFF` (~25.99°C) and `0x0CFE` (~26.05°C) recorded in standalone test; lost during integrated run.
  - *F. Valid Measurements (PARTIAL)*: Valid in standalone run; failed in integrated run.
  - *G. Dashboard (FAIL)*: Displayed "Not connected" and "--" on live dashboard during historical integrated run.
  - *H. Reference Validation (NOT RUN)*: Never compared against a NIST/calibrated medical reference thermometer.

- **MAX30102**:
  - *D. Detection (PARTIAL)*: Detected at `0x57` with `PART_ID = 0x15` at boot; not run on hardware in current session.
  - *E. Raw Measurements (PARTIAL)*: Ambient light raw Red/IR counts read at boot; authentic pulsatile AC waveform from human fingertip has NOT been captured.
  - *F. Valid Measurements (NOT RUN)*: Never generated a valid heart rate or SpO2 reading on physical hardware.
  - *G. Dashboard (PARTIAL)*: Correctly displayed "Warming up" and "--" when uncontacted, but has never displayed valid vitals.
  - *H. Reference Validation (NOT RUN)*: Never benchmarked against a clinical pulse oximeter.

- **MPU-6050**:
  - *D. Detection (PARTIAL)*: Detected at `0x68` in historical integrated run; not run on hardware in current session.
  - *E. Raw Measurements (PARTIAL)*: Raw acceleration at rest read (~1.0g); dynamic raw acceleration and angular rates during motion/impact not captured.
  - *F. Valid Measurements (PARTIAL)*: Stationary 1.0g confirmed; two-stage fall detection (<0.6g then >2.5g within 600ms) has NOT been physically executed.
  - *G. Dashboard (PASS)*: Motion magnitude and status successfully transmitted and plotted on live dashboard in historical integrated run.
  - *H. Reference Validation (NOT RUN)*: No reference IMU or calibration shaker table used.

- **SSD1306 OLED**:
  - *D. Detection (PARTIAL)*: Detected at `0x3C` in historical scan; not run on hardware in current session.
  - *E, F, G. Display Output (NOT RUN)*: Frame buffers transfer over I2C in code, but physical visual rendering on the glass display has not been verified by optical inspection.
  - *H. Reference Validation (NOT RUN)*: No display measurement equipment used.

- **SOS Push Button**:
  - *D. Detection (PARTIAL)*: GPIO 5 pull-up configured in software; physical electrical continuity not verified on bench in current session.
  - *E, F. Measurements (NOT RUN)*: Physical button press to ground has not been recorded on hardware.
  - *G. Dashboard (PARTIAL)*: Backend and UI handle `sos_active` flag, but physical end-to-end trigger has not been executed.
  - *H. Reference Validation (NOT RUN)*: Not applicable.

- **MLX90614 & SHT40**:
  - *All physical dimensions (BLOCKED)*: Sensors are physically absent from the breadboard. Correctly compiled out.

---

## 3. Host Environment & Build Verification

All software build verification succeeded on 2026-11-01 / 2026-11-02:

| Subsystem / Tool | Version / Command | Software Status |
|---|---|---|
| **OS** | Windows 11 Home / Pro (ASUS TUF Gaming F15) | Verified |
| **Python** | 3.12.10 (`pytest -q`) | **64 passed** in 0.24s |
| **Node.js** | v24.19.0 (`node --test`) | **10 passed** in 74ms |
| **PlatformIO Core** | 6.2.0 | Installed |
| **Main Firmware Build** | `pio run -e esp32-s3-devkitc-1` | **SUCCESS** (RAM: 6.5%, Flash: 5.0%) |
| **TMP117 Raw Diagnostic** | `pio run -d diagnostics/tmp117_raw` | **SUCCESS** |
| **Coexistence Diag Stage 1** | `pio run -d diagnostics/tmp117_with_max -e tmp117-max-stage1` | **SUCCESS** |
| **Coexistence Diag Stage 2** | `pio run -d diagnostics/tmp117_with_max -e tmp117-max-stage2` | **SUCCESS** |
| **Coexistence Diag Stage 3** | `pio run -d diagnostics/tmp117_with_max -e tmp117-max-stage3` | **SUCCESS** |

---

## 4. Open Engineering Problems

1. **P-01: TMP117 Address NACK in Integrated Firmware** (Severity: HIGH)
   - *Status*: Open. Unresolved on physical hardware.
   - *Working Hypothesis*: Breadboard 3.3V power droop during optical LED firing, I2C bus recovery timing, or pull-up resistance mismatch. Not yet proven on bench.
2. **P-02: MAX30102 Zero Measurement Proof** (Severity: HIGH)
   - *Status*: Open. Firmware state oscillation bug is fixed in software, but physical measurement with human fingertip has not been executed.
3. **P-03: MPU-6050 Fall Detection & Gyroscope Unverified** (Severity: MEDIUM)
   - *Status*: Open. Only static 1.0g rest acceleration verified historically.
4. **P-04: OLED Physical Rendering Unverified** (Severity: LOW)
   - *Status*: Open. Driver builds, but physical glass display unverified.
5. **P-05: SOS Button End-to-End Event Unverified** (Severity: LOW)
   - *Status*: Open. GPIO debouncing implemented, but physical contact unverified.
