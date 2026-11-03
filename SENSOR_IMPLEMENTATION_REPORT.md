# Sensor Implementation Report

- Date: 2026-11-01
- Repository: `C:\Users\ASUS\Downloads\RPMIOMTproject`
- Branch / HEAD at start of this work: `main` / `34b2d4d`
- Working tree: intentionally left uncommitted. No commit, push, reset, clean,
  revert or discard was performed.
- Hardware state at the end of this work: the board was **not** uploaded to,
  reset or opened on COM6 during this session. It still runs the previously
  uploaded stage-2 coexistence diagnostic, not the main firmware.

## 1. Scope and constraints

The goal was to improve the reliability of the installed TMP117 and MAX30102
paths and carry their data through the existing bridge, local database and
dashboard without inventing measurements or weakening safety.

The following constraints were kept:

- Preserve the ESP32-S3/RPMIOMT architecture and existing uncommitted work.
- Do not replace the firmware, board or backend with a tutorial project.
- Do not add a second TMP117 implementation or an unnecessary library.
- Do not hard-code the TMP117 address. Discovery remains `0x48`-`0x4B` with a
  `WHO_AM_I == 0x0117` identity check.
- Do not lower MAX30102 DC, AC or perfusion-index thresholds without physical
  evidence.
- Keep `tmp117_sensor_temperature_c`, `wrist_skin_temperature_c` and
  `estimated_core_temperature_c` separate.
- Keep `wrist_contact_status` at `unverified`, the clinical wrist value `null`,
  core temperature `null` and fever screening unavailable.
- Do not delete historical patient data.
- No hardware access without explicit permission.

## 2. What was inspected

- `src/main.cpp`: TMP117 and MAX30102 acquisition, status transitions, JSON
  serialization and hot-plug handling.
- `src/tmp117_protocol.h`: registers, signed conversion, identity, range and
  stuck-bus checks.
- `src/sensor_math.h`: MAX30102 quality guard and new optical-window state helper.
- `telemetry_bridge.py`: strict packet validation, SSE/API relay and status/value
  consistency.
- `telemetry_store.py`: valid-measurement rules, SQLite schema, migration and
  history aggregation.
- `assets/dashboard_core.js` and `assets/dashboard.js`: missing-value masking,
  sensor-health labels and temperature presentation.
- `tests/`: existing protocol, history, baseline, temperature-safety and
  dashboard tests.
- `diagnostics/tmp117_raw/` and `diagnostics/tmp117_with_max/`: focused
  diagnostics.
- All four reference videos, their metadata/descriptions/transcripts where
  available, and sampled storyboard frames. Details and evidence limits are in
  `VIDEO_REFERENCE_ANALYSIS.md`.

## 3. Findings

### 3.1 TMP117: protocol path is correct; the observed disappearance is physical

The TMP117 code path does the right things:

1. It scans `0x48`-`0x4B`.
2. It reads `WHO_AM_I` and requires `0x0117`.
3. It writes configuration `0x01A0` and checks the writable-mask readback.
4. It reads the offset register for audit.
5. It waits 600 ms, performs a checked data-ready/configuration read, then reads
   the signed big-endian temperature register.
6. It rejects `0x0000` and `0xFFFF`, checks range, and requires a confirmation
   sample after an abrupt change.

The observed failure is not a TMP117 protocol failure:

- In the main-firmware boot log, TMP117 was found at `0x49` with
  `WHO_AM_I=0x117`, `config=0x1A0`, and a valid reading of `26.84 °C` at
  `uptime_s=3`.
- At `uptime_s=4`, the same address returned `i2c_address_nack`. Later it was
  reported as `not_found_or_identity_mismatch`.
- The standalone `diagnostics/tmp117_raw` firmware ran for 30 seconds at the same
  address with stable readings around `26.8 °C`, configuration readback
  `0x01A0`, and no NACK.
- Coexistence stage 1 (`MAX30102.begin()` plus identity only) left TMP117 present
  and stable for the observed run.
- Coexistence stage 3 (full MAX30102 setup with red/IR pulse amplitude `0x24`)
  found TMP117 in the first scan and then failed to find it immediately after
  MAX30102 initialization.
- Stage 2 (full MAX30102 setup with pulse amplitude `0x00`) had not been
  captured before this permission restriction. That is the next discriminating
  test.

**Conclusion:** the evidence points to a hardware/power/wiring/bus interaction,
most likely involving the MAX30102 LED current or a marginal 3.3 V/ground path,
but the exact electrical cause is **not proven**. No firmware workaround was
added to hide it. In particular, the address was not hard-coded, the identity
check was not relaxed, and no threshold was lowered.

### 3.2 MAX30102: a real status regression was fixed

The old transition had a confirmed bug:

- `finishOpticalWindow()` sets `maxStatus`, `heartRateStatus` and `spo2Status` to
  `low_quality` when a completed window fails the DC/AC/perfusion-index guard.
- On later valid IR/red samples, `sampleCount` is below 100 during the next
  partially filled window. The old code then replaced those statuses with
  `warming_up`.
- The result was a misleading oscillation between "Low quality" and "Warming
  up" after a completed result, even though no new window had been evaluated.

The fix:

- Added `sensor_math::opticalWindowIsWarming(samples, hasWindowResult)`.
- The helper returns true only for a partially filled **first** window.
- `resetOpticalState()` now clears `lastOpticalResultMs`, so a real contact loss
  or reset can legitimately start a new warming period.
- `sampleOptical()` preserves the completed valid or low-quality result while the
  next window fills.
- Compile-time assertions cover empty, partial, full and completed-result cases.
  The existing source-contract test also checks the helper and its static
  assertions.

No signal threshold changed. The 50,000 DC floor, 1,000 AC floor and 0.10
perfusion-index floor remain the same until a physical fingertip capture supports
any change.

### 3.3 TMP117 discovery reporting is more truthful

`initTmp117()` previously returned `true` after the 600 ms first-conversion wait
even if that first transaction had already lost the address. It now returns
`tmp117Present` after that read. This does not change identity checking or
recover a damaged sensor; it prevents a transient first-read failure from being
reported as an online discovery.

The startup and hot-plug messages now include the discovered address, which makes
the log easier to compare with the standalone and coexistence diagnostics.

### 3.4 The data path remains separate and non-fabricating

Firmware:

- `tmp117_sensor_temperature_c` is emitted only when the TMP117 is present, its
  raw register is valid, its status is `valid`, and the converted value is
  finite.
- `tmp117_sensor_temperature_raw` and its timestamp are emitted only for that
  same valid path.
- `wrist_contact_status` is always `unverified`.
- `wrist_skin_temperature_c`, its raw register and timestamp remain `null`.
- `estimated_core_temperature_c` remains `null`; core status remains
  `not_available`.
- Fever screening remains `not_available` with the exact message
  `Core temperature unavailable — confirmation required`.

Bridge:

- Rejects contradictory status/value combinations, absent sensors with valid
  values, non-finite numbers, stuck TMP117 raw patterns, conversion mismatches,
  missing timestamps and non-null core/fever claims.
- Keeps the actual TMP117 reading separate from the clinical wrist value.
- Does not invent a value when the device reports `not_available`, `stale`,
  `low_quality`, `sensor_error` or `unverified`.

Database:

- The clinical history columns still store only explicitly valid clinical
  measurements. They do not turn the actual TMP117 temperature into wrist skin
  temperature.
- The actual TMP117 value is now retained in the SQLite `observations` table as
  **diagnostic columns**:
  `tmp117_sensor_temperature`,
  `tmp117_sensor_temperature_raw`,
  `tmp117_sensor_temperature_timestamp_ms`, and
  `tmp117_sensor_temperature_status`.
- The schema addition is additive through `MIGRATION_COLUMNS`; existing rows are
  preserved, and no historical data is deleted.
- `actual_tmp117_reading()` revalidates the value, raw code, timestamp, range and
  signed conversion before storing a non-null diagnostic value. Invalid evidence
  stores null value/raw/timestamp while retaining the reported status for audit.
- The actual TMP117 diagnostic column is not part of the active clinical
  baseline, personal-baseline models, wrist history or fever logic.

Dashboard:

- Displays the actual TMP117 sensor value and the clinical wrist value as
  separate concepts.
- Labels missing/invalid states from `sensor_health`; it does not substitute zero
  or a previous value.
- Keeps "Not connected" and "Warming up" tied to firmware health rather than
  inventing a connection.

## 4. Files changed in this implementation

Changes made during this work:

- `src/sensor_math.h`
  - Added `opticalWindowIsWarming()`.
  - Added compile-time status-transition assertions.
- `src/main.cpp`
  - Clear `lastOpticalResultMs` in `resetOpticalState()`.
  - Use the new warming helper instead of overwriting completed results.
  - Return `tmp117Present` after the first TMP117 conversion read.
  - Print the discovered TMP117 address at startup and hot-plug.
- `tests/test_tmp117_vectors.py`
  - Added source-contract checks for the new helper and assertions.
- `tests/test_history.py`
  - Added diagnostic actual-TMP117 storage and invalidation tests.
  - Added migration-column assertions.
- `telemetry_store.py`
  - Added additive diagnostic TMP117 columns and `actual_tmp117_reading()`.
  - Stored actual TMP117 diagnostic evidence separately from wrist history.
- `diagnostics/tmp117_with_max/platformio.ini`
  - Added explicit `tmp117-max-stage1`, `tmp117-max-stage2` and
    `tmp117-max-stage3` environments.
- `diagnostics/tmp117_with_max/src/main.cpp`
  - Documented the stage commands; no measurement logic changed.
- New: `VIDEO_REFERENCE_ANALYSIS.md`, `SENSOR_IMPLEMENTATION_REPORT.md`,
  `HARDWARE_TEST_GUIDE.md`.

Pre-existing uncommitted changes in the repository were preserved. This report
does not claim authorship of unrelated work in the working tree.

## 5. Verification performed

All commands were run from the repository root.

| Check | Result |
|:---|:---|
| `python -m pytest` | **64 passed** |
| `ruff check .` | **All checks passed** |
| `python -m compileall -q .` | No errors |
| `node --test tests/dashboard_core.test.js` | **10 passed, 0 failed** |
| `node --check assets/dashboard.js` | Passed |
| `node --check assets/dashboard_core.js` | Passed |
| `node --check tests/fixtures.js` | Passed |
| `pio run -e esp32-s3-devkitc-1` | **SUCCESS**; RAM 21,424 / 327,680 bytes; flash 326,061 / 6,553,600 bytes |
| `pio run -d diagnostics/tmp117_raw` | **SUCCESS**; RAM 18,916 / 327,680 bytes; flash 282,377 / 6,553,600 bytes |
| `pio run -d diagnostics/tmp117_with_max -e tmp117-max-stage1` | **SUCCESS**; RAM 18,940 / 327,680 bytes; flash 282,153 / 6,553,600 bytes |
| `pio run -d diagnostics/tmp117_with_max -e tmp117-max-stage2` | **SUCCESS**; RAM 18,940 / 327,680 bytes; flash 283,061 / 6,553,600 bytes |
| `pio run -d diagnostics/tmp117_with_max -e tmp117-max-stage3` | **SUCCESS**; RAM 18,948 / 327,680 bytes; flash 283,625 / 6,553,600 bytes |
| `pio run -d diagnostics/tmp117_with_max` (default stage 3) | **SUCCESS**; RAM 18,948 / 327,680 bytes; flash 283,625 / 6,553,600 bytes |
| `git diff --check` | No whitespace errors; Git emitted expected LF-to-CRLF conversion warnings |

The nonfatal SparkFun `I2C_BUFFER_LENGTH` redefinition warning remains. It comes
from the library header and does not change the successful build result.

These are **software/build results**. They do not prove that the physical TMP117
stays present when the MAX30102 LEDs draw current, that the fingertip signal
passes the quality guard, or that any reported value is clinically accurate.

## 6. Unverified physical items

- TMP117 3.3 V rail stability under MAX30102 LED load.
- TMP117 ground continuity and SDA/SCL continuity on the assembled breadboard.
- TMP117 ADD strapping and address stability.
- TMP117 pull-up adequacy and bus behavior with all three devices attached.
- Stage 2: full MAX30102 setup with LEDs off.
- Stage 3: with production LED current, whether TMP117 is lost at MAX
  initialization or only after FIFO/LED activity.
- Main firmware with a live TMP117 and MAX30102 simultaneously.
- MAX30102 raw IR/red values with a real, stationary fingertip.
- MAX30102 heart-rate and SpO2 values against any reference.
- OLED rendering and SOS/fall paths.
- End-to-end ESP32 -> bridge -> SQLite -> dashboard behavior.
- Clinical wrist contact, core temperature and fever screening: unavailable by
  design, not merely unverified.

The exact bench sequence and commands are in `HARDWARE_TEST_GUIDE.md`.
