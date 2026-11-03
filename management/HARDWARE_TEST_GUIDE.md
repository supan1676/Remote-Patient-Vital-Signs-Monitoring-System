# Physical Hardware Test & Verification Guide

- Document ID: MGT-HTG-001
- Version: 1.1.0 (Evidence-Corrected)
- Date: 2026-11-02
- Target Platform: ESP32-S3 N16R8, Windows 11, PowerShell
- Author: Chief Engineering Manager, Hardware & Safety Specialist Agents

---

## 1. Safety & Operational Constraints

> [!CAUTION]
> **ELECTRICAL SAFETY RULES:**
> - All sensors (MAX30102, TMP117, MPU-6050, SSD1306) MUST be powered strictly from the **3.3V rail**.
> - DO NOT connect any sensor VCC or pull-up to the 5V / VIN rail. ESP32-S3 GPIO pins are NOT 5V tolerant and will be permanently damaged.
> - Ensure all ground connections (GND) share a single common ground bus on the breadboard.

> [!IMPORTANT]
> **FIRMWARE UPLOAD & SERIAL PORT RULES:**
> - Never run firmware upload while `telemetry_bridge.py` is running, as both require exclusive access to the serial COM port.
> - Always terminate the Python bridge (`Ctrl+C`) before flashing firmware.

---

## 2. Wiring Verification Checklist

Confirm physical connections on your breadboard before applying power:

### Primary I2C Bus (Bus 0 — Low Speed @ 50kHz)
| Component | Pin Label | ESP32-S3 Pin | Voltage Rail | Notes |
|---|---|---|---|---|
| **ESP32-S3** | 3V3 / GND | — | 3.3V Output | Power source for breadboard rail |
| **TMP117** | VIN / GND | 3.3V / GND | 3.3V | 7SEMI breakout (ADDR strapped to VCC -> 0x49) |
| **TMP117** | SDA / SCL | GPIO 8 / GPIO 9 | 3.3V Logic | Primary I2C data / clock lines |
| **MAX30102** | VIN / GND | 3.3V / GND | 3.3V | Optical PPG sensor (Address 0x57) |
| **MAX30102** | SDA / SCL | GPIO 8 / GPIO 9 | 3.3V Logic | Shared on Primary I2C |
| **SSD1306 OLED** | VCC / GND | 3.3V / GND | 3.3V | 128x64 display (Address 0x3C) |
| **SSD1306 OLED** | SDA / SCL | GPIO 8 / GPIO 9 | 3.3V Logic | Shared on Primary I2C |

### Secondary I2C Bus (Bus 1 — High Speed @ 400kHz)
| Component | Pin Label | ESP32-S3 Pin | Voltage Rail | Notes |
|---|---|---|---|---|
| **MPU-6050** | VCC / GND | 3.3V / GND | 3.3V | 6-axis IMU (Address 0x68) |
| **MPU-6050** | SDA / SCL | GPIO 17 / GPIO 18 | 3.3V Logic | Isolated high-speed bus |

### User Input (SOS Emergency Button)
| Component | Pin Label | ESP32-S3 Pin | Voltage Rail | Notes |
|---|---|---|---|---|
| **Push Button** | Terminal 1 | GPIO 5 | Logic Input | Internal pull-up active |
| **Push Button** | Terminal 2 | GND | Ground | Closes circuit to GND when pressed |

---

## 3. The 6 Exact Physical Tests Remaining to Demonstrate the System

These are the precise physical bench tests that must be executed to move requirements from **PARTIAL** or **NOT RUN** to **PASS**:

---

### Physical Test 1: Identify Active Serial COM Port
Connect the ESP32-S3 to your Windows PC via the USB-UART / COM port. Open PowerShell:

```powershell
pio device list
```

*Expected Result*: Confirm the active COM port assigned by Windows (e.g., `COM3`, `COM4`, or `COM6`).

---

### Physical Test 2: TMP117 / MAX30102 Electrical Coexistence Diagnosis
**Objective**: Empirically isolate whether the TMP117 I2C NACK is caused by bus presence, register setup, or optical LED pulse current.

#### Step 2A: Upload Stage 1 (Bus Presence Only)
```powershell
pio run -d diagnostics/tmp117_with_max -e tmp117-max-stage1 -t upload
pio device monitor --baud 115200
```
- **Observe for 15 seconds**: Does TMP117 stay at `0x49` and report steady temperature?
- *Exit with `Ctrl+]`*.

#### Step 2B: Upload Stage 2 (Optical Setup with LEDs OFF, 0 mA)
```powershell
pio run -d diagnostics/tmp117_with_max -e tmp117-max-stage2 -t upload
pio device monitor --baud 115200
```
- **Observe for 15 seconds**: Does TMP117 stay online when the MAX30102 FIFO and registers are configured without LED load?
- *Exit with `Ctrl+]`*.

#### Step 2C: Upload Stage 3 (Operational LED Pulse Current, ~7.2 mA)
```powershell
pio run -d diagnostics/tmp117_with_max -e tmp117-max-stage3 -t upload
pio device monitor --baud 115200
```
- **Observe**: If TMP117 returns `i2c_address_nack` ONLY in Stage 3, the power droop hypothesis is supported. 
  - *Remedy*: Connect a 10µF to 100µF capacitor across MAX30102 VCC and GND on the breadboard.
- If TMP117 fails in Stage 1 or 2 as well: Check I2C bus pull-up resistors and breadboard jumper wire continuity.
- *Exit with `Ctrl+]`*.

---

### Physical Test 3: Integrated Firmware Boot & Physical Detection
**Objective**: Flash the complete production firmware and verify boot detection of all 4 installed components.

```powershell
pio run -e esp32-s3-devkitc-1 -t upload
pio device monitor --baud 115200
```

- **Observe Serial Output**:
  - Boot I2C scan: Are `0x3C` (OLED), `0x49` (TMP117), `0x57` (MAX30102), and `0x68` (MPU6050) detected?
  - Does TMP117 report `valid` temperature at `uptime_s >= 5` without dropping out?
- *Exit monitor with `Ctrl+]` before starting Python bridge*.

---

### Physical Test 4: Visual OLED Screen Inspection
**Objective**: Verify physical display output on the SSD1306 glass module.
- Look directly at the physical 0.96" OLED screen on the breadboard:
  - Is the screen lit and readable?
  - Does it alternate pages every 4 seconds between:
    - Page 1: Vitals (HR, SpO2, Status)
    - Page 2: Environmental & Motion (TMP117 Temperature, Motion G, Fall Status)?

---

### Physical Test 5: Physical Sensor Interaction & Measurements
**Objective**: Generate genuine physiological and motion measurements on the bench.

1. **TMP117 Thermal Response**:
   - Firmly touch the black TMP117 sensor package with your finger for 10 seconds.
   - Verify temperature rises from ambient room temperature (~25–26°C) toward skin surface temperature (~31–33°C).
   - Release: verify temperature cools back toward room temperature.

2. **MAX30102 Optical Fingertip Measurement**:
   - Place your index fingertip gently over the optical window of the MAX30102.
   - Hold completely still for 8 to 10 seconds.
   - Verify status transitions from `"warming_up"` to `"valid"` and produces genuine Heart Rate (e.g., 65–85 BPM) and SpO2 (e.g., 96–99%).
   - Remove finger: verify status transitions to `"warming_up"` / `"low_quality"` with values reverting to `null` (zero fabrication).

3. **MPU-6050 Dynamic Motion & Fall Test**:
   - Stationary: verify magnitude reads $\approx 1.00\text{g} \pm 0.08\text{g}$.
   - Tilt and shake breadboard: verify magnitude responds dynamically.
   - Simulated Fall: Lift breadboard 5–10 cm and drop it onto a soft surface (e.g., mousepad).
   - Verify `fall_detected: true` latches for 6 seconds.

4. **SOS Button Press Test**:
   - Press the push button connected to GPIO 5 for 200ms.
   - Verify `sos_active: true` is emitted in telemetry.

---

### Physical Test 6: End-to-End Live Dashboard Verification
**Objective**: Verify complete telemetry pipeline to browser UI.

In PowerShell:
```powershell
python telemetry_bridge.py
```
Open browser to: `http://localhost:8000`

- Verify live SSE updates for active sensors.
- Verify charts plot real-time curves without fabricated zero lines.
- Verify emergency banner triggers when SOS button is pressed or fall occurs.
