# Code Audit Manifest

- Audit date: 2026-10-28
- Repository: `C:\Users\ASUS\Downloads\RPMIOMTproject`
- Branch / HEAD: `main` / `f67c13a`
- Working tree: uncommitted changes and new files are present. No commit, push,
  reset, revert or discard was performed.
- Scope: source, host tests, dashboard, build-system configuration and
  documentation for the RPM IoMT prototype.
- Out of scope for this audit: physical sensor operation, uploads, serial
  captures, reference-thermometer accuracy and clinical/regulatory validation.

## 1. Hardware model

| Component | Interface / address | Audit status |
|:---|:---|:---|
| ESP32-S3 DevKitC-1 N16R8 | 16 MB QIO flash, 8 MB OPI PSRAM | Build target only; not physically revalidated |
| SSD1306 OLED | `Wire`, `0x3C`, SDA 8 / SCL 9 | Software paths present; display not physically revalidated |
| MAX30102 | `Wire`, `0x57`, SDA 8 / SCL 9 | Software paths present; accuracy not physically revalidated |
| 7SEMI TMP117 ES-12132 | `Wire`, candidate addresses `0x48`–`0x4B`, SDA 8 / SCL 9 | Actual-sensor semantics implemented; physical validation pending |
| MPU-6050 / MPU-6500 | `Wire1`, `0x68`/`0x69`, SDA 17 / SCL 18 | Software paths present; calibration/axes not physically revalidated |
| SOS pushbutton | GPIO 5 to GND, active LOW | Software path present; physical press not revalidated |
| SHT40, MLX90614 | Not installed | Compiled out by default, not counted and not required |

The firmware scans `0x48`–`0x4B` and verifies `WHO_AM_I = 0x0117`. A prior
diagnostic observation reported address `0x49`; that observation is not a
current audit result and must be rechecked on the actual board.

## 2. Temperature and fever contract

| Field | Meaning | Audit rule |
|:---|:---|:---|
| `tmp117_sensor_temperature_c` | Actual TMP117 package/sensor reading | Valid range `-55..150 °C`; raw, timestamp and signed conversion must agree; may be valid outside the clinical wrist range |
| `tmp117_sensor_temperature_status` | Actual-sensor hardware status | Uses `valid`, `warming_up`, `low_quality`, `stale`, `sensor_error`, `not_available`; not `unverified` |
| `wrist_contact_status` | Whether clinical wrist contact is verified | Current firmware emits `unverified`; no contact detector is installed |
| `wrist_skin_temperature_c` | Clinical wrist-skin observation | JSON `null` while contact is unverified; only a future verified-contact reading with matching evidence and `-10..60 °C` may be exposed |
| `wrist_skin_temperature_status` | Clinical wrist status | `unverified` while contact is unverified; hardware statuses otherwise |
| `estimated_core_temperature_c` | Core-temperature estimate | Always JSON `null` |
| `estimated_core_temperature_status` | Core-temperature availability | Always `not_available` |
| `fever_screening.status` | Fever result | Always `not_available` |
| `fever_screening.message` | Required clinical message | Exactly `Core temperature unavailable — confirmation required` |

The TMP117 temperature register is treated as a signed 16-bit big-endian value
with `0.0078125 °C/LSB`. Raw `0x0000` and `0xFFFF` are rejected as stuck-bus
patterns. No fixed offset is applied, and no wrist or actual-sensor value is
converted into a core temperature.

## 3. Source inventory

| Path | Responsibility |
|:---|:---|
| `src/main.cpp` | ESP32-S3 acquisition, TMP117/MAX/MPU handling, OLED, JSON serialization |
| `src/tmp117_protocol.h` | TMP117 registers, conversion, range and compile-time vectors |
| `src/sensor_math.h` | MPU scale conversions and MAX signal-quality guards |
| `platformio.ini` | Main and diagnostic build configuration |
| `boards/esp32-s3-devkitc-1-n16r8.json` | 16 MB flash / 8 MB OPI PSRAM board manifest |
| `diagnostics/tmp117_raw/` | Standalone raw-register diagnostic procedure |
| `temperature_safety.py` | Shared actual-sensor versus clinical-wrist safety model |
| `telemetry_bridge.py` | Serial/HTTP bridge, packet validation, duplicate-key rejection, SSE |
| `telemetry_store.py` | SQLite history, gap preservation and clinical storage rules |
| `personal_baseline.py` | Seven-day per-wearer reference model |
| `ai_decision_engine.py` | Terminal findings/action summary |
| `assets/dashboard_core.js` | Pure dashboard temperature/validation helpers |
| `assets/dashboard.js` | Dashboard rendering and history/CSV behavior |
| `index.html` | Clinical and actual-sensor labels, safety strip |
| `tests/` | Synthetic protocol fixtures and host tests |
| `README.md`, `wiring-guide.html` | User-facing policy and wiring documentation |
| `CODE_CLEANUP_REGISTER.md` | Findings, dispositions and open verification items |
| `NEXT_STEPS.md` | Ordered hardware, contact-verification and release work |

## 4. Software verification evidence

Executed on 2026-10-28:

| Check | Result |
|:---|:---|
| `python -m pytest -q` | `62 passed` |
| `node --test tests/dashboard_core.test.js` | `10` passing tests, `0` failures |
| `python -m ruff check ...` | All checks passed |
| `python -m compileall -q ...` | Completed without errors |
| `node --check` on `assets/dashboard.js`, `assets/dashboard_core.js`, `tests/dashboard_core.test.js`, `tests/fixtures.js` | Completed without syntax errors |
| `pio run -e esp32-s3-devkitc-1` | **SUCCESS**; RAM 21,424 / 327,680 bytes, flash 326,001 / 6,553,600 bytes |
| `pio run -d diagnostics/tmp117_raw` | **SUCCESS**; RAM 18,916 / 327,680 bytes, flash 282,377 / 6,553,600 bytes |
| README telemetry example parsed by `telemetry_bridge.parse_packet` | Accepted; actual sensor valid, clinical wrist `null`, contact `unverified` |
| `git diff --check` | No whitespace errors; Git reported expected line-ending conversion warnings |
| `git status --short` | Uncommitted modifications and untracked source/tests/docs are present |

The main build emits a nonfatal `I2C_BUFFER_LENGTH` redefinition warning from the
SparkFun MAX3010x library. The build still succeeds; the warning was not
suppressed.

These are software/build results. They do not prove that any physical sensor,
upload path, display or reference measurement works.

## 5. Prior hardware observations (not reproduced in this audit)

The following values were reported in prior work and are retained only as
context. They were not captured or independently reproduced during this audit:

| Observation | Value |
|:---|:---|
| TMP117 raw `0x0ED3` / integer `3795` | `29.6484375 °C` after signed conversion |
| Raw `0xFFFF` | `-0.0078125 °C`; rejected by the current software as a stuck-bus pattern |
| Prior diagnostic address | `0x49` |
| Prior diagnostic configuration | `0x21A0` |
| Prior data-ready observation | `1` |
| Prior diagnostic raw | `0x0DA7` |
| Prior diagnostic conversion | `27.30469 °C` |
| Prior diagnostic result | 60 successful reads, zero failures, zero stuck patterns |

Status: **HARDWARE VERIFICATION REQUIRED**. No fresh upload, serial capture or
reference-thermometer comparison was performed in this audit. The prior values
must not be presented as current validation.

## 6. Explicitly unverified items

- TMP117 address, `WHO_AM_I`, configuration readback and raw acquisition on the
  actual board.
- TMP117 accuracy against a validated reference thermometer and a documented
  uncertainty protocol.
- Wrist-contact verification. The current clinical wrist value remains `null`
  and `unverified`.
- MAX30102 initialization, signal quality, heart-rate and SpO2 accuracy.
- MPU-6050/6500 range, axis, calibration, fall-candidate and recovery behavior.
- OLED rendering, including the compact `TMP:`/`Wrist:` temperature page. The
  exact required labels and full fever message are implemented in the dashboard
  and JSON; the 128x64 OLED necessarily uses shorter text.
- SOS button and alert/recovery path on hardware.
- End-to-end ESP32 → bridge → dashboard/history behavior with a live device.
- Clinical, research and regulatory suitability.

## 7. Readiness statement

- Software build and host tests: passing as listed above.
- Physical hardware: **HARDWARE VERIFICATION REQUIRED**.
- Clinical/research use: not established.
- Regulatory/medical-device readiness: not established.
- Core temperature and fever screening: unavailable by design.

No claim in this manifest should be read as a clinical validation or as proof
that an unperformed hardware test passed.
