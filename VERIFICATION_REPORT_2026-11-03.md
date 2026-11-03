# Project and Connected-Device Verification — 2026-11-03

> This is the initial audit, before the later MAX30102 repair. The UART sampling
> fault and V-02 optical-contract mismatch have since been fixed and firmware
> `rpm-2.1.1` uploaded. Both OLED and dashboard readings were confirmed by the
> user. See [the subsequent repair report](MAX30102_FIX_REPORT_2026-11-03.md)
> for current optical evidence and measurement limitations.

## Result

**Partially working. The ESP32-S3 is connected and transmitting genuine telemetry,
but the MPU motion sensor is offline. Full system operation is not established.**

This assessment uses this checkout (`1849d8f`), the actual COM3 serial stream,
fresh host tests, HTTP/SSE integration checks, and source review. Historical audit
claims were not counted as current test results. The user selected automatic
checks only. No firmware was uploaded and application source was not changed.

## Live hardware results

| Component | Current evidence | Result |
|---|---|---|
| USB / ESP32-S3 | CH343 USB serial on COM3, 115200 baud; ESP32-S3 ROM boot and monitoring firmware `rpm-2.1.0`; reports 16 MB flash and approximately 8 MB usable PSRAM | PASS: connected and transmitting |
| Installed sensor inventory | Every captured packet reports `active: 2`, `active_max: 3` | PARTIAL: one measurement sensor missing |
| TMP117 | Address `0x49`, identity `0x0117`, expected writable configuration `0x01A0`, zero hardware offset; valid raw codes and temperatures for more than five minutes | PASS: acquisition and transport; accuracy against a reference NOT RUN |
| MAX30102 | Address `0x57`, part ID `0x15`, changing red/IR counts; no finger detected; HR and SpO2 correctly remain null | PARTIAL: detection/raw acquisition pass; finger measurement and accuracy NOT RUN |
| MPU-6050/6500 | No ACK on GPIO 17/18 bus scan; `present: false`, `not_found_or_unsupported`, calibration unavailable; motion/gyro/steps null | FAIL: unavailable throughout this run |
| SSD1306 OLED | Address `0x3C` ACKs and initialization reports online | PARTIAL: bus detection passes; visible rendering NOT RUN |
| SOS input | Boot reports GPIO 5 released; no physical press during capture | NOT RUN physically; isolated simulated event test passes |
| Fall detection | MPU absent; no physical fall stimulus | BLOCKED by missing MPU |
| Wrist/core temperature | Wrist contact unverified; wrist and core values remain null; fever screening unavailable | Expected implemented behavior; no clinical wrist/core measurement |

The completed UTF-8 capture contains **585 accepted packets over 584 seconds
(9 minutes 44 seconds)**, with exactly one-second device-uptime increments, zero
rejections and zero reported TMP117 errors. TMP117 readings in that capture were
**28.89–29.11 °C**. MPU was absent in all 585 packets; none reported finger
contact, SOS or fall. These numbers describe the saved capture, not a reference
thermometer comparison or the current temperature after monitoring continued.

The previous integrated TMP117 dropout was **not reproduced** in this observation.
This does not prove the earlier problem permanently resolved. No standalone or
MAX coexistence diagnostic firmware was flashed in this session.

The initial 20-second serial capture also preserved the boot scan. That capture
used .NET's default serial text encoding, which replaced UTF-8 punctuation. All
protocol validation and longer monitoring use the subsequent UTF-8 pyserial log.

## Software and integration results

| Check | Result |
|---|---|
| Python suite, `python -m pytest -q` in isolated Python 3.13 environment | **64 passed** |
| Same suite using default Python 3.14 standard-library unittest discovery | **64 passed** |
| Node dashboard core suite | **10 passed** on Node v22.19.0 |
| `node --check` for both dashboard JavaScript files | PASS |
| `py_compile` for all five application Python modules | PASS |
| Main ESP32-S3 firmware build | PASS; RAM 26,112 bytes, application image 430,436 bytes |
| Standalone TMP117 raw diagnostic build | PASS |
| TMP117/MAX coexistence diagnostic stages 1, 2 and 3 | PASS for all three checked environments |
| Dashboard HTML, redirect page, wiring guide, CSS, JavaScript, font | HTTP 200 |
| Telemetry, history, baseline and events GET APIs | HTTP 200 |
| Live SSE | Three consecutive connected events with advancing device uptime and genuine TMP117 values |
| Live SQLite recording | Genuine TMP117 diagnostic values persisted; unavailable clinical readings remain null; integrity check `ok` |
| Invalid history parameter | HTTP 400 |
| GET access to source code and database paths | HTTP 404 |
| Eight isolated HTTP integration checks | PASS: enrollment start/end, simulated SOS recording/deduplication, cross-origin rejection, wrong-device rejection, stale telemetry hiding, disconnected enrollment rejection |
| Visual browser validation | NOT RUN: browser automation stopped because Windows browser URL-policy enforcement is unsupported |

The eight isolated HTTP checks used an in-memory database and a copied live
packet. Their simulated SOS did not enter the live serial log or live database.
Unit tests and HTTP checks do not establish physical OLED, SOS or fall behavior.

All five checked firmware targets built with PlatformIO 6.2.0, Espressif platform
8.0.0, Arduino ESP32 3.3.12 and Xtensa compiler 14.2.0. These binaries were not
uploaded. Nonfatal warnings remain: the SparkFun I2C buffer macro redefinition,
upstream unused-variable/parentheses warnings, and `%u` versus `uint32_t` format
warnings at `src/main.cpp:1180` and `src/main.cpp:1628` under the new toolchain.
Use matching explicit casts or portable integer format macros when addressing
the application warnings. The build is successful, but not warning-free.

## Newly reproduced software findings

### V-01 — Uncaught malformed-packet exceptions can terminate serial acquisition

**Priority: medium.** `telemetry_bridge.py:98` converts integers through
`math.isfinite`/`float` without handling overflow. A valid JSON packet with
`uptime_s = 10**400` raises `OverflowError`. Approximately 1,100 nested arrays
also raise `RecursionError` from `parse_packet` at line 458. The serial loop at
line 602 catches only serial/OS exceptions, so these inputs escape its worker.

Reproduced directly against a copy of a real packet in a separate process; these
inputs were not injected into the live bridge. Ordinary captured packets did not
trigger the issue. Reject oversized/deep inputs and contain parsing/validation
errors so the next valid packet can still be processed.

### V-02 — Firmware and bridge disagree on optical perfusion range

**Priority: medium.** `telemetry_bridge.py:46` restricts
`optical_perfusion_index` to `0..20`. `src/sensor_math.h` only applies a minimum
perfusion threshold. `src/main.cpp:885` computes the index and line 1296 emits it
when quality is good, without that upper bound. For example, mean 100,000 counts
and peak-to-peak amplitude 30,000 give PI 30%, which the firmware quality helper
allows and the bridge rejects.

A copied schema-valid packet with PI 25 was rejected. This drops the entire
packet, including any SOS/fall fields it carries. Align producer and consumer
constraints and add a regression covering high-variation optical windows. This
path was established by source and a contract probe, not observed with a finger.

### V-03 — Measurement timestamps are not checked for age

**Priority: low / validation hardening.** A copied live packet with a valid
TMP117 value but `tmp117_sensor_temperature_timestamp_ms = 1` is accepted at
device uptime of several hundred seconds. The bridge checks nonnegative
timestamps and packet arrival freshness, but does not independently verify sensor
sample age against device uptime. Current firmware has its own stale checks;
no stale TMP117 sample was observed. Define age bounds and uptime-wrap behavior
before adding bridge-side enforcement.

## Project structure and documentation observations

- `src/main.cpp` implements acquisition, local OLED output and SOS/fall logic.
- `telemetry_bridge.py` provides serial validation, localhost HTTP and SSE;
  `telemetry_store.py` persists observations in SQLite.
- `personal_baseline.py` implements per-metric seven-day median/MAD references.
  `ai_decision_engine.py` is a rule-based threshold consumer, rather than a
  trained inference model.
- The running application binds to `127.0.0.1`; this checkout implements local
  USB monitoring and does not provide an internet-accessible remote service.
- The default Python 3.14 initially lacked pytest, pyserial and PlatformIO.
  Dependencies were installed in the ignored audit environment instead of
  changing the global Python installation. No requirements manifest is present.
- Root README/cleanup records still quote 62 Python tests; the current suite has
  64. `management/TOOLCHAIN.md` shows native USB CDC enabled, while the actual
  build disables it. Its listed tool versions do not describe this machine.
- Documentation describing an all-or-nothing baseline is outdated: the current
  code allows individual metrics to become ready. The wrist metric still cannot
  qualify while contact remains unverified; full readiness remains unavailable.
- `platform = espressif32` and caret library constraints are unpinned. A fresh
  build resolved platform 8.0.0, rather than the historical version recorded in
  management documents. Build results must identify the resolved toolchain.

## Evidence and local running environment

Audit files are under ignored `data/verification-2026-11-03/`:

- `initial-serial-COM3.log`: original boot scan and initial telemetry.
- `live-serial-COM3.log`: UTF-8 serial lines from the actual device.
- `serial-summary.json`: packet counts, duration, temperature range and statuses.
- `live.sqlite3`: genuine live observations for this audit; no patient enrollment.
- `http-checks.json`, `isolated-http-checks.json`, `validation-probes.json`.
- `capture_bridge.py`, `http_integration.py`, `collect_summary.py`: audit utilities.
- `venv/`: isolated Python/serial/PlatformIO environment.
- `main-build.log`: fresh firmware build output.
- `tmp117-raw-build.log`, `tmp117-max-stage1-build.log`,
  `tmp117-max-stage2-build.log`, `tmp117-max-stage3-build.log` and
  `diagnostic-build-results.json`: diagnostic build evidence.

The audit bridge runs at <http://localhost:8080/index.html> using the isolated
audit database. It owns COM3; close it before opening a serial monitor or uploader.

To restart it from the repository root:

```powershell
& .\data\verification-2026-11-03\venv\Scripts\python.exe telemetry_bridge.py --serial-port COM3 --database data\verification-2026-11-03\live.sqlite3
```

## Next actions

1. With power disconnected, check MPU VCC/common GND, SDA to GPIO 17, SCL to
   GPIO 18, and AD0 address selection. The current evidence cannot distinguish
   wiring, power, module failure or a different device without physical access.
2. Resolve V-01 and V-02 and add targeted regression coverage.
3. Perform steady-finger HR/SpO2 checks, inspect OLED text, press/cancel SOS, and
   validate motion/gyro/fall behavior once MPU is online.
4. Compare measurements against appropriate reference instruments before claiming
   accuracy. Keep clinical wrist/core values unavailable under the present design.
5. Reconcile the audit documentation with source behavior and pin the verified
   build dependencies for repeatable builds.
