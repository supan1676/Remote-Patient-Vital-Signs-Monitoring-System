# Code Cleanup Register

> **Latest motion restoration (2026-11-03):** the user corrected the MPU SDA/SCL
> wiring. Current firmware remains `rpm-2.1.1`; no additional flash was needed.
> The MPU now supplies real motion/gyro readings, all **3/3 measurement sensors**
> are online, and stationary calibration completed. Section 7 supersedes the
> earlier H-01 unavailability finding and MPU-offline statements below, which
> record the state at those earlier checks. Display confirmation and physical
> fall-algorithm validation are not established by this capture. See
> [the motion restoration report](MPU_RESTORATION_REPORT_2026-11-03.md).

> **Latest MAX30102 repair (2026-11-03):** firmware `rpm-2.1.1` has been uploaded.
> The user confirmed heart-rate/SpO2 numbers on both OLED and dashboard. The
> recurring UART sampling interruption and V-02 optical-contract mismatch are
> fixed; accuracy remains unvalidated and MPU remains offline. See
> [the repair report](MAX30102_FIX_REPORT_2026-11-03.md). Earlier audit sections
> describe the state before this repair.

> Latest connected-device recheck: **2026-11-03 — partially working**. COM3 is
> transmitting real telemetry, but the MPU is offline. The historical closure
> statements below do not cover the newly reproduced parser and optical-contract
> findings. See [the current verification report](VERIFICATION_REPORT_2026-11-03.md)
> and section 5 for current evidence.

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

## 5. Connected-device recheck — 2026-11-03

This checkout is at `1849d8f`. The user requested automatic checks only.
Application source and device firmware were not changed. Fresh results:

- **64 Python tests and 10 JavaScript tests passed**, as did syntax/compile checks.
- COM3 identifies the running ESP32-S3 node; genuine JSON, HTTP, SSE and local
  SQLite recording work. Eight isolated HTTP integration checks passed.
- TMP117 at `0x49` remained valid for more than five minutes with no reported
  errors. The previous dropout was not reproduced; reference accuracy is untested.
- MAX30102 and OLED are detected. No steady-finger optical measurement, physical
  SOS press, OLED visual inspection or fall test was performed.
- MPU did not ACK on GPIO 17/18 and remained absent in all captured packets.
  The device therefore reports **2/3 measurement sensors online**.
- The main firmware freshly builds with resolved `espressif32@8.0.0`.
- The standalone TMP117 raw diagnostic and all three checked MAX coexistence
  stage targets also build successfully. No diagnostic was flashed. Nonfatal
  library warnings and new-toolchain integer-format warnings remain documented
  in the verification report.

| ID | Finding | Current disposition |
|:---|:---|:---|
| V-01 | Oversized numeric/deep JSON inputs raise uncaught parser exceptions and can stop the serial worker. | OPEN; reproduced in an isolated process; not triggered by ordinary live packets |
| V-02 | Firmware permits optical perfusion values above 20, but the bridge rejects the entire packet at that value. | OPEN; source/contract reproduction; not physically observed |
| V-03 | The bridge accepts an old sensor timestamp inside a freshly arriving packet. | OPEN hardening item; current firmware has its own stale checks |
| H-01 | MPU unavailable; motion, gyro, calibration, steps and fall detection unavailable. | OPEN physical investigation: power, ground, GPIO 17/18, AD0 and module identity |
| D-01 | Historical test counts, tool versions, USB settings and baseline descriptions differ from current source/environment. | OPEN documentation reconciliation; current facts recorded in the linked report |

Detailed evidence, local dashboard startup and remaining checks are in
[VERIFICATION_REPORT_2026-11-03.md](VERIFICATION_REPORT_2026-11-03.md).

## 6. MAX30102 readings repair — 2026-11-03

- Reproduced strong finger-present optical signals remaining in `warming_up`
  across 44 before-fix observations.
- Fixed serial telemetry blocking acquisition by configuring an 8 KB UART TX
  buffer before initialization. The 150 ms gap guard and signal-quality checks
  remain active. Added sample/window/gap counters and version `rpm-2.1.1`.
- Built and uploaded the firmware to COM3 with flash-hash verification.
- Captured 534 genuine accepted packets after the fix, including 104 with both
  optical values valid; one example is 78 bpm and 95% SpO2. The user confirmed
  numbers on **both physical OLED and dashboard**.
- Normal measurement sampling had a maximum 94 ms gap and no resets. A later
  TMP117 NACK/recovery caused one 698 ms pause and a legitimate optical reset;
  that separate intermittent TMP117 fault remains open.
- **V-02 is resolved in software:** bridge and firmware now agree on the optical
  perfusion-ratio range. Regression coverage includes retention of SOS fields.
- **66 Python tests and 10 JavaScript tests pass.** V-01 and V-03 remain open.
- Accuracy is not established: large transient HR/SpO2 estimate variation was
  captured and is documented without replacing it with forced normal values.
- The standard live bridge is running; raw capture has stopped. No commit/push.

Full evidence and startup instructions:
[MAX30102_FIX_REPORT_2026-11-03.md](MAX30102_FIX_REPORT_2026-11-03.md).

## 7. MPU motion restoration - 2026-11-03

- The user identified incorrect SDA/SCL wiring and corrected it. The existing
  `rpm-2.1.1` hotplug path then detected the MPU and produced real acceleration
  and gyroscope readings. Its initial calibration failed while the device was
  moving.
- After the user confirmed the device was flat and still, a reset produced a
  secondary-bus ACK at `0x68` with `WHO_AM_I=0x70`. The primary scan detected
  `0x3C` (OLED), `0x49` (TMP117), and `0x57` (MAX30102).
- All **23 genuine captured telemetry packets** reported **3/3 measurement
  sensors online**, MPU status `valid`, and MPU error `none`. Calibration was
  `basic_complete` on the first attempt with 80 samples, `stationary=true`, and
  orientation `z_up`.
- Recorded gyro bias was `[7.666, 4.7276, 0.1754]` degrees/s and accelerometer
  bias was `[-0.0109, -0.0342, 0.0254]` g. The latest stationary readings were
  `1.0 g` acceleration magnitude and `0.11 degrees/s` gyroscope magnitude.
- **H-01 unavailability is resolved:** the MPU communicates and supplies valid
  motion data after the wiring correction. Physical motion-display confirmation
  and fall-algorithm validation remain unperformed at this checkpoint; online
  status and calibration do not establish fall-detection performance.
- Firmware/source remain unchanged from `rpm-2.1.1` for this restoration. The
  proposed diagnostic code was reverted before any build or flash; no additional
  firmware upload was needed.
- MAX30102 accuracy, the intermittent TMP117 NACK/recovery issue, V-01 parser
  robustness, and V-03 timestamp hardening remain open. Earlier audit evidence
  and limitations above are retained.

Boot/calibration evidence:
`data/verification-2026-11-03/mpu-calibration-serial-COM3.log`.
Full restoration evidence:
[MPU_RESTORATION_REPORT_2026-11-03.md](MPU_RESTORATION_REPORT_2026-11-03.md).
