# Connected ESP32 check — 2026-11-17

Result: software checks pass; the assembled sensor system does not pass the live hardware check.

## Software and controller

- Connected serial device: `/dev/ttyACM0`, USB VID:PID `1A86:55D3`.
- Linux initially denied serial access. The user granted a device ACL and serial access then worked.
- `.venv/bin/pytest -q`: **134 passed, 5 subtests passed**. Six HTTP tests required execution outside the socket-restricted sandbox; all passed on that rerun.
- `node --test tests/dashboard_core.test.js`: passed.
- `pio run -e esp32-s3-devkitc-1`: passed, RAM 23,904 / 327,680 bytes and flash 327,521 / 6,553,600 bytes.
- Main firmware uploaded successfully with verified flash hashes. ESP32-S3 revision v0.2, 16 MB flash, firmware-reported PSRAM 8,386,263 bytes.
- Local HTTP endpoints `/api/telemetry`, `/api/optical`, `/api/priority`, `/api/care` and `/index.html` returned HTTP 200. Both model services reported no model-loading error.
- Actual local Jeff/Qwen calls were exercised with explicitly simulated readings: one of four summaries completed, three were withheld by grounding checks, none returned a model-call error. This is partial functional evidence, not four successful explanations or a test on real vitals.

## Physical findings

An unmodified main-firmware capture stopped producing output after its primary I2C scan heading during the short capture. Targeted temporary instrumentation established that the scan was progressing through slow timeouts rather than proving a permanent CPU lockup.

A temporary build printed bus pin levels and scanned the expected primary addresses plus the two MPU addresses. It reported:

- Primary SDA GPIO 8 **LOW**, SCL GPIO 9 **HIGH** before probing, and the same levels before every primary probe.
- OLED `0x3C`, TMP117 candidates `0x48`–`0x4B`, MAX30102 `0x57`: every probe returned Wire result **5 (timeout)**.
- MPU bus GPIO 17/18: neither `0x68` nor `0x69` ACKed.
- Initialization reported OLED, MAX30102, TMP117 and MPU offline; telemetry reported **0/3** measurement sensors online and null vitals.
- GPIO 5 initially read LOW and an SOS event was generated. The event later cleared. A correctly wired, released button should read HIGH; its wiring/physical state still needs checking.
- Near the end of the diagnostic capture, `HOT-PLUG SSD1306 online` appeared once. This is evidence of intermittent bus behavior; it does not validate visible OLED pixels or establish that all sensors recovered.
- User observed only the ESP32 red light and occasional blue light, no visible sensor/display output.

These observations indicate a shared-bus electrical/connection problem is a leading hypothesis. They do **not** identify a particular failed sensor, prove a rail voltage, or distinguish a short from an unpowered/held-low peripheral without physical isolation and measurements.

## Cleanup and next physical checks

Temporary instrumentation was removed, the source restored byte-for-byte to its pre-test content, and the standard main firmware rebuilt and uploaded successfully. Existing source changes were preserved. The live bridge test used a separate `/tmp` database; the simulation used its in-memory database.

Disconnect USB before changing wires. Check common ground and 3.3 V at each module, SDA GPIO 8 / SCL GPIO 9 on the primary bus, and SDA GPIO 17 / SCL GPIO 18 on the MPU bus. Verify GPIO 5 is not tied to ground when the SOS button is released. Isolate primary-bus modules one at a time to identify what holds SDA LOW. Re-run live tests after correcting the connections.

HR/SpO2 contact measurement, temperature stability, MPU calibration/motion, OLED pixels, and a deliberate SOS press/release remain unverified. No calibration or clinical accuracy claim follows from these checks.

Diagnostic serial evidence and simulated AI output: `data/hardware-check-2026-11-17/`.
