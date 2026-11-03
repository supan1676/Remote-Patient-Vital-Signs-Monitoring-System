# System Risk Register & Hazard Analysis

- Document ID: MGT-RSK-001
- Version: 1.0.0
- Date: 2026-11-01
- Project: Remote Patient Vital Signs Monitoring System (RPMIOMTproject)
- Author: Chief Engineering Manager & Verification Specialist Agent

---

## 1. Risk Evaluation Methodology

Risks are rated across three standard dimensions:
- **Severity (S)**: 1 (Negligible) to 5 (Catastrophic / Severe injury / Device destruction)
- **Likelihood (L)**: 1 (Improbable) to 5 (Frequent / Highly likely)
- **Risk Priority Number (RPN)**: $RPN = S \times L$ (Scale: 1 to 25)
  - Low (1–6): Acceptable with standard engineering practices.
  - Medium (8–12): Active mitigation and architectural safeguards required.
  - High (15–25): Critical hazard requiring fail-safe controls and verification.

---

## 2. Risk Log

| Risk ID | Risk Category | Hazard Description | Severity (S) | Likelihood (L) | Initial RPN | Engineering Mitigation & Failsafe Control | Residual S | Residual L | Residual RPN | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| **RSK-HW-01** | Electrical / Power | MAX30102 LED pulse current (~50mA peaks) causes 3.3V rail voltage droop, causing TMP117 to brown out or NACK on I2C bus. | 4 | 4 | **16 (High)** | Created staged diagnostic firmware (`diagnostics/tmp117_with_max`) to isolate LED load. Hardware recommendation: 100µF decoupling capacitor across MAX30102 VCC/GND. | 3 | 2 | 6 (Low) | **MITIGATED IN CODE / BENCH ACTION PENDING** |
| **RSK-HW-02** | Electrical | Connecting sensors to 5V rail exposes ESP32-S3 3.3V GPIOs to over-voltage, permanently destroying pins. | 5 | 2 | **10 (Med)** | Explicit wiring instructions, documentation alerts, and hardware test guide specifying strict 3.3V power rails. | 4 | 1 | 4 (Low) | **CONTROLLED** |
| **RSK-HW-03** | Bus / Signal | Parallel pull-up resistors on multiple breakout boards drop net resistance below 1.5kΩ, exceeding I2C sink current. | 3 | 3 | 9 (Med) | Split architecture across two independent hardware buses (`Wire` at 50kHz, `Wire1` at 400kHz). | 2 | 2 | 4 (Low) | **CONTROLLED** |
| **RSK-SAFE-01** | Clinical Safety | User or caregiver misinterprets raw TMP117 sensor reading as core body temperature, delaying fever medical treatment. | 5 | 4 | **20 (High)** | Strict architectural decoupling: `wrist_skin_temperature_c` is null until contact is verified; `estimated_core_temperature_c` is permanently null; fever screening is disabled. | 5 | 1 | 5 (Low) | **VERIFIED BY TESTS** |
| **RSK-SENS-01** | Measurement Quality | MAX30102 optical sensor outputs false HR/SpO2 readings from ambient lighting or optical table reflection when no finger is present. | 3 | 5 | **15 (High)** | Triple-stage signal quality gate: Red/IR DC mean ≥ 50,000, AC amplitude ≥ 1,000, Perfusion Index ≥ 0.10%. Outputs masked as `low_quality`. | 2 | 2 | 4 (Low) | **VERIFIED BY TESTS** |
| **RSK-SENS-02** | Measurement Quality | Partial FIFO buffer filling during sliding window updates causes UI to flicker between `low_quality` and `warming_up`. | 2 | 5 | **10 (Med)** | Fixed in `src/sensor_math.h` and `src/main.cpp`: `opticalWindowIsWarming()` preserves completed window result while new samples fill. | 1 | 1 | 1 (Low) | **RESOLVED & VERIFIED** |
| **RSK-FW-01** | Embedded Stability | Unresponsive or hot-unplugged I2C slave holds SDA low, causing `Wire.endTransmission()` to hang the ESP32-S3 indefinitely. | 4 | 3 | **12 (Med)** | Implemented software I2C bus recovery routine with 9 clock pulses on SCL and explicit timeout handling. | 2 | 2 | 4 (Low) | **CONTROLLED** |
| **RSK-BE-01** | Data Integrity | Telemetry bridge crashes or writes corrupted records to SQLite when receiving partial or malformed serial packets. | 3 | 3 | 9 (Med) | Defensive parsing in `telemetry_bridge.py`: 100+ validation assertions, strict JSON schema parsing, transaction rollback in `telemetry_store.py`. | 2 | 1 | 2 (Low) | **VERIFIED BY TESTS** |
| **RSK-UI-01** | UX / Fabrication | Dashboard displays 0 or previous stale value when a sensor disconnects or reports low quality. | 3 | 4 | **12 (Med)** | Headless `dashboard_core.js` masks missing values with explicit strings ("--", "Not connected") and renders broken chart segments. | 2 | 1 | 2 (Low) | **VERIFIED BY TESTS** |
| **RSK-OPS-01** | Toolchain / Bench | Attempting to upload firmware while `telemetry_bridge.py` holds the serial COM port open results in `esptool.py` serial access error. | 2 | 4 | 8 (Med) | Clear operational instructions in `HARDWARE_TEST_GUIDE.md` detailing the shutdown of Python bridge prior to PlatformIO upload. | 1 | 2 | 2 (Low) | **CONTROLLED** |

---

## 3. High-Priority Action Items

1. **Physical Power Decoupling (RSK-HW-01)**:
   - When user performs physical bench validation, test staged firmware (`tmp117-max-stage1`, `stage2`, `stage3`) to confirm whether LED pulse current triggers the TMP117 bus NACK.
   - If NACK occurs only in stage 3, user should attach a 10µF–100µF electrolytic or ceramic capacitor across the MAX30102 VCC and GND pins.
2. **Clinical Safety Safeguard (RSK-SAFE-01)**:
   - Continuous enforcement in CI and automated tests to ensure no commit ever re-enables fever screening or core temperature estimation without certified reference data.

