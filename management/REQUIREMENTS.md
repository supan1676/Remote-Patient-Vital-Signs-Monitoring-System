# System Requirements Specification & Traceability

- Document ID: MGT-REQ-001
- Version: 1.0.0
- Date: 2026-11-01
- Project: Remote Patient Vital Signs Monitoring System (RPMIOMTproject)
- Author: Chief Engineering Manager & Verification Specialist Agent

---

## 1. Requirement Taxonomy & Status Definitions

Requirements are organized into functional domains:
- **SYS-xxx**: System-level integration and operational requirements
- **HW-xxx**: Hardware, electrical, wiring, and power requirements
- **FW-xxx**: Microcontroller firmware, I2C, and scheduler requirements
- **SENS-xxx**: Sensor driver, data extraction, and signal quality requirements
- **BE-xxx**: Backend bridge, validation, database, and API requirements
- **UI-xxx**: Dashboard, visualization, and alerting requirements
- **SAFE-xxx**: Clinical safety, boundary enforcement, and failure protection requirements
- **TEST-xxx**: Automated testing, verification, and regression requirements
- **DOC-xxx**: Engineering documentation, test guides, and architecture manuals

### Verification Status Codes
- **PASS**: Verified by passing automated tests and/or direct software/hardware proof.
- **PARTIAL**: Implemented in code and passes unit tests, but awaiting bench hardware validation.
- **FAIL**: Verified failure in current testing or benchmark.
- **BLOCKED**: Implementation or test blocked by hardware dependency or missing component.
- **NOT RUN**: Test or procedure has not yet been executed.

---

## 2. Requirements Matrix

### System-Level (SYS)

| ID | Title | Description & Acceptance Criteria | Verification Method | Status |
|---|---|---|---|---|
| **SYS-001** | End-to-End Vital Monitoring | Continuous monitoring of temperature, heart rate, SpO2, and physical activity with live telemetry transmission to local computer. | Integration Run | **PARTIAL** |
| **SYS-002** | Zero Measurement Fabrication | Under no circumstances shall the system output, store, or display fabricated, simulated, or placeholder vital numbers when genuine physical data is missing or low quality. | Automated Tests | **PASS** |
| **SYS-003** | Sensor Disconnection Resilience | The disconnection of any individual sensor (TMP117, MAX30102, MPU-6050, OLED) shall not crash the firmware, lock up the I2C bus, or halt the processing of remaining active sensors. | Firmware Unit / Hot-Plug | **PARTIAL** |
| **SYS-004** | Telemetry Transport Integrity | Serial JSON telemetry packets shall include sequence numbers, device timestamps, and complete sensor status flags, with strict UTF-8 JSON parsing. | Pytest Bridge Tests | **PASS** |

### Hardware & Electrical (HW)

| ID | Title | Description & Acceptance Criteria | Verification Method | Status |
|---|---|---|---|---|
| **HW-001** | Core Microcontroller | ESP32-S3 N16R8 (16MB Flash, 8MB PSRAM) operating at 3.3V logic levels. | Board Config Check | **PASS** |
| **HW-002** | Primary I2C Bus Isolation | Primary bus (GPIO 8 SDA, GPIO 9 SCL) dedicated to MAX30102 (0x57), TMP117 (0x48-0x4B), and SSD1306 OLED (0x3C) at 50kHz clock rate. | Pin Verification | **PASS** |
| **HW-003** | Secondary I2C Bus Isolation | Secondary bus (GPIO 17 SDA, GPIO 18 SCL) dedicated to MPU-6050 (0x68) running at 400kHz fast mode. | Pin Verification | **PASS** |
| **HW-004** | 3.3V Power Integrity & Decoupling | All connected modules must be powered from 3.3V (NOT 5V). MAX30102 power rail requires decoupling to absorb optical LED pulse currents. | Hardware Audit / Bench | **PARTIAL** |
| **HW-005** | SOS Emergency Button | Physical momentary button wired to GPIO 5 with internal pull-up and hardware debouncing. | Code Review & Bench | **PARTIAL** |

### Firmware (FW)

| ID | Title | Description & Acceptance Criteria | Verification Method | Status |
|---|---|---|---|---|
| **FW-001** | Non-Blocking Main Loop | The main loop shall execute at ~10-20ms tick intervals, polling MPU-6050 at 50Hz, servicing MAX30102 FIFO, and scheduling TMP117 reads at 0.5Hz without blocking delays. | Firmware Audit | **PASS** |
| **FW-002** | Compile-Time Math Asserts | All raw-to-physical conversion formulas and bit masks in `src/sensor_math.h` and `src/tmp117_protocol.h` must be validated by `static_assert` statements. | PlatformIO Build | **PASS** |
| **FW-003** | Automatic I2C Bus Recovery | If an I2C transaction fails or hangs, the firmware must execute bus reset sequences to clear stuck SDA/SCL lines. | Firmware Review | **PASS** |
| **FW-004** | JSON Serialization | Telemetry serialization must generate valid JSON packets conforming strictly to the schema accepted by `telemetry_bridge.py`. | Bridge Schema Tests | **PASS** |

### Sensor Drivers & Signal Processing (SENS)

| ID | Title | Description & Acceptance Criteria | Verification Method | Status |
|---|---|---|---|---|
| **SENS-001** | TMP117 Device Discovery | Dynamic discovery across addresses 0x48–0x4B with verification that `WHO_AM_I == 0x0117`. Must detect 7SEMI module at 0x49. | PlatformIO Diagnostic | **PASS** |
| **SENS-002** | TMP117 16-Bit Conversion | Raw 16-bit signed conversion with 0.0078125°C resolution, rejecting 0x0000 and 0xFFFF stuck bus states. | Pytest Vector Tests | **PASS** |
| **SENS-003** | MAX30102 Part Verification | Startup verification of `PART_ID == 0x15` before optical initialization. | Code & Build | **PASS** |
| **SENS-004** | MAX30102 PPG Windowing | 100-sample raw buffer for HR/SpO2 calculation with 25-sample sliding window updates. | Firmware Audit | **PASS** |
| **SENS-005** | Optical Signal Quality Gate | Red/IR DC mean ≥ 50,000, AC amplitude ≥ 1,000, and Perfusion Index ≥ 0.10%. Flag `low_quality` if failed. | Pytest & Static Asserts | **PASS** |
| **SENS-006** | Optical State Persistence | Prevent partial window filling from erroneously resetting completed results back to `warming_up`. | Unit Tests & Code Audit | **PASS** |
| **SENS-007** | MPU-6050 Scale & Calibration | Configure ±8g accelerometer and ±250°/s gyro; calibrate rest offsets on boot. | Firmware Review | **PASS** |
| **SENS-008** | Two-Stage Fall Detection | Free-fall phase (<0.6g) followed by impact phase (>2.5g) within 60–600ms window triggers emergency fall state. | Code & Vector Tests | **PARTIAL** |

### Backend & Persistence (BE)

| ID | Title | Description & Acceptance Criteria | Verification Method | Status |
|---|---|---|---|---|
| **BE-001** | Strict Inbound Validation | `telemetry_bridge.py` rejects malformed JSON, impossible physiological ranges, contradictory statuses, and unverified data. | Pytest Suite (25+ tests) | **PASS** |
| **BE-002** | SQLite Time-Series Store | `telemetry_store.py` logs valid telemetry losslessly with timestamps, sequence IDs, and automatic schema migrations. | Pytest DB Tests | **PASS** |
| **BE-003** | Diagnostic Column Retention | TMP117 diagnostic values retained in `observations` table (`tmp117_sensor_temperature`, etc.) without corrupting clinical wrist records. | Pytest History Tests | **PASS** |
| **BE-004** | Personal Baseline Engine | Rolling 7-day statistical engine computing mean, standard deviation, and anomaly thresholds per patient. | Pytest Baseline Tests | **PASS** |
| **BE-005** | Multi-Tier Decision Alerts | Rule-based engine categorizing vitals into Normal, Cautionary, and Critical alert events. | Pytest Engine Tests | **PASS** |

### Dashboard & UI (UI)

| ID | Title | Description & Acceptance Criteria | Verification Method | Status |
|---|---|---|---|---|
| **UI-001** | Real-Time Telemetry Streaming | Web UI updates vitals, charts, and health badges in real-time via Server-Sent Events (SSE). | Node Core Tests & Browser | **PASS** |
| **UI-002** | Zero-Value Masking | Missing, unverified, or warming-up sensor values display clear status text ("--", "Warming up", "Not connected") and NEVER substitute 0 or prior values. | Node Core Tests (10/10) | **PASS** |
| **UI-003** | Discontinuous Chart Rendering | Line charts break paths across missing/invalid intervals rather than drawing interpolated lines through null points. | Node Core Tests | **PASS** |
| **UI-004** | Diagnostic vs Clinical Display | The UI explicitly distinguishes raw TMP117 diagnostic sensor readings from clinical wrist skin temperature. | Node Core Tests | **PASS** |

### Clinical Safety & Risk Controls (SAFE)

| ID | Title | Description & Acceptance Criteria | Verification Method | Status |
|---|---|---|---|---|
| **SAFE-001** | Non-Clinical Disclaimer | Dashboard and documentation prominently state that this is a digital engineering prototype and NOT a certified medical diagnostic device. | UI & Doc Review | **PASS** |
| **SAFE-002** | Temperature Safety Isolation | `wrist_skin_temperature_c` is null until contact is physically verified. `estimated_core_temperature_c` is permanently null. Fever screening is disabled. | Pytest & JS Tests | **PASS** |
| **SAFE-003** | SOS & Fall Emergency Priority | Emergency button presses and fall detection events immediately elevate telemetry packet priority and UI alert banners. | Pytest & Integration | **PARTIAL** |

### Verification & Documentation (TEST / DOC)

| ID | Title | Description & Acceptance Criteria | Verification Method | Status |
|---|---|---|---|---|
| **TEST-001** | Automated Test Regression | Full test suite (`pytest` and `node --test`) must run and pass 100% on demand. | Automated Script | **PASS** |
| **TEST-002** | Firmware Compilation Integrity | PlatformIO build for ESP32-S3 and all diagnostic targets must succeed with zero errors. | PlatformIO Build | **PASS** |
| **DOC-001** | Hardware Test Guide | Comprehensive, reproducible step-by-step instructions for bench testing physical sensors with exact terminal commands. | Document Inspection | **PASS** |
| **DOC-002** | Video Reference Analysis | Analysis document comparing 4 engineering reference videos against project implementation. | Document Inspection | **PASS** |

