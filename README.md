# IoMT Remote Patient Monitoring (RPM) Node

An ESP32-S3 powered Internet of Medical Things (IoMT) node for continuous, non-invasive vital signs monitoring, fall detection, and emergency alerting. Built with **C++ / PlatformIO** (Arduino framework).

## 🏥 Overview

Multi-sensor wearable patient monitoring node with an onboard OLED display, dual-bus I2C architecture, and structured JSON telemetry over serial for dashboards and alert checkers.

### Key Features
- **Heart Rate & SpO₂** — MAX30102 optical pulse oximeter (I2C Bus 0: `0x57`)
- **Object/Surface & Ambient Temperature** — MLX90614 contactless IR thermometer (I2C Bus 0: `0x5A`)
- **Motion & Fall Detection** — MPU-6050 6-axis IMU (Dedicated I2C Bus 1: `0x68` / `0x69`)
- **OLED Display** — SSD1306 128×64, real-time vitals dashboard (I2C Bus 0: `0x3C`)
- **SOS Emergency Button** — GPIO 5, internal pull-up, active LOW
- **Dual Hardware I2C Buses** — Dedicated bus for MPU-6050 to prevent bus congestion
- **Telemetry Stream** — Compact single-line JSON stream at 115200 baud (verbose cards are opt-in)

---

## 📁 Project Files

| File | Purpose |
|:---|:---|
| `src/main.cpp` | Complete firmware — dual I2C buses, sensor drivers, fallback registers, OLED rendering, and JSON streaming |
| `platformio.ini` | PlatformIO environment config for ESP32-S3 N16R8 (16 MB flash / 8 MB OPI PSRAM) |
| `index.html` / `dashboard.html` | Live dashboard (dashboard.html redirects to index.html); local SSE bridge with recorded trends and patient baseline views |
| `telemetry_bridge.py` | USB serial reader, localhost web server and fresh-packet SSE stream |
| `ai_decision_engine.py` | Python serial listener that evaluates vitals against baseline alert thresholds |
| `wiring-guide.html` | Interactive hardware pinout and wiring reference |

---

## 🛠️ Hardware & Pin Configuration (ESP32-S3)

### Primary I2C Bus (`Wire` - Bus 0 at 50 kHz)
| Component | SDA Pin | SCL Pin | I2C Address | Notes |
|:---|:---|:---|:---|:---|
| **SSD1306 OLED** | GPIO 8 | GPIO 9 | `0x3C` | Real-time screen |
| **MAX30102 Pulse Ox** | GPIO 8 | GPIO 9 | `0x57` | Pulse & SpO2 |
| **MLX90614 IR Temp** | GPIO 8 | GPIO 9 | `0x5A` | 3.3V operation, SMBus compliant |

### Dedicated Secondary I2C Bus (`Wire1` - Bus 1 at 400 kHz)
| Component | SDA Pin | SCL Pin | I2C Address | Notes |
|:---|:---|:---|:---|:---|
| **MPU-6050 IMU** | GPIO 17 | GPIO 18 | `0x68` / `0x69` | Dedicated bus for fast motion & fall tracking |

### Peripherals
| Component | Pin | Configuration | Notes |
|:---|:---|:---|:---|
| **SOS Pushbutton** | GPIO 5 | `INPUT_PULLUP` | Connect other side to GND (Active LOW) |

> 💡 **Sensors & Power**: All sensor breakout boards operate on the 3.3V rail and include onboard I2C pull-up resistors.

---

> ⚕️ **Disclaimer**: This is an educational and engineering prototype. Vital sign calculations are approximations and are not intended to diagnose disease or prescribe medical treatments.

---

## 📡 Telemetry Format

Single-line JSON output over serial at `115200` baud:

```json
[JSON] {"schema_version":2,"uptime_s":45,"device_id":"RPM-NODE-01","risk":"UNKNOWN","sensors":{"oled":true,"mpu":true,"mlx":false,"max":true,"active":3},"vitals":{"heart_rate":null,"spo2":null,"finger_on":false,"raw_ir":721,"raw_red":1040,"temp_core":null,"temp_object":null,"temp_skin":null,"temp_amb":null,"steps":0,"motion_g":1.03},"alerts":{"sos":false,"fall":false},"status_summary":"Waiting for valid optical readings; unavailable measurements are null."}
```

### Alert Thresholds
| Condition | Threshold | System Action |
|:---|:---|:---|
| Low Heart Rate | BPM < 50 | Warning flag — notify caregiver |
| High Heart Rate | BPM > 120 | Warning flag — notify caregiver |
| Low SpO₂ | < 90% | Warning flag — notify caregiver |
| Temperature | Object/surface and ambient only | No core-temperature estimate or core-temperature alerts |
| Fall Detection | Below 0.6g then above 2.5g within 60–600ms | Emergency alert — check on patient |
| SOS Button | GPIO 5 pressed | Emergency alert — check on patient |

---

## 🚀 Building & Flashing

```bash
pio device list
pio run
pio run -t upload --upload-port /dev/ttyACM0
python3 telemetry_bridge.py --serial-port /dev/ttyACM0
```

Open **http://localhost:8080/index.html**. On Windows, substitute the actual COM port.
The firmware uses the USB-to-UART connector, not native USB CDC. Only one program
should own the serial port: close PlatformIO monitor before starting the bridge.
The bridge supplies the dashboard automatically. Keep it running to record data
even when the browser is closed. The dashboard opens in light mode by default.

On Arch/CachyOS, serial ports usually belong to `uucp`. A temporary, user-only grant:

```bash
sudo setfacl -m u:"$USER":rw /dev/ttyACM0
```

Reconnecting USB may remove this grant. A persistent option is adding your account
to `uucp` and logging out and back in. Do not make the device world-writable.

### Live Monitoring Interfaces

1. **Terminal Stream**: Run `pio device monitor` to see raw JSON packets. `RPM_VERBOSE_TELEMETRY=1` also enables verbose cards for diagnostics, but can interrupt optical sampling.
2. **Web Dashboard**: Run the local bridge and open `http://localhost:8080`. View measurements, recorded trends, patient reference coverage and items for clinician review.
3. **Threshold Alert Engine (`ai_decision_engine.py`)**: Run `python ai_decision_engine.py COM6` to inspect incoming packets and print status cards.

---

## 📋 Alert Behavior

When any alert condition is met:
1. **OLED Display** — Shows an emergency override screen (`EMERGENCY ALERT` / `SOS CALL` / `FALL ALERT`).
2. **Serial Stream** — Immediately flags `"risk": "EMERGENCY"` or `"WARNING"` with an alert description.
3. **Dashboard / Console** — Highlights the affected parameter and prompts the user to check on the patient.

---

## 🔮 Future Scope & Planned Sensors (ਬਾਕੀ ਰਹਿੰਦੇ ਸੈਂਸਰ / Roadmap)

Currently, the device captures the primary 4 vital metrics (**Pulse, SpO₂, Temperature, and Fall/Motion**). To evolve this prototype into a comprehensive clinical-grade Remote Patient Monitoring (RPM) system, the following sensors and modules are planned for future integration:

| Sensor / Module | Primary Medical Purpose | Target Interface | Clinical Value |
|:---|:---|:---|:---|
| **AD8232 / MAX30003** | Single-Lead ECG (Electrocardiogram) | SPI / Analog ADC | Detects arrhythmias, atrial fibrillation, and Heart Rate Variability (HRV). |
| **GSR / EDA Sensor** | Galvanic Skin Response (Skin Conductance) | Analog ADC | Measures stress, anxiety, emotional arousal, and sympathetic nervous response. |
| **Cuffless BP (PTT)** | Blood Pressure Estimation (Systolic/Diastolic) | Algorithm (ECG + PPG) | Uses Pulse Transit Time between ECG R-peak and MAX30102 PPG peak for continuous BP. |
| **Respiration Sensor** | Respiratory Rate & Breathing Effort | Piezoelectric / PPG-derived | Tracks breaths-per-minute for asthma, COPD, and sleep apnea monitoring. |
| **NEO-6M / NEO-8M** | GPS Location Tracker | Hardware UART | Emergency geolocation dispatch for elderly fall victims or Alzheimer's geo-fencing. |
| **BME680 / BME280** | Ambient Air Quality, Humidity & Temp | I2C (Bus 0) | Monitors environmental factors triggering respiratory attacks. |
| **BLE / MQTT Cloud** | Wireless Telemetry & Mobile App Sync | ESP32-S3 WiFi/BLE | Streams patient telemetry directly to cloud databases (AWS IoT/Supabase) and caregiver apps. |



## Live-data behavior and validation

- No demo patients, generated ECG, fake packet counts, fixed temperature offsets,
  or made-up stability scores. Sensor status is counted from device flags.
- JSON `null` and dashboard `—` mean unavailable. Zero motion and zero/negative
  measured temperatures remain valid numbers. Core temperature is always `null`.
- MAX30102 runs at 100 Hz with averaging of 4, matching the Maxim algorithm's
  25 samples/sec. Paired FIFO samples form a four-second window, updated each second.
  Results require algorithm validity flags; saturation, removal or sampling gaps
  clear the window. These are prototype estimates, not calibrated clinical measurements.
- MPU6050/MPU6500 acceleration uses checked register reads at ±8g. Unsupported chip
  identities are rejected; failed reads no longer substitute 1g.
- MLX90614 object and ambient readings are reported directly, without a +3°C offset.
- The bridge marks the device live only after valid JSON and expires it after five
  seconds without a fresh packet. SSE heartbeat replays do not increment counters.
- Device details show actual uptime and memory. The chart supports 15-minute,
  one-hour and 24-hour windows, a measurement cursor and CSV export.
- Clinician review notes are browser-local and cannot clear hardware alerts.

Run software regression checks with `python3 -m unittest discover -s tests -v`.

### Hardware check on 2026-10-11

The updated firmware was uploaded and its flash hashes verified on `/dev/ttyACM0`.
The programmer identified an ESP32-S3 revision 0.2 with embedded 8 MB PSRAM.
Final firmware telemetry reported 16,777,216 flash bytes and 8,386,279 usable
PSRAM bytes, confirming the N16R8 configuration at runtime.
Live packets confirmed OLED and MAX30102 online and motion around 1.03–1.04g.
The IMU returned WHO_AM_I `0x70` (MPU6500-compatible register interface).
MLX90614 did not respond at `0x5A`; check its power, ground and GPIO 8/9 wiring.
An additional I2C ACK at `0x03` was observed but its device identity is unverified.
No finger was detected during the initial capture, so heart rate and SpO₂ were
correctly unavailable. A later live browser capture showed algorithm estimates of
100 BPM and 93% SpO₂; after finger removal both returned to unavailable.
This confirms data flow, not measurement accuracy, temperature functionality,
or a physical fall/SOS test. The temperature sensor still needs investigation.


## Local clinician dashboard

The interface is for a doctor reviewing a patient, with no automated healthy/unhealthy
verdict. All current work stays local; remote sharing and the proposed later JEV
model are outside this implementation.

- **Patient overview:** measured signals, time-series history, baseline context,
  device alerts, sensor availability and a clinician review form.
- **Patient baseline:** explicitly enroll a patient name or reference. Each metric
  requires seven elapsed days and seven days containing at least 30 distinct sampled
  minutes. A sampled minute contains one or more valid measurements, not necessarily
  a full minute of continuous recording. Missing values never fill coverage.
- **Comparison:** each ready metric freezes its median and a MAD-based range with
  engineering noise floors. Three consecutive departures produce an observation;
  these are prototype statistical comparisons, not clinical diagnostic thresholds.
- **Temperature:** the unavailable MLX90614 channel stays visible and builds its own
  reference once measurements arrive; other metrics can become ready independently.
- **Storage:** the bridge stores up to 30 days of recordings in
  `data/telemetry.sqlite3` (excluded from Git). Baselines persist across restarts.
  The latest clinician review is saved separately in this browser for the active
  enrollment. Clearing browser storage removes that note, but not SQLite recordings.
- **Appearance:** light mode is the initial default; an explicitly selected dark
  mode persists in the browser. Desktop and mobile use the same live data source.
