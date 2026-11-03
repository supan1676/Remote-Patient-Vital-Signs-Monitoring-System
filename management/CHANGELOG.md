# Engineering Changelog & Version History

- Document ID: MGT-CHG-001
- Version: 1.0.0
- Date: 2026-11-01
- Project: Remote Patient Vital Signs Monitoring System (RPMIOMTproject)
- Author: Chief Engineering Manager

---

## [1.0.0-V1.Demonstrator] - 2026-11-01

### Summary of Sprint
Conducted a complete audit, bug fixing, safety hardening, and documentation overhaul across the entire RPMIOMTproject stack. Resolved firmware optical status oscillations, implemented staged hardware coexistence diagnostics for the TMP117/MAX30102 bus issue, added additive database migration for diagnostic telemetry, and created an extensive 13-document engineering management framework.

---

### Detailed Changes by Subsystem

#### 1. Embedded Firmware (`src/`)
- **`src/sensor_math.h`**:
  - Implemented `sensor_math::opticalWindowIsWarming(uint16_t samples, bool hasWindowResult)`.
  - Added compile-time `static_assert` assertions verifying empty, partial, full, and post-result optical buffer states.
  - Fixed status oscillation bug where in-progress sliding window buffer refills erroneously reverted `low_quality` states back to `warming_up`.
- **`src/main.cpp`**:
  - Updated `resetOpticalState()` to clear `lastOpticalResultMs`, ensuring authentic contact resets trigger a fresh warming cycle.
  - Integrated `opticalWindowIsWarming()` into `sampleOptical()` to preserve valid or low-quality window metrics while subsequent sliding windows fill.
  - Enhanced `initTmp117()` to return actual `tmp117Present` status after the first 600ms conversion read rather than reporting true on initialization entry.
  - Added explicit address logging on TMP117 discovery and hot-plug events.

#### 2. Telemetry Persistence & Backend (`telemetry_store.py`)
- **`telemetry_store.py`**:
  - Added additive diagnostic schema migration (`MIGRATION_COLUMNS`) for `tmp117_sensor_temperature`, `tmp117_sensor_temperature_raw`, `tmp117_sensor_temperature_timestamp_ms`, and `tmp117_sensor_temperature_status`.
  - Implemented `actual_tmp117_reading()` to validate raw codes, timestamps, and signed conversions before persistence.
  - Preserved 100% of historical patient data without schema truncation or loss.
  - Enforced strict isolation: diagnostic sensor data is strictly segregated from clinical wrist skin columns and baseline models.

#### 3. Frontend Architecture (`assets/`, `index.html`)
- **`assets/dashboard_core.js`**:
  - Decoupled raw TMP117 diagnostic sensor readings from clinical wrist temperature.
  - Enforced zero-fabrication masking: missing or invalid sensor states render clear textual badges ("--", "Warming up", "Not connected") and never substitute 0 or previous values.
  - Implemented discontinuous chart rendering so line charts break across null/missing intervals rather than drawing interpolated paths.

#### 4. Hardware Diagnostics (`diagnostics/`)
- **`diagnostics/tmp117_with_max/platformio.ini` & `src/main.cpp`**:
  - Created 3 isolated coexistence diagnostic targets (`tmp117-max-stage1`, `tmp117-max-stage2`, `tmp117-max-stage3`).
  - Enables non-destructive empirical diagnosis of breadboard power droop under optical LED pulse loads.

#### 5. Verification & Test Suites (`tests/`)
- **`tests/test_tmp117_vectors.py`**:
  - Added source-contract tests verifying the mathematical logic and static assertions of `opticalWindowIsWarming()`.
- **`tests/test_history.py`**:
  - Added unit tests for diagnostic TMP117 observation logging and schema migration.
- **Test Suite Results**:
  - Python Pytest: **64 passed** (0.23s).
  - Node.js Dashboard Test: **10 passed** (74ms).
  - PlatformIO Build: **SUCCESS** across production and all 4 diagnostic environments.

#### 6. Management Framework (`management/`)
- Created complete documentation suite:
  - `PROJECT_STATE.md`: Comprehensive audit and system state.
  - `SYSTEM_ARCHITECTURE.md`: Complete hardware/software architecture with Mermaid data flows.
  - `VIDEO_REFERENCE_ANALYSIS.md`: Rigorous analysis of 4 reference videos with evidence classifications.
  - `SOURCES.md`: Citations for datasheets, standards, and references.
  - `REQUIREMENTS.md`: Hierarchical system requirements with unique IDs and statuses.
  - `TASK_BOARD.md`: Specialist task distribution mapped to Agents 1–5.
  - `INTERFACES.json`: Machine-readable hardware and software schema specification.
  - `VERIFICATION_MATRIX.md`: End-to-end requirement traceability matrix.
  - `RISK_REGISTER.md`: FMEA risk analysis and mitigations.
  - `SENSOR_IMPLEMENTATION_REPORT.md`: Comprehensive sensor audit and root-cause analysis.
  - `HARDWARE_TEST_GUIDE.md`: Step-by-step physical bench validation manual.
  - `TOOLCHAIN.md`: Toolchain versions, build profiles, and commands.
  - `CHANGELOG.md`: Detailed version history.
  - `OPEN_ISSUES.md`: Open issues and bench verification items.
  - `CHANGE_REQUEST_USAGE.md`: Change control protocol.

