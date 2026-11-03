# Code Cleanup Register

- Audit date: 2026-10-28
- Repository: `C:\Users\ASUS\Downloads\RPMIOMTproject`
- Branch / HEAD: `main` / `f67c13a`
- State: changes are uncommitted. No commit, push, reset, revert or discard was
  performed.
- Meaning of “resolved”: the listed software behavior is covered by source review
  and host tests/builds. It does not mean the physical hardware or clinical use
  has been validated.

## 1. Findings closed in software

| ID | Finding | Resolution | Evidence |
|:---|:---|:---|:---|
| C-01 | Actual TMP117 temperature was conflated with clinical wrist temperature. | Added separate actual-sensor fields and a distinct clinical wrist field across firmware, bridge, safety model, dashboard and terminal output. | `temperature_safety.py`; `telemetry_bridge.py`; `assets/dashboard_core.js`; `src/main.cpp`; temperature and telemetry tests |
| C-02 | Unverified wrist contact could expose a clinical value. | Firmware emits `wrist_contact_status: "unverified"` with null wrist value/raw/timestamp; bridge, dashboard and store reject or mask a value without verified contact. | `tests/test_telemetry.py`, `tests/test_temperature_safety.py`, `tests/dashboard_core.test.js`, `tests/test_history.py` |
| C-03 | The clinical wrist range was incorrectly applied to the actual TMP117 sensor. | Actual sensor validation now uses `-55..150 °C`; clinical `-10..60 °C` applies only to a verified wrist observation. | `tmp117_protocol.h`, `temperature_safety.py`, `telemetry_bridge.py`, `assets/dashboard_core.js`, range test |
| C-04 | TMP117 raw conversion and stuck-bus patterns needed explicit handling. | Signed 16-bit big-endian conversion at `0.0078125 °C/LSB`; `0x0000` and `0xFFFF` are rejected; no offset is applied. | `src/tmp117_protocol.h`, `tests/test_tmp117_vectors.py`, backend temperature tests |
| C-05 | A valid status could carry stale or inconsistent raw/timestamp evidence. | Valid actual and clinical readings must agree with their signed raw conversion and timestamp; contradictions fail closed. | `telemetry_bridge.py`, `temperature_safety.py`, tests |
| C-06 | Duplicate JSON object keys could create ambiguous packets. | The bridge rejects duplicate keys at every object level and continues to reject duplicate identical serial lines. | `telemetry_bridge.py`, `tests/test_telemetry.py` |
| C-07 | Core temperature or fever screening could be implied from wrist data. | `estimated_core_temperature_c` stays null, status stays `not_available`, fever status stays `not_available`, and the message is exactly `Core temperature unavailable — confirmation required`. | `temperature_safety.py`, firmware JSON, `index.html`, `assets/dashboard.js`, tests |
| C-08 | Legacy temperature aliases could smuggle a non-null value; absent SHT40/MLX could be counted. | Non-null legacy aliases are rejected; SHT40 and MLX90614 remain absent, compiled out and not counted. | `telemetry_bridge.py`, `platformio.ini`, `README.md`, tests |
| C-09 | OLED temperature lines could fall outside the 64-pixel display. | Temperature page lines were moved into valid coordinates and the unavailable message was shortened. | `src/main.cpp`; firmware build succeeds; physical display remains unverified |
| C-10 | Missing history could be joined into false continuity or converted to zero. | Missing buckets and values stay null; the chart starts a new segment at a gap; CSV leaves gaps blank. | `assets/dashboard_core.js`, `assets/dashboard.js`, `telemetry_store.py`, gap/CSV tests |
| C-11 | Actual sensor telemetry could be mistaken for clinical history. | SQLite history stores only a verified, range-checked clinical wrist observation; actual TMP117 telemetry remains live context and is not stored as the wrist history metric. | `telemetry_store.py`, `tests/test_history.py` |
| C-12 | Baseline documentation and qualification could imply a wrist model from unverified data. | Baseline requires verified stored clinical wrist values; while contact is unverified it cannot qualify, which is documented rather than worked around. | `personal_baseline.py`, `telemetry_store.py`, `README.md`, baseline tests |
| C-13 | User-facing documentation still described the wrist value as authoritative while contact was unverified. | `README.md` and `wiring-guide.html` now distinguish **Wrist Skin Temperature (°C)** from **TMP117 Sensor Temperature (°C)** and state the contact limitation. | Documentation review; README telemetry example parses |
| C-14 | Test coverage did not exercise all new temperature semantics. | Added coverage for actual sensor, unverified/verified wrist, raw consistency, stuck patterns, null handling, fever input, legacy aliases, duplicate keys, gaps and CLI behavior. | `python -m pytest -q` → 62 passed; `node --test` → 10 passed |

## 2. Deliberately retained behavior

- Optional SHT40/MLX90614 code paths remain in the source for compatibility but
  are compiled out by default. They are not installed, required, counted, or
  described as tested hardware.
- The test fixtures are synthetic protocol shapes. They are not served as live
  telemetry and are not written to the application database.
- Raw TMP117 `0xFFFF` is still shown as a diagnostic observation in the separate
  raw diagnostic sketch so the fault can be investigated; the main firmware
  treats it as invalid.
- The nonfatal SparkFun MAX3010x `I2C_BUFFER_LENGTH` redefinition warning remains
  visible; it was not hidden.

## 3. Open items

| ID | Item | Required next evidence |
|:---|:---|:---|
| O-01 | Physical TMP117 address, identity, configuration and raw acquisition | **HARDWARE VERIFICATION REQUIRED**: upload diagnostic, capture at least five minutes, verify address/WHO_AM_I/config/raw/offset/stuck counts |
| O-02 | Actual TMP117 accuracy | **HARDWARE VERIFICATION REQUIRED**: comparison with a validated reference and documented uncertainty |
| O-03 | Wrist-contact verification method | Design and validate a detector or controlled procedure before populating clinical wrist fields |
| O-04 | MAX30102 and MPU-6050/6500 behavior | **HARDWARE VERIFICATION REQUIRED**: reference comparison, placement/quality checks, axis/range/calibration/fall tests |
| O-05 | OLED, SOS and end-to-end alert path | **HARDWARE VERIFICATION REQUIRED**: visual and physical checks on the assembled device |
| O-06 | Clinical/research/regulatory suitability | Not established; requires appropriate clinical and regulatory work outside this code audit |
| O-07 | CI automation | Add host-test and firmware-build CI after repository policy review |

## 4. Final cleanup statement

No unresolved code-review finding from this cleanup is being represented as a
validated hardware or clinical feature. The remaining limitations are hardware,
verification-method or clinical/regulatory items, not evidence that those tests
passed.
