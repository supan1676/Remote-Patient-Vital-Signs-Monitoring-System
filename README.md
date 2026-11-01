# RPM IoMT Patient Monitoring Node

ESP32-S3 firmware, a local serial/HTTP bridge, SQLite history, a patient baseline
and a browser dashboard for a remote-monitoring prototype.

> **Validation status:** the software builds and the host tests pass. The
> sensors, upload path, TMP117 raw anomaly, MAX30102 accuracy and MPU calibration
> have **not** been physically verified in this audit because no serial device or
> reference thermometer was available. Items marked **HARDWARE VERIFICATION
> REQUIRED** must be checked on the real hardware before making clinical claims.

## Installed hardware

| Component | Bus / address | Purpose |
|:---|:---|:---|
| ESP32-S3 DevKitC-1 N16R8 | 16 MB QIO flash, 8 MB OPI PSRAM | Controller |
| SSD1306 128×64 OLED | `Wire`, `0x3C`, SDA 8 / SCL 9 | Local display |
| MAX30102 | `Wire`, `0x57`, SDA 8 / SCL 9 | Optical pulse and SpO2 estimates |
| 7SEMI TMP117 ES-12132 | `Wire`, one of `0x48`–`0x4B`, SDA 8 / SCL 9 | Actual sensor temperature; clinical wrist contact currently unverified |
| MPU-6050 / MPU-6500 | `Wire1`, `0x68`/`0x69`, SDA 17 / SCL 18 | Motion and fall candidate detection |
| SOS pushbutton | GPIO 5 to GND, active LOW | Emergency event |

The primary bus runs at 50 kHz. The dedicated IMU bus runs at 400 kHz. All
breakouts are 3.3 V devices.

### Explicitly not installed

SHT40 and MLX90614 are **not installed**. They are optional legacy code paths,
compiled out by default:

```ini
-DRPM_ENABLE_OPTIONAL_SHT40=0
-DRPM_ENABLE_OPTIONAL_MLX90614=0
```

They are not counted in `sensors.active`, `active_max`, the baseline, the
dashboard tabs, or the sensor inventory. The installed measurement inventory is
`max`, `mpu`, `tmp117`; therefore `active_max` is **3**. The OLED is a display,
not a measurement sensor. No SHT40 or MLX90614 library is required by the default
build. The bridge rejects a packet that claims either sensor is present and also
rejects non-null legacy temperature fields, so absent hardware cannot become a
silent data source. The actual TMP117 reading is exposed separately from the
clinical wrist metric; only the installed TMP117 is counted.

## Temperature and fever policy

The actual TMP117 sensor temperature and the clinical wrist-skin observation are
separate fields with separate meanings.

- `tmp117_sensor_temperature_c` is the actual TMP117 package/sensor reading. It
  is diagnostic telemetry, not a wrist-skin or core-body measurement. It is
  valid from `-55 °C` to `150 °C`. Its raw register and timestamp are published
  only when the reading is valid.
- `wrist_skin_temperature_c` is the clinical wrist-skin metric, displayed as
  **Wrist Skin Temperature (°C)**. While `wrist_contact_status` is
  `unverified`, it stays JSON `null`, its status stays `unverified`, and its raw
  register and timestamp stay `null`. The current firmware always emits
  `unverified` because no validated contact detector is installed.
- A future verified-contact reading must match the actual sensor value, raw
  register and timestamp, satisfy the signed conversion, and stay within the
  clinical wrist range `-10 °C` to `60 °C`. An actual sensor reading outside the
  clinical wrist range but inside `-55 °C` to `150 °C` remains valid for display;
  it is not promoted to a clinical wrist value.
- No fixed offset or conversion is applied, and neither field is called core
  temperature.
- `estimated_core_temperature_c` is always JSON `null` and
  `estimated_core_temperature_status` is always `not_available`.
- Fever screening is not available. The exact JSON and dashboard message is:
  **Core temperature unavailable — confirmation required**. The OLED shows
  `Core temp unavailable` and `confirmation required` because its built-in font
  lacks U+2014.
- A wrist reading cannot confirm or rule out fever. If fever is suspected, use a
  validated clinical thermometer and clinician assessment.
- Missing, stale, warming, low-quality, sensor-error, not-available and
  unverified clinical values are JSON `null`; they are never replaced with zero
  or a previous value.
- The TMP117 driver uses checked raw I2C reads, not the Adafruit TMP117 library.
  The temperature register is signed big-endian with
  `0.0078125 °C/LSB`. `WHO_AM_I (0x0F)` must be `0x0117`. Configuration
  `0x01A0` selects continuous conversion, eight-sample averaging and a 500 ms
  cycle. `0xFFFF` and `0x0000` are rejected as stuck-bus patterns, and abrupt
  changes need a confirming sample.
- The legacy alias `tmp117_temp_c` is not emitted by the firmware. The bridge
  tolerates it only as `null`/absent and rejects a non-null value.

Supported wrist/contact status values are `valid`, `warming_up`, `low_quality`,
`stale`, `sensor_error`, `not_available` and `unverified`. Actual-sensor status
does not use `unverified`.

## Wiring

### TMP117

| TMP117 pin | Connect to | Notes |
|:---|:---|:---|
| VIN | 3.3 V | Do not use 5 V. Do not connect the separate 3.3 V pin to VIN. |
| GND | GND | Common ground |
| SDA | GPIO 8 | Shared primary I2C |
| SCL | GPIO 9 | Shared primary I2C, 50 kHz |
| ALT | Not connected | Alert is not implemented |
| ADD | As manufactured | Sets one of `0x48`–`0x4B`; identity is checked |

### Other installed devices

| Device | Wiring |
|:---|:---|
| SSD1306 OLED | VCC 3.3 V, GND, SDA GPIO 8, SCL GPIO 9, address `0x3C` |
| MAX30102 | VIN 3.3 V, GND, SDA GPIO 8, SCL GPIO 9, address `0x57` |
| MPU-6050/6500 | VCC 3.3 V, GND, SDA GPIO 17, SCL GPIO 18, AD0 selects `0x68`/`0x69` |
| SOS button | GPIO 5 to GND; internal pull-up; active LOW |

Do not add SHT40 or MLX90614 wiring for this build.

## Build and upload

PlatformIO is required. The custom board manifest deliberately selects 16 MB
flash, 8 MB OPI PSRAM and the 16 MB partition table. Do not replace it with the
stock N8 board definition.

```bash
pio device list
pio run -e esp32-s3-devkitc-1
pio run -e esp32-s3-devkitc-1 -t upload --upload-port COM6
pio device monitor --port COM6
```

On Linux/macOS use the actual device, for example `/dev/ttyACM0`. On Windows the
port is usually `COM6` or similar; never copy another machine's port blindly.
The firmware uses the USB-to-UART connector, not native USB CDC. Only one program
may own the serial port.

The build was executed in this audit:

- `pio run -e esp32-s3-devkitc-1` — **SUCCESS**
- `pio run -d diagnostics/tmp117_raw` — **SUCCESS**

The build environment identified `Espressif ESP32-S3-DevKitC-1-N16R8 (16 MB QIO
flash, 8 MB OPI PSRAM)` with 16,777,216 flash bytes. This is build metadata, not
physical validation. The SparkFun MAX3010x library emits a nonfatal
`I2C_BUFFER_LENGTH` redefinition warning during compilation; it comes from the
library header and does not change the successful build result.

## TMP117 raw-register diagnostic

The diagnostic is a separate PlatformIO project at
`diagnostics/tmp117_raw/`. It does not use the Adafruit TMP117 library. It
prints the scan, `WHO_AM_I`, configuration before/after, offset, raw bytes, the
signed code and converted temperature every second, and flags `0xFFFF`,
`0x0000`, data-not-ready and read failures.

From the repository root:

```bash
pio run -d diagnostics/tmp117_raw
pio device list
pio run -d diagnostics/tmp117_raw -t upload --upload-port COM6
pio device monitor -d diagnostics/tmp117_raw --port COM6
```

Then capture at least five minutes of output, including the period in which the
normal firmware previously displayed about `-0.01 °C`. The output contains no
patient identifiers. Record:

1. The I2C scan results and whether `WHO_AM_I` is `0x0117`.
2. The address that responds in `0x48`–`0x4B`.
3. Configuration before and after, and whether the writable-mask readback
   matches `0x01A0`.
4. Offset register raw/signed value.
5. Whether the `-0.01 °C` event coincides with raw `0xFFFF`.
6. Whether read failures or `drdy=0` occur at the same time.
7. The summary counts: successful reads, failures, all-ones, all-zeros and
   data-not-ready.

`0xFFFF` converts to `-0.0078125 °C`, which a two-decimal display rounds to
`-0.01 °C`. That is numerically consistent with a stuck-bus pattern, but it does
**not** prove the cause until the raw diagnostic log captures it. This audit did
not capture that log because no serial device was available.

If the diagnostic shows `WHO_AM_I` mismatch, no ACK, `0xFFFF`/`0x0000`, or
configuration readback mismatch, stop and check power, common ground, solder
joints, pull-ups, address strapping and the GPIO 8/9 wiring before running the
main firmware again.

## Telemetry contract

Single-line JSON at 115200 baud, prefixed with `[JSON]`. Schema version 2. The
packet is strict on the active count and status/value consistency. The packet
below is a **synthetic, schema-valid illustration**, not a live hardware capture:

```json
{"uptime_s":45,"device_id":"RPM-NODE-01","firmware_version":"rpm-2.1.0","schema_version":2,"board":{"flash_bytes":16777216,"psram_bytes":8388608},"sensors":{"oled":true,"max":true,"mpu":true,"tmp117":true,"sht40":false,"mlx":false,"active":3,"active_max":3},"vitals":{"heart_rate":72,"heart_rate_status":"valid","heart_rate_timestamp_ms":5000,"spo2":98,"spo2_status":"valid","spo2_timestamp_ms":5000,"finger_on":true,"tmp117_sensor_temperature_c":29.65,"tmp117_sensor_temperature_status":"valid","tmp117_sensor_temperature_raw":3795,"tmp117_sensor_temperature_timestamp_ms":5000,"wrist_contact_status":"unverified","wrist_skin_temperature_c":null,"wrist_skin_temperature_status":"unverified","wrist_skin_temperature_raw":null,"wrist_skin_temperature_timestamp_ms":null,"estimated_core_temperature_c":null,"estimated_core_temperature_status":"not_available","fever_screening":{"status":"not_available","message":"Core temperature unavailable — confirmation required","rule":null,"input":{"measurement":"wrist_skin_temperature","value_c":null,"unit":"C","quality":"unverified","measured":false,"timestamp_ms":null,"raw_register":null},"uncertainty":"No validated core-temperature estimate or core reference is available.","limitations":"Wrist skin temperature is affected by ambient conditions, blood flow, contact pressure and activity. A wrist reading alone cannot confirm or rule out fever."},"motion_g":1.0,"motion_status":"valid","motion_timestamp_ms":5000,"steps":0},"alerts":{"sos":false,"fall":false},"status_summary":"No configured optical alert threshold crossed; core temperature unavailable — confirmation required."}
```

The bridge validates the packet before accepting it. It rejects non-finite or
malformed numbers, duplicate JSON object keys, contradictory statuses, an absent
sensor with a valid value, any non-null core temperature, an unsupported fever
result, a wrong `active_max`, a stuck TMP117 raw pattern marked valid, and
duplicate identical serial lines. A valid actual TMP117 reading must carry a
matching signed raw conversion and timestamp. A clinical wrist reading is
accepted only with verified contact, the same evidence and the `-10..60 °C`
guard. Unavailable readings are `null`; stale evidence cannot be reused.

The bridge only marks the node live after valid JSON and expires the live view
after five seconds without a fresh packet. It does not replay stale packets to a
new browser.

## Local bridge and dashboard

```bash
python telemetry_bridge.py --serial-port COM6
# Windows alternative: python -m pip install pyserial
```

Open <http://localhost:8080/index.html>. The bridge serves the dashboard, SSE
stream, SQLite history, baseline and event APIs. It binds to `127.0.0.1` only.

- The dashboard has four active metrics: heart rate, SpO2, wrist skin
  temperature and motion. There are no SHT40/MLX tabs.
- The clinical metric is visibly labelled **Wrist Skin Temperature (°C)**. While
  contact is unverified it displays no numeric value and its raw/timestamp
  evidence stays hidden.
- The actual TMP117 reading is shown separately as **TMP117 Sensor Temperature (°C)**. It can be valid outside the clinical wrist range, but is never promoted to a wrist or core value.
- Core temperature is shown as unavailable with the exact fever message
  **Core temperature unavailable — confirmation required**.
- Recorded history preserves gaps: a missing bucket has null values and the chart
  starts a new line segment instead of drawing through the gap. Actual TMP117
  sensor telemetry is not stored as the clinical wrist history metric.
- CSV export contains the active metrics; missing values are blank.
- `data/telemetry.sqlite3` is local, additive in schema, and pruned after 30 days.
  It is excluded from source control.
- The seven-day baseline requires four active metrics and at least 30 distinct
  sampled minutes per day. While wrist contact remains unverified, wrist values
  are not stored, so the baseline cannot qualify; this is intentional rather than
  a fabricated data path. Wrist skin temperature is baseline context, never a
  core-temperature estimate.

## Calibration and physical-validation status

| Item | Status |
|:---|:---|
| TMP117 signed conversion and byte order | Compile-time vectors pass; diagnostic built |
| TMP117 `WHO_AM_I` / configuration / stuck-bus rejection | Firmware checks implemented; physical log pending |
| TMP117 `-0.01 °C` anomaly | Hypothesis: raw `0xFFFF`; **HARDWARE VERIFICATION REQUIRED** |
| TMP117 accuracy against a reference thermometer | **HARDWARE VERIFICATION REQUIRED**; no reference available |
| Core temperature | Not implemented; must remain `null` |
| Fever screening | Not available; no validated rule or reference |
| MAX30102 initialization, quality, HR/SpO2 | Software checks implemented; accuracy/placement **HARDWARE VERIFICATION REQUIRED** |
| MPU6050 ranges, axes, failed reads | ±8 g / ±250 dps / 131 LSB/dps / 4096 LSB/g in code; **HARDWARE VERIFICATION REQUIRED** |
| MPU stationary calibration | Basic startup bias, single orientation; physical retest required |
| SHT40 / MLX90614 | Not installed, compiled out, not counted, not tested |

No calibration offset is applied to TMP117. The MPU startup calibration only
estimates gyro bias and a single-orientation accelerometer bias; it is not a
six-face accelerometer calibration and is not a clinical motion validation.

## Tests executed

```bash
python -m pytest -q
# 62 passed

node --check assets/dashboard.js
node --check assets/dashboard_core.js
node --test tests/dashboard_core.test.js
# 10 passed

python -m py_compile temperature_safety.py telemetry_bridge.py \
  telemetry_store.py personal_baseline.py ai_decision_engine.py
```

Coverage includes TMP117 conversion/register vectors, stuck-bus masking, separate
actual-sensor and unverified/verified wrist semantics, MAX/MPU scale constants
and signal-quality guards (compile-time assertions), backend schema/status
validation, malformed-type and duplicate-key rejection, fever rejection, SQLite
migration and gaps, four-metric baseline qualification, and dashboard
status/gap/CSV behavior.

These are host/software tests. They do not prove the physical sensors work.

## Hardware verification procedure

1. Disconnect power, inspect wiring, confirm common ground and 3.3 V.
2. Run `pio device list`; upload the TMP117 raw diagnostic to the actual port.
3. Capture five minutes of diagnostic output and resolve any address,
   `WHO_AM_I`, configuration, raw-pattern or read-error issue.
4. Upload the main firmware and watch the boot scan. Confirm OLED, MAX30102,
   TMP117 and MPU addresses and the `3/3 measurement sensors online` line.
5. With TMP117 removed, confirm the actual TMP117 fields are null, its status is
   `not_available`, `sensors.tmp117` is false, and the clinical wrist fields stay
   null and `unverified`; reconnect and confirm hot-plug recovery.
6. Keep the sensor still and compare the actual TMP117 reading with a validated
   reference under controlled conditions. Document ambient temperature, contact
   pressure and stabilization time. Separately define and validate any future
   wrist-contact verification method. Do not derive core temperature and do not
   promote the actual sensor reading to a clinical wrist value without verified
   contact and matching evidence.
7. Test MAX30102 with no finger, steady finger, motion and removal. Confirm HR
   and SpO2 become null and statuses change; record signal quality.
8. Test MPU at rest and in known orientations; rotate around each axis and
   compare units/signs. Verify failed reads produce null values, not 1 g.
9. Press SOS and simulate a fall (safely). Confirm serial, OLED and dashboard
   alerts and recovery.
10. Confirm the dashboard shows **Wrist Skin Temperature (°C)** and **TMP117 Sensor Temperature (°C)** as separate values, the exact core-temperature message, and no SHT40/MLX tabs. Confirm no chart line crosses a disconnect gap.

Record results in the hardware log, not in source control.

## Security and privacy

- No credentials, API keys or patient identifiers belong in the repository.
- The bridge stores a device ID, measurements and optional alias locally. Do not
  put real patient identifiers in the alias field.
- The server listens only on localhost. Do not expose it to a network without
  authentication, TLS and a privacy/security review.
- Ordinary logs contain sensor status and error strings, not a patient's name or
  raw clinical history. The dashboard review note is browser-local.

## Remaining work

1. Capture and inspect the TMP117 raw diagnostic; confirm or refute the
   `0xFFFF` cause of the `-0.01 °C` display.
2. Physically validate the actual TMP117 sensor reading against a reference and
   define a defensible measurement/uncertainty protocol. Do not add a fixed
   offset.
3. Define and validate a wrist-contact verification method before exposing
   clinical wrist values. Until then, keep `wrist_skin_temperature_c`,
   `wrist_skin_temperature_raw` and `wrist_skin_temperature_timestamp_ms` null,
   and keep `wrist_contact_status` and the wrist status `unverified`.
4. Validate MAX30102 HR/SpO2 against a reference and document placement/quality
   limitations.
5. Re-run MPU range, axis, calibration and fall tests; do not call the
   single-orientation bias a full calibration.
6. Decide whether a validated core-temperature method will ever be added. Until
   then, keep `estimated_core_temperature_c` null and fever screening disabled.
7. Add CI for the existing host tests and firmware builds.

## Audit records

- [`CODE_AUDIT_MANIFEST.md`](CODE_AUDIT_MANIFEST.md) — scope, software evidence,
  prior hardware observations and unverified items.
- [`CODE_CLEANUP_REGISTER.md`](CODE_CLEANUP_REGISTER.md) — findings, dispositions
  and open verification work.
- [`NEXT_STEPS.md`](NEXT_STEPS.md) — ordered hardware, contact-verification and
  release steps.
