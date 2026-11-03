# Video Reference Analysis & Benchmarking

- Document ID: MGT-VRA-001
- Version: 1.0.0
- Date: 2026-11-01
- Project: Remote Patient Vital Signs Monitoring System (RPMIOMTproject)
- Author: Chief Engineering Manager & Verification Specialist Agent

---

## 1. Executive Summary & Methodology

Four practical engineering videos were analyzed as behavioural and physical references.
The objective is **not** to blindly copy tutorial code, wiring, or thresholds, but to understand real-world sensor physics, finger placement dynamics, optical PPG noise characteristics, and I2C bus coexistence.

### Evidence Classification Standards
To maintain rigorous documentation integrity, every finding is explicitly classified:
- **[VISUAL]**: Directly verified from storyboard frames and demonstration video footage.
- **[TRANSCRIPT]**: Verified from spoken captions or official video transcript.
- **[DOCUMENTED]**: Verified from manufacturer datasheet or published companion article.
- **[INFERRED]**: Engineering deduction based on standard electrical/embedded principles.
- **[NON-TRANSFERABLE]**: Tutorial design choice that MUST NOT be used in this project due to electrical or architectural incompatibilities.

---

## 2. Reference 1: DroneBot Workshop — TMP117 Precision Thermometer

- **URL**: `https://www.youtube.com/watch?v=XHfyc8TiGmM`
- **Companion Article**: `https://dronebotworkshop.com/tmp117/`
- **Channel**: DroneBot Workshop | **Duration**: 27:05
- **Hardware Demonstrated**: Seeed Studio XIAO ESP32-S3, SparkFun/Adafruit TMP117 breakout, SSD1306 0.96" OLED display.

### Key Observations & Evidence
1. **Electrical Supply [TRANSCRIPT/VISUAL 5:20–5:58]**: TMP117 breakout powered strictly from 3.3V rail and common GND.
2. **Thermal Mass & Isolation [DOCUMENTED/VISUAL]**: Breakout PCB features isolation milling cutouts around the sensor IC to minimize thermal conduction from copper planes and microcontroller heat.
3. **I2C Bus Configuration [TRANSCRIPT 6:00–7:44]**: Uses I2C with standard pull-ups; periodic polling at 1 Hz intervals.
4. **Demonstration Values [VISUAL 23:50–24:30]**: OLED displays ambient temperature reading of ~25.02°C.
5. **Metrology Reality [DOCUMENTED]**: The video notes that while the sensor is factory-calibrated to ±0.1°C NIST-traceable precision, ambient air vs body surface thermal transfer requires significant stabilization time and mechanical coupling.

### Transferable Engineering Lessons
- **Keep 3.3V power rail clean**: ESP32-S3 I/O is 3.3V only. Never power TMP117 or pull-ups to 5V.
- **Thermal isolation on breadboard**: Position TMP117 far from the ESP32-S3 onboard regulator and the MAX30102 LEDs to prevent thermal pollution.
- **Polling interval**: The current firmware polls TMP117 every 2 seconds with 8-sample hardware averaging (0x01A0 configuration), which prevents self-heating and provides smooth readings.

### Non-Transferable Elements
- **GPIO Pinout**: The tutorial uses XIAO D4/D5; our ESP32-S3 DevKitC-1 uses GPIO 8 (SDA) and GPIO 9 (SCL).
- **Adafruit Driver Abstraction**: The project avoids heavy third-party driver bloat, maintaining a direct, static-assert-verified register implementation (`src/tmp117_protocol.h`) with strict `WHO_AM_I == 0x0117` validation.

---

## 3. Reference 2: Adafruit — TMP117 Product Showcase & Response Test

- **URL**: `https://www.youtube.com/watch?v=kZ7-vQgognc`
- **Channel**: Adafruit Industries | **Duration**: 1:00
- **Hardware Demonstrated**: Adafruit TMP117 breakout with STEMMA QT.

### Key Observations & Evidence
1. **PCB Thermal Cutout [TRANSCRIPT 0:08–0:26]**: The physical PCB slot cuts thermal conduction pathways from the rest of the board.
2. **Thermal Step Response [TRANSCRIPT/VISUAL 0:26–0:52]**: Demonstrates rapid thermal slew when physically touched by a finger (jumping from cooled ~70°F to body heat in seconds).
3. **No Clinical Claims [TRANSCRIPT]**: The demonstration explicitly presents physical temperature responsiveness, not medical clinical core temperature.

### Transferable Engineering Lessons
- **Abrupt Change Filter**: Rapid temperature swings are physically possible on direct skin contact; the firmware's abrupt change check requires a confirmation sample before rejecting or accepting swings > 2.0°C.
- **Strict Separation of Diagnostic vs Clinical**: Direct touch measures surface boundary temperature, NOT core body temperature. Our architecture preserves the separation between `tmp117_sensor_temperature_c` (diagnostic) and `wrist_skin_temperature_c` (clinical).

---

## 4. Reference 3: UtGo Tech / ShillehTek — MAX30102 / MPU6050 ESP32 Setup

- **URL**: `https://www.youtube.com/watch?v=V5UvNVQsUsY`
- **Channel**: UtGo Tech / ShillehTek | **Duration**: 3:01
- **Hardware Demonstrated**: ESP32 dev board, MAX30102 PPG breakout (green PCB), MPU-6050 6-axis IMU, breadboard.

### Key Observations & Evidence
1. **Physical Finger Coupling [VISUAL 0:20–2:54]**: Fingertip must be placed gently across the optical aperture without excessive pressure. Pressing hard blanches capillaries and destroys the pulsatile AC signal.
2. **Motion Sensitivity [VISUAL/INFERRED]**: Motion artifacts immediately degrade the photoplethysmogram (PPG) waveforms. Motion detection from MPU-6050 is essential to gate optical validity.
3. **IMU Fusion [DOCUMENTED]**: MPU-6050 operates on separate I2C address (`0x68`) and can run at 400kHz Fast Mode for responsiveness.

### Transferable Engineering Lessons
- **Dual I2C Bus Architecture**: Placing MPU-6050 on Wire1 (GPIO 17/18 @ 400kHz) and optical/temp sensors on Wire (GPIO 8/9 @ 50kHz) prevents high-frequency IMU reads from starving optical FIFO reads.
- **Motion Gating**: Fall detection and vigorous motion status must alert the user that optical vitals are unmeasurable during movement.

---

## 5. Reference 4: MOUNT DYNAMICS — MAX30102 Pulse Oximeter & OLED Display

- **URL**: `https://www.youtube.com/watch?v=W_3ljVlt7Sk`
- **Channel**: MOUNT DYNAMICS | **Duration**: 5:11
- **Hardware Demonstrated**: Arduino Nano, MAX30102 breakout, SSD1306 128x64 I2C OLED display, push button.

### Key Observations & Evidence
1. **Settling Time [TRANSCRIPT 0:09–0:31]**: Highlights that valid HR and SpO2 readings require a stabilization window of 4–8 seconds after finger placement before stable values emerge.
2. **Buffer Processing [DOCUMENTED/TRANSCRIPT]**: Uses 100-sample raw buffer for Red and IR channels, evaluating AC/DC ratios for photoplethysmography.
3. **Display State Switching [VISUAL 4:05 onward]**: Push button toggles between display pages and power states.

### Transferable Engineering Lessons
- **Windowed Processing**: 100-sample buffer with 25-sample sliding updates ensures stable initial capture (4 seconds @ 25 sps) followed by 1 Hz refreshed updates.
- **Fixed State Machine Glitch**: The project fixed the bug where an in-progress window erroneously set state back to `warming_up` after an initial valid or low-quality window was calculated.
- **OLED Page Cycling**: Alternate between temperature/diagnostics and motion/vital pages to avoid display clutter.

### Non-Transferable Elements
- **5V Supply [NON-TRANSFERABLE]**: The Nano video wires OLED and sensor to 5V. On the ESP32-S3, all sensors and displays MUST be powered strictly from 3.3V.

---

## 6. Synthesis & System Application Matrix

| Parameter / Technique | Video Tutorial Finding | RPMIOMTproject Implementation | Rationale |
|---|---|---|---|
| **TMP117 Supply** | 3.3V rail (DroneBot) | 3.3V rail from ESP32-S3 | Protects ESP32-S3 3.3V GPIO inputs |
| **TMP117 Polling** | 1 Hz timer | 0.5 Hz (every 2s) with 8x averaging | Zero self-heating, high stability |
| **TMP117 Address** | Hardcoded 0x48 | Dynamic scan 0x48–0x4B with WHO_AM_I check | Supports 7SEMI module (0x49) and hot-plug |
| **MAX30102 Finger Check** | Simple IR threshold (>50,000) | Triple-gate: DC range, AC peak, PI ≥ 0.10% | Prevents false HR calculation on ambient light |
| **MAX30102 Windowing** | 100 samples static | 100 samples initial + 25-sample sliding window | Low latency (1s updates) with 4s stability |
| **I2C Architecture** | Single shared bus | Dual independent buses (Wire: 50kHz, Wire1: 400kHz) | Eliminates bus contention between IMU & optical |
| **Clinical Integrity** | Tutorials show crude numbers | Strict null handling; unverified contact flagged | Prevents medical misinformation |

