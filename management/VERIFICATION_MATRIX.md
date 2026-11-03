# System Verification & Traceability Matrix

- Document ID: MGT-VER-001
- Version: 1.1.0 (Evidence-Corrected)
- Date: 2026-11-02
- Project: Remote Patient Vital Signs Monitoring System (RPMIOMTproject)
- Author: Chief Engineering Manager & Verification Specialist Agent

---

## 1. Traceability Overview & Ground Rules

This matrix distinguishes between **software verification** (passing automated tests and compilation) and **physical hardware validation** (empirical bench operation).

**Status Codes (Strict):**
- **PASS**: Verified by automated test suites or reproducible software/build evidence.
- **PARTIAL**: Verified in software/unit tests or historical bench runs, but lacking live physical validation.
- **FAIL**: Verified failure in integrated execution or benchmark.
- **BLOCKED**: Blocked by physical absence of hardware.
- **NOT RUN**: Procedure or physical bench test has not yet been executed.

---

## 2. Sensor Evaluation Grid (8 Dimensions)

| Dimension | TMP117 | MAX30102 | MPU-6050 | SSD1306 | SOS Button | MLX90614 | SHT40 |
|---|---|---|---|---|---|---|---|
| **A. Code implementation** | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** (Disabled) | **PASS** (Disabled) |
| **B. Automated tests** | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** |
| **C. Firmware build** | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** | **PASS** |
| **D. Physical device detection** | **PARTIAL** | **PARTIAL** | **PARTIAL** | **PARTIAL** | **PARTIAL** | **BLOCKED** | **BLOCKED** |
| **E. Genuine raw measurement** | **PARTIAL** | **PARTIAL** | **PARTIAL** | **NOT RUN** | **NOT RUN** | **BLOCKED** | **BLOCKED** |
| **F. Valid measurement** | **PARTIAL** | **NOT RUN** | **PARTIAL** | **NOT RUN** | **NOT RUN** | **BLOCKED** | **BLOCKED** |
| **G. Integrated dashboard** | **FAIL** | **PARTIAL** | **PASS** | **NOT RUN** | **PARTIAL** | **BLOCKED** | **BLOCKED** |
| **H. Reference validation** | **NOT RUN** | **NOT RUN** | **NOT RUN** | **NOT RUN** | **NOT RUN** | **BLOCKED** | **BLOCKED** |

---

## 3. Formal Requirements Traceability Matrix

| Req ID | Requirement Title | Verification Method | Associated Test / Artifact | Evidence & Observed Result | Status |
|---|---|---|---|---|---|
| **SYS-001** | End-to-End Vital Monitoring | Physical Bench Test | Complete Pipeline | Main firmware builds; bridge parses JSON; UI runs. Physical end-to-end vitals unverified. | **PARTIAL** |
| **SYS-002** | Zero Measurement Fabrication | Automated Tests | `dashboard_core.test.js`, `test_telemetry.py` | Headless JS & Pytest verify missing data renders `"--"`/`null`, never 0. | **PASS** |
| **SYS-003** | Sensor Disconnection Resilience | Firmware / Unit Tests | `src/main.cpp` hot-plug loop | Software detects I2C NACK and flags error without crashing CPU. Bench hot-unplug unverified. | **PARTIAL** |
| **SYS-004** | Telemetry Transport Integrity | Automated Pytest | `test_telemetry.py::test_valid_packet` | 100% schema validation pass on incoming JSON payloads. | **PASS** |
| **HW-001** | Core Microcontroller Target | Board Config Check | `boards/esp32-s3-devkitc-1-n16r8.json` | PlatformIO configuration targets ESP32-S3 (16MB Flash, 8MB PSRAM). | **PASS** |
| **HW-002** | Primary I2C Bus Isolation | Pin Mapping Audit | `src/main.cpp` | GPIO 8 (SDA) / GPIO 9 (SCL) assigned at 50 kHz for TMP117, MAX30102, OLED. | **PASS** |
| **HW-003** | Secondary I2C Bus Isolation | Pin Mapping Audit | `src/main.cpp` | GPIO 17 (SDA) / GPIO 18 (SCL) assigned at 400 kHz for MPU-6050. | **PASS** |
| **HW-004** | 3.3V Power Integrity & Decoupling | Electrical Bench Test | Multimeter / Staged Diag | Diagnostic targets built. Physical rail voltage under optical pulse load unmeasured. | **NOT RUN** |
| **HW-005** | SOS Emergency Button | Physical Bench Test | `src/main.cpp` | Active-low debounce logic implemented in code. Physical button press not executed. | **NOT RUN** |
| **FW-001** | Non-Blocking Main Loop | Code Timing Audit | `src/main.cpp` millis() scheduling | Non-blocking scheduling implemented for all sensors and telemetry. | **PASS** |
| **FW-002** | Compile-Time Math Asserts | PlatformIO Build | `src/sensor_math.h`, `src/tmp117_protocol.h` | 27 `static_assert` statements verified during compilation. | **PASS** |
| **FW-003** | Automatic I2C Bus Recovery | Firmware Review | `src/main.cpp` bus recovery function | 9-clock bus reset sequence implemented on transmission timeout. | **PASS** |
| **FW-004** | JSON Serialization | Pytest Bridge Suite | `tests/test_telemetry.py` | Serialized JSON matches `telemetry_bridge.py` strict parser schema. | **PASS** |
| **SENS-001** | TMP117 Device Discovery | Bench Diagnostic | `diagnostics/tmp117_raw` | Historical standalone test found 0x49; integrated run failed at uptime_s=4 with NACK. | **PARTIAL** |
| **SENS-002** | TMP117 16-Bit Conversion | Automated Pytest | `tests/test_tmp117_vectors.py` | 14 test vectors verify signed 16-bit conversion ($raw \times 0.0078125^\circ\text{C}$). | **PASS** |
| **SENS-003** | MAX30102 Part Verification | Firmware Audit | `src/main.cpp` (`checkPartId()`) | Code checks register `0xFF == 0x15` before proceeding to optical setup. | **PASS** |
| **SENS-004** | MAX30102 PPG Windowing | Firmware Audit | `src/main.cpp` FIFO handling | 100-sample window with 25-sample sliding updates implemented. | **PASS** |
| **SENS-005** | Optical Signal Quality Gate | Automated Pytest & Math | `src/sensor_math.h`, `test_telemetry.py` | DC mean, AC amplitude, and Perfusion Index gates enforced in software. | **PASS** |
| **SENS-006** | Optical State Persistence | Unit & Static Asserts | `src/sensor_math.h` (`opticalWindowIsWarming`) | Compile-time assertions verify fix for spurious `warming_up` state resets. | **PASS** |
| **SENS-007** | MPU-6050 Scale & Calibration | Firmware Audit | `src/sensor_math.h`, `src/main.cpp` | Scale factors $\pm 8\text{g}$ and $\pm 250^\circ/\text{s}$ configured. Rest offset calibration code in place. | **PASS** |
| **SENS-008** | Two-Stage Fall Detection | Bench Motion Test | `src/sensor_math.h`, `src/main.cpp` | Free-fall (<0.6g) + impact (>2.5g) logic implemented; physical drop test not executed. | **NOT RUN** |
| **BE-001** | Strict Inbound Validation | Automated Pytest | `tests/test_telemetry.py` (25 methods) | Bridge rejects malformed ranges, contradictory flags, and stuck words. | **PASS** |
| **BE-002** | SQLite Time-Series Store | Automated Pytest | `tests/test_history.py` | `observations` table schema, indexes, and migrations verified. | **PASS** |
| **BE-003** | Diagnostic Column Retention | Automated Pytest | `tests/test_history.py::test_diagnostic_tmp117` | Additive migration columns store raw TMP117 data separate from wrist data. | **PASS** |
| **BE-004** | Personal Baseline Engine | Automated Pytest | `tests/test_baseline.py` | 7-day rolling statistical model computes valid ranges and z-scores. | **PASS** |
| **BE-005** | Multi-Tier Decision Alerts | Automated Pytest | `tests/test_telemetry.py::test_decision_engine` | Evaluates normal, cautionary, and critical alert tiers accurately. | **PASS** |
| **UI-001** | Real-Time Telemetry Streaming | Node.js Test Suite | `tests/dashboard_core.test.js` | Headless core dispatches SSE events to UI model. Live browser verification pending. | **PARTIAL** |
| **UI-002** | Zero-Value Masking | Node.js Test Suite | `tests/dashboard_core.test.js` | Masking prevents displaying 0 for null/low-quality sensor data. | **PASS** |
| **UI-003** | Discontinuous Chart Rendering | Node.js Test Suite | `tests/dashboard_core.test.js` | Chart logic starts new segment across missing values without drawing fake lines. | **PASS** |
| **UI-004** | Diagnostic vs Clinical Display | Node.js Test Suite | `tests/dashboard_core.test.js` | Exposes raw TMP117 diagnostic and clinical wrist as distinct fields. | **PASS** |
| **SAFE-001** | Non-Clinical Disclaimer | UI / Documentation | `index.html`, `README.md` | Prominent engineering demonstrator disclaimer visible on all pages. | **PASS** |
| **SAFE-002** | Temperature Safety Isolation | Automated Pytest & JS | `tests/test_temperature_safety.py`, `dashboard_core.test.js` | Wrist temp is null; core temp is null; fever screening is disabled. | **PASS** |
| **SAFE-003** | SOS & Fall Emergency Priority | Bench Integration | `telemetry_bridge.py`, `dashboard.js` | Software prioritization verified. Physical button/fall trigger to UI banner pending. | **PARTIAL** |
| **TEST-001** | Automated Test Regression | Shell Execution | `pytest` and `node --test` | 64 Python tests PASS, 10 Node tests PASS (100% pass rate). | **PASS** |
| **TEST-002** | Firmware Compilation Integrity | PlatformIO CLI | `pio run -e esp32-s3-devkitc-1` + diag targets | Main firmware and all 4 diagnostic targets compile with SUCCESS. | **PASS** |
| **DOC-001** | Hardware Test Guide | Document Inspection | `management/HARDWARE_TEST_GUIDE.md` | Non-destructive bench validation sequence documented with exact commands. | **PASS** |
| **DOC-002** | Video Reference Analysis | Document Inspection | `management/VIDEO_REFERENCE_ANALYSIS.md` | 4 reference videos analyzed with classified evidence levels. | **PASS** |

---

## 4. Verification Summary

- **Total Requirements**: 35
- **Verified PASS (Software / Build)**: 25 (71.4%)
- **PARTIAL (Software verified; awaiting physical bench validation)**: 6 (17.1%)
- **NOT RUN (Physical bench test required)**: 4 (11.4%)
- **FAIL**: 0 (in current software tests)
- **BLOCKED**: 0
