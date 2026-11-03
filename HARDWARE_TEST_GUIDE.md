# Hardware Test Guide

- Date: 2026-11-01
- Scope: ESP32-S3 DevKitC-1, TMP117, MAX30102, SSD1306 OLED, MPU and the
  local bridge/database/dashboard.
- **Permission gate:** no upload, reset, serial monitor or COM6 access was
  performed while preparing this guide. Run the commands below only after you
  explicitly authorize physical access. The board currently runs the previously
  uploaded `diagnostics/tmp117_with_max` stage-2 firmware, not the main firmware.
- Run every command from the repository root:
  `C:\Users\ASUS\Downloads\RPMIOMTproject`.
- Only one program may own COM6. Close the monitor before starting the bridge.

This guide separates **signal availability** from **clinical validation**. A
passing signal test does not make the MAX30102 pulse/SpO2 estimates accurate and
does not make the TMP117 a wrist, core or fever measurement.

## 1. Bench setup and safety

Use a desk, not a worn breadboard. A steady fingertip on the MAX30102 is enough;
the breadboard does not need to be worn.

1. Disconnect USB before changing wiring.
2. Check that every breakout is powered from **3.3 V**, not 5 V. The ESP32-S3
   I/O is not 5 V tolerant.
3. Confirm a common ground between the ESP32-S3, TMP117, MAX30102 and OLED.
4. Keep the TMP117 away from the ESP32-S3 regulator, the OLED and the MAX30102
   optical module. Do not put a finger on the TMP117 when recording a room
   temperature; it is not a clinical contact measurement.
5. Use a USB data cable, not a charge-only cable.
6. Do not connect a patient or use this prototype for diagnosis during the test.
7. Preserve the current working tree. Do not reset, clean, revert or commit as
   part of a hardware test.

### Wiring to verify

| Device | Expected wiring | Check |
|:---|:---|:---|
| TMP117 | VIN 3.3 V, GND, SDA GPIO 8, SCL GPIO 9, ADD as manufactured | Do not use the separate 3.3 V pin as an input; do not apply 5 V |
| MAX30102 | VIN 3.3 V, GND, SDA GPIO 8, SCL GPIO 9 | Red LED faces the fingertip; no 5 V |
| SSD1306 | VCC 3.3 V, GND, SDA GPIO 8, SCL GPIO 9, address `0x3C` | Display only |
| MPU | VCC 3.3 V, GND, SDA GPIO 17, SCL GPIO 18 | Separate `Wire1` bus |
| SOS button | GPIO 5 to GND, active LOW | Optional for this sensor test |

The primary bus is intentionally 50 kHz. The TMP117 is one of `0x48`-`0x4B`;
its address is discovered and its `WHO_AM_I` must be `0x0117`. Do not hard-code
or force an address.

## 2. Pre-flight checks

Run these without uploading:

```powershell
pio device list
pio run -e esp32-s3-devkitc-1
pio run -d diagnostics/tmp117_raw
pio run -d diagnostics/tmp117_with_max -e tmp117-max-stage1
pio run -d diagnostics/tmp117_with_max -e tmp117-max-stage2
pio run -d diagnostics/tmp117_with_max -e tmp117-max-stage3
```

Pass criteria for the builds:

- All commands report `SUCCESS`.
- The main firmware reports the expected ESP32-S3-N16R8 target.
- The SparkFun `I2C_BUFFER_LENGTH` redefinition warning is nonfatal; do not
  treat it as a sensor failure.
- Note the build timestamps and firmware build strings for the test record.

Before powering the sensors, with USB disconnected, use a multimeter:

- Continuity from each breakout GND to the ESP32-S3 GND.
- Continuity from TMP117 SDA to GPIO 8 and SCL to GPIO 9; repeat for the MAX.
- No short between 3.3 V and GND.
- TMP117 ADD strapping matches the address you expect. The firmware will still
  discover whichever valid address is present.
- If the modules expose pull-ups, check that the shared bus is not overloaded by
  several strong pull-up networks. Record the measured resistance from SDA and
  SCL to 3.3 V with power off.

## 3. Stage A: standalone TMP117

This removes MAX30102 activity from the test. The TMP117 shares the bus with the
other breakouts physically, but this sketch does not initialize or drive them.

Upload and monitor, **only with permission**:

```powershell
pio run -d diagnostics/tmp117_raw
pio run -d diagnostics/tmp117_raw -t upload --upload-port COM6
pio device monitor --port COM6 --baud 115200
```

Leave it running for at least five minutes. If the sensor is disconnected or
reconnected, the diagnostic rescans every five seconds.

### Record

- I2C scan addresses that ACK.
- The discovered TMP117 address, which must be in `0x48`-`0x4B`.
- `WHO_AM_I`, which must print `0x0117`.
- Configuration before and after. The writable-mask readback must match
  `0x01A0` (the serial print may omit leading zeroes).
- Offset raw/signed value. A nonzero offset is reported; this firmware does not
  apply a software offset.
- Raw register and converted temperature each second.
- Counts of successful reads, failures, `0xFFFF`, `0x0000` and `drdy=0`.
- Any `ADDRESS_NACK`, `DATA_NACK`, `short_read` or `bus_error`.

### Pass/fail

| Result | Meaning |
|:---|:---|
| ACK at `0x48`-`0x4B`, `WHO_AM_I=0x0117`, config readback `0x01A0`, plausible stable raw values for five minutes | TMP117 path passes the standalone stage |
| No ACK, identity mismatch, config readback mismatch, stuck `0xFFFF`/`0x0000`, repeated NACK or bus error | Stop and fix power/ground/wiring/pull-ups/ADD before continuing |

The previous evidence was: main firmware initially read `0x49`, `0x117`,
`0x1A0` and `26.84 °C`, then received `i2c_address_nack`; the standalone
diagnostic was stable at `0x49`. Re-run it to confirm the current assembly, not
to assume it still behaves the same way.

Stop the monitor with `Ctrl+C` before the next upload.

## 4. Stage B: TMP117/MAX30102 coexistence

These diagnostics initialize the MAX30102 in controlled stages. They are the
discriminating test for the observed TMP117 disappearance.

### Stage 1: MAX begin and identity only

```powershell
pio run -d diagnostics/tmp117_with_max -e tmp117-max-stage1
pio run -d diagnostics/tmp117_with_max -e tmp117-max-stage1 -t upload --upload-port COM6
pio device monitor --port COM6 --baud 115200
```

Expected:

- MAX30102 `begin` succeeds and `PART_ID=0x15`.
- The message says `identity only; setup/LEDs untouched`.
- TMP117 remains identified and readable for at least two minutes.

### Stage 2: full MAX setup, red/IR pulse amplitude `0x00`

```powershell
pio run -d diagnostics/tmp117_with_max -e tmp117-max-stage2
pio run -d diagnostics/tmp117_with_max -e tmp117-max-stage2 -t upload --upload-port COM6
pio device monitor --port COM6 --baud 115200
```

The SparkFun `setup()` call is followed by explicit red/IR pulse amplitude
`0x00`. The diagnostic prints `configured; LEDs at 0x00`. Watch the TMP117
before, during and after that transition.

### Stage 3: production LED current and FIFO polling

```powershell
pio run -d diagnostics/tmp117_with_max -e tmp117-max-stage3
pio run -d diagnostics/tmp117_with_max -e tmp117-max-stage3 -t upload --upload-port COM6
pio device monitor --port COM6 --baud 115200
```

This uses the same red/IR pulse amplitude as the main firmware (`0x24`) and
polls the MAX FIFO. It prints `max_samples`, `last_ir`, `last_red` and a bus
scan every five seconds, plus TMP117 reads every second.

### Interpretation

| Observation | Next check |
|:---|:---|
| TMP117 fails in stage 1 | MAX `begin`/identity interaction, shared bus, power or wiring |
| TMP117 passes stage 1 but fails in stage 2 | MAX full setup or transient LED current; check rail/ground and the setup transition |
| TMP117 passes stage 2 but fails in stage 3 | MAX LED current/FIFO activity or rail droop under optical load |
| TMP117 passes all three stages | The earlier disappearance is intermittent; repeat with the main firmware and record the full log |

Do not "fix" a failure by lowering MAX LED current, changing thresholds,
hard-coding the TMP117 address or weakening identity checks. First determine
whether the 3.3 V rail, ground return, pull-ups or the assembled breadboard is
marginal.

## 5. Stage C: main firmware

Only after the diagnostics are understood and you have permission:

```powershell
pio run -e esp32-s3-devkitc-1
pio run -e esp32-s3-devkitc-1 -t upload --upload-port COM6
pio device monitor --port COM6 --baud 115200
```

Capture at least the first two minutes and then a five-minute steady period.
Record:

- Startup bus scan: `0x3C` OLED, `0x57` MAX30102 and one TMP117 candidate.
- `Found TMP117 at 0x...`, `WHO_AM_I=0x117`, `config=0x1A0` (or `0x01A0`).
- MAX30102 initialization and `PART_ID=0x15`.
- `tmp117_sensor_temperature_c`, `tmp117_sensor_temperature_raw`,
  `tmp117_sensor_temperature_timestamp_ms` and
  `tmp117_sensor_temperature_status` in each `[JSON]` line.
- `wrist_contact_status="unverified"`, `wrist_skin_temperature_c=null`,
  `estimated_core_temperature_c=null` and
  `fever_screening.status="not_available"`.
- Any `i2c_address_nack`, `i2c_data_nack`, `stuck_bus_raw_pattern`,
  `data_not_ready`, `abrupt_change_pending_confirmation` or repeated
  `sensor_error`.

### TMP117 acceptance

- Address is discovered in `0x48`-`0x4B`; `WHO_AM_I` is `0x0117`.
- Configuration writable-mask readback is `0x01A0`.
- The raw register is not `0x0000` or `0xFFFF`.
- The converted value matches the signed big-endian conversion.
- Readings are plausible for the bench environment and do not jump wildly
  without a confirming sample.
- TMP117 remains present while the MAX30102 is active.
- The actual TMP117 value is displayed separately. It is **not** copied into the
  wrist metric and does not create a core or fever result.

A normal room-temperature reading does not prove clinical accuracy. Compare only
against a suitable reference if one is available; do not use a finger, mouth or
another uncalibrated thermometer as a reference.

## 6. Stage D: MAX30102 fingertip test

Use the main firmware and a monitor capture first. Do not start the bridge until
the monitor is closed.

1. Confirm the MAX30102 `PART_ID` is `0x15`.
2. Rest the fingertip gently over the red/IR optical window. Cover the window,
   keep the finger still and avoid pressing hard.
3. Wait at least four seconds for a complete 100-sample window. The effective
   sample rate is 25 Hz, so a window takes about four seconds.
4. Watch `raw_ir`, `raw_red`, `finger_on`, `optical_signal_quality`,
   `heart_rate`, `heart_rate_status`, `spo2` and `spo2_status`.
5. Repeat with the finger removed to confirm the no-contact path.

### Expected signal behavior

- No finger or poor contact: raw values below the DC floor, `finger_on=false`,
  statuses such as `not_available` or `low_quality`, and no invented pulse value.
- Finger present: raw IR and red above the DC floor; `finger_on=true`.
- A completed good window: `optical_signal_quality="good"` and a valid pulse or
  SpO2 estimate only if the algorithm accepts the window.
- A completed low-quality window: `low_quality` is retained while the next
  window fills; it must not immediately flip back to `warming_up`.
- The first partial window may legitimately show `warming_up`.

The current guards require a mean IR DC of at least 50,000, an AC amplitude of
at least 1,000 and a perfusion index of at least 0.10. Do **not** lower these
values merely to make a number appear. Check placement, motion, ambient light,
finger temperature and the 3.3 V supply first.

A MAX30102 pulse/SpO2 estimate is not a calibrated medical measurement. No
clinical accuracy claim is made.

## 7. Stage E: bridge, API, database and dashboard

Close the serial monitor first, then start the bridge:

```powershell
python telemetry_bridge.py --serial-port COM6
```

Open:

```text
http://localhost:8080/index.html
```

The bridge binds to `127.0.0.1` only. In another PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/api/telemetry | ConvertTo-Json -Depth 20
Invoke-RestMethod "http://127.0.0.1:8080/api/history?device_id=RPM-NODE-01&seconds=900" | ConvertTo-Json -Depth 20
```

Check the live response under `latest.vitals` and `latest.sensors`:

- `sensors.tmp117=true` when the TMP117 is present.
- `tmp117_sensor_temperature_c` is a number only when the matching raw,
  timestamp and status are valid.
- `wrist_contact_status="unverified"`.
- `wrist_skin_temperature_c=null`, `wrist_skin_temperature_raw=null` and
  `wrist_skin_temperature_timestamp_ms=null`.
- `estimated_core_temperature_c=null`.
- `fever_screening.status="not_available"` with the confirmation-required
  message.
- MAX raw values and statuses correspond to the live finger state.

Inspect the SQLite diagnostic columns without deleting data:

```powershell
@'
import sqlite3
con = sqlite3.connect("data/telemetry.sqlite3")
con.row_factory = sqlite3.Row
rows = con.execute(
    "SELECT recorded_at, heart_rate, spo2, wrist_skin_temperature, "
    "tmp117_sensor_temperature, tmp117_sensor_temperature_raw, "
    "tmp117_sensor_temperature_timestamp_ms, tmp117_sensor_temperature_status "
    "FROM observations ORDER BY id DESC LIMIT 5"
).fetchall()
for row in rows:
    print(dict(row))
con.close()
'@ | python -
```

Expected database behavior:

- `tmp117_sensor_temperature` is populated only for a valid actual TMP117
  reading.
- `wrist_skin_temperature` remains null while contact is unverified.
- Existing rows are preserved; the migration is additive.
- The actual TMP117 diagnostic column is not the clinical wrist metric and is not
  used for core/fever logic.

The history API returns the clinical trend series. It is allowed to contain gap
values for unavailable wrist temperature; it must not contain a fabricated wrist
value derived from the actual TMP117 sensor reading.

Stop the bridge with `Ctrl+C` when finished.

## 8. Power and bus checks if TMP117 disappears

Perform these with the system powered from USB, using a multimeter, and with the
MAX30102 active if possible:

1. Measure TMP117 VIN to TMP117 GND. Record the value at idle and while the MAX
   red LED is active. It should remain at the 3.3 V rail, not sag toward 3.0 V or
   below.
2. Measure the ESP32-S3 3.3 V pin to a known ground. Compare it with the TMP117
   VIN measurement.
3. Check TMP117 GND to ESP32-S3 GND continuity. A shared breadboard rail can
   look connected but have a high-resistance joint.
4. Check TMP117 SDA/SCL continuity from the module pins to GPIO 8/9 under the
   same physical arrangement used during the test.
5. Inspect the ADD strap and confirm only one TMP117 address is intended.
6. Check the shared pull-ups. Multiple breakouts can create a very strong
   pull-up; record the resistance and do not add another pull-up blindly.
7. Reseat or replace the TMP117 jumpers and try a short, direct connection.
8. If available, power the TMP117 from a separate regulated 3.3 V source with a
   common ground for a diagnostic comparison. Do not use 5 V.
9. Repeat stage 1, 2 and 3 after each physical change. Change one variable at a
   time.

If the TMP117 is stable only when the MAX30102 LEDs are off, record that result
and stop. Do not hide it by lowering the LED current or by relaxing the sensor
checks. The next step is an electrical review of the 3.3 V rail, ground return
and decoupling, not a fabricated temperature.

## 9. Acceptance summary

| Area | Pass condition | What a pass does not prove |
|:---|:---|:---|
| TMP117 identity | Address in `0x48`-`0x4B`, `WHO_AM_I=0x0117` | Clinical accuracy |
| TMP117 configuration | Writable-mask readback `0x01A0` | That the sensor is thermally coupled to a body |
| TMP117 stability | Five minutes standalone and coexistence without NACK | That the assembled device will always be reliable |
| TMP117 under MAX load | Present and readable in stage 2 and stage 3 | That the rail has adequate margin at every temperature/current |
| MAX30102 identity | `PART_ID=0x15`, 3.3 V, shared bus | Correct pulse or SpO2 |
| MAX30102 contact | Raw IR/red above floor, `finger_on=true` | A medically valid reading |
| MAX30102 quality | Completed good window with accepted output | Clinical calibration |
| Bridge | Valid packets accepted, invalid packets rejected | Sensor accuracy |
| Database | Actual TMP stored as diagnostic; wrist remains null | That actual TMP is wrist/core temperature |
| Dashboard | Actual sensor and clinical wrist shown separately | Fever or core-temperature capability |
| Safety | Wrist contact unverified, core null, fever unavailable | Any clinical use |

## 10. What to capture for the final test record

- Date, board, port name and build command.
- Firmware build string from each diagnostic and from the main firmware.
- I2C scan results, TMP117 address, `WHO_AM_I`, configuration and offset.
- Standalone five-minute TMP117 log summary.
- Stage 1, stage 2 and stage 3 observations, especially the transition where
  TMP117 disappears.
- Main-firmware boot log and a five-minute steady log.
- MAX30102 `PART_ID`, raw IR/red with and without a finger, quality state and
  accepted/rejected output.
- API responses and SQLite diagnostic rows.
- Any physical change (jumper, power source, seating, ADD strap) and the result.
- A statement that no value is promoted to wrist, core or fever without the
  required evidence.

Do not include patient identifiers in saved logs. Do not commit or push test
artifacts unless explicitly requested.
