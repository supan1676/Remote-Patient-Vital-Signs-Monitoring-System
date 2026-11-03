# Video Reference Analysis

- Analysis date: 2026-11-01
- Purpose: separate what the four reference videos directly show from what their
  captions, descriptions, linked material and inference support.
- Project constraint: these videos are behavioural references only. The project
  keeps its ESP32-S3 firmware, Python bridge, SQLite history, dashboard and
  temperature-safety rules. No tutorial code or wiring was copied blindly.

## 1. Method and evidence limits

I inspected the available YouTube metadata, descriptions, official transcripts
where present, the linked article for Video 1, and sampled storyboard frames.
The storyboard strips are low-resolution sample frames, not a full-motion review:

| Video | Sample interval | Samples inspected |
|:---|:---|:---|
| 1. DroneBot Workshop, TMP117 | 10 s | Wiring, code, comparison and final-project frames |
| 2. Adafruit, TMP117 product pick | 1 s | Full one-minute thermal demonstration |
| 3. UtGo Tech, MAX30102 | 2 s | Module, Arduino wiring, datasheet/PC and finger-demo frames |
| 4. MOUNT DYNAMICS, MAX30102 pulse oximeter | 5 s | Demo, wiring, code and finger-demo frames |

Direct visual observations are labelled **visual**. Spoken content is labelled
**transcript**. Article/description content is labelled **text**. Statements that
are plausible but not directly established are labelled **inference**. Nothing
in this document is a calibration or clinical validation.

Video 3 has captions disabled. No transcript was available, so no code, library,
pin mapping, output value or spoken claim is attributed to it. Its description
and sampled frames are the only evidence used.

## 2. Video 1 - DroneBot Workshop, TMP117 precision thermometer

- Title: "TMP117 Precision Temperature Sensor - Build a WiFi Thermometer"
- Channel: DroneBot Workshop
- Duration: 27:05
- URL: <https://www.youtube.com/watch?v=XHfyc8TiGmM>
- Linked article: <https://dronebotworkshop.com/tmp117/>

### Directly supported

- **Transcript, 5:20-5:58:** the experiment uses a TMP117 module and a Seeed
  Studio XIAO ESP32S3. The TMP117 VIN goes to the 3.3 V output, GND to GND, SCL
  to D5 and SDA to D4.
- **Visual, around 5:30-6:00:** a Qwiic TMP117 breakout and a Fritzing-style
  wiring diagram are shown. The diagram uses 3.3 V, ground and the two I2C
  lines.
- **Transcript, 6:00-7:44:** the segment uses the Adafruit TMP117 library and a
  simple read-and-print sketch.
- **Transcript, 7:47-7:51:** the serial monitor prints the temperature every
  second to two decimal places. The presenter compares it informally with a
  workshop thermometer, not a calibrated reference.
- **Transcript/article:** the sensor is described as a high-accuracy digital
  temperature sensor. Thermal isolation and avoiding self-heating are discussed
  in the article and project section.
- **Visual, around 23:50-24:30:** the final breadboard project is shown, and the
  OLED displays approximately `25.02 °C`. This is a demonstration value, not a
  reference measurement.
- **Article:** the project uses 3.3 V, a 1 s read interval and a display/network
  project. The article reinforces that the TMP117 is a sensor, not a clinical
  core-temperature device.

### Use in this project

- Keep the TMP117 on **3.3 V** with a common ground.
- Keep the primary I2C bus at a conservative speed. This project uses 50 kHz on
  GPIO 8/9 rather than the XIAO's D4/D5 pins.
- Read at a sensible interval. This firmware polls the TMP117 every 2 s and
  configures a 500 ms conversion cycle with eight-sample averaging.
- Keep the TMP117 physically away from the ESP32-S3 regulator, the OLED and the
  MAX30102 LEDs so board heat and optical heat do not dominate the sensor.
- Do **not** use the video's displayed `25.02 °C` as a calibration value.

### Not transferable

- The XIAO ESP32S3 pin names and wiring.
- The Adafruit TMP117 driver as a replacement for this project's checked raw
  register path. This firmware deliberately verifies `WHO_AM_I` and the
  configuration readback itself.
- The video's informal thermometer comparison is not a metrology study.

## 3. Video 2 - Adafruit TMP117 product pick

- Title: "JP's Product Pick of the Week Recap TMP117 Precision Temperature
  Sensor"
- Channel: Adafruit Industries
- Duration: 1:00
- URL: <https://www.youtube.com/watch?v=kZ7-vQgognc>

### Directly supported

- **Transcript, 0:08-0:26:** the TMP117 breakout is shown. The transcript calls
  attention to the cut-out in the breakout board that lowers thermal mass around
  the sensor.
- **Transcript, 0:26-0:42:** an ice pack has cooled the ambient reading to about
  70 °F. The presenter presses a finger against the sensor and says the reading
  climbs rapidly, to roughly "70 72" in the automatic transcript. The exact
  displayed value is not legible in the sampled frames.
- **Transcript, 0:42-0:52:** the presenter also places the sensor in his mouth;
  he calls the action ill-advised but uses it to show a rapid thermal response.
- **Visual:** the breakout and finger contact are visible. The demonstration is
  a product teaser, not a controlled test.

### Use in this project

- The breakout's thermal cut-out supports the decision to treat the TMP117 as a
  sensor with its own thermal mass, not as an instant clinical thermometer.
- Finger contact can change the reading quickly, so the implementation retains
  an abrupt-change confirmation rule and keeps the actual sensor value separate
  from any future wrist-skin clinical value.
- The video provides **no code**, no address discovery, no configuration
  readback and no accuracy data.

### Not transferable

- The approximate Fahrenheit values are not a calibration source.
- Mouth contact is not a validated body-temperature method.
- The video does not justify exposing a wrist or core temperature.

## 4. Video 3 - UtGo Tech, MAX30102 heart-beat sensor

- Title: "What is MAX30102 and how to use it | Heart Beat Sensor | UtGo"
- Channel: UtGo Tech
- Duration: 3:01
- URL: <https://www.youtube.com/watch?v=V5UvNVQsUsY>
- Captions: **disabled** (no transcript available)

### Directly supported

- **Description:** the video is about the MAX30102. The listed components are a
  MAX30102 module, an Arduino Uno, a small breadboard and jumper wires. The
  description also links a MAX30102 datasheet.
- **Visual, 0:00-0:28:** the green MAX30102 breakout and an animated heart-beat /
  oxygen-level graphic are shown. A finger is placed over the module in the
  opening demonstration.
- **Visual, 0:30-1:20:** an Arduino Uno, small breadboard and jumper wires are
  visible. The exact header-to-pin mapping is not legible at storyboard
  resolution.
- **Visual, 1:22-2:18:** a datasheet or web page and a computer screen are shown.
  The exact code, library and serial output are not readable.
- **Visual, 2:20-2:54:** a finger is held over the green module during the
  demonstration. The display or serial values are not legible.
- **No code or library is verified from this video.**

### Use in this project

- The visual demonstration supports the basic physical technique: place a
  fingertip over the optical window and keep it still while the signal settles.
- It does not establish a pin mapping, LED current, sample rate, algorithm,
  threshold, or accuracy claim.
- This project uses the SparkFun MAX3010x library at 3.3 V on the ESP32-S3,
  with its own signal-quality gate and its own 100-sample window.

### Not transferable

- The Arduino Uno wiring and any assumed 5 V supply.
- Any unreadable code or displayed value.
- Any claim that the video's MAX30102 output is clinically accurate.

## 5. Video 4 - MOUNT DYNAMICS, MAX30102 pulse oximeter

- Title: "Pulse Oximeter! Measure Heart Rate and Oxygen Saturation using
  Max30102, Arduino and Oled Display"
- Channel: MOUNT DYNAMICS
- Duration: 5:11
- URL: <https://www.youtube.com/watch?v=W_3ljVlt7Sk>

### Directly supported

- **Transcript, 0:09-0:31:** the presenter places a finger on the heart-rate
  sensor and says the OLED readings take a few seconds to become stable. A push
  button switches the meter on and checks the average pulse and oxygen reading.
- **Transcript, 0:38-1:04:** components are a MAX30102 module, a 0.96-inch OLED,
  an Arduino Nano, a half breadboard, one push button and breadboard wires.
- **Transcript, 1:15-2:00:** the OLED VCC is connected to 5 V; the transcript
  gives the Arduino Nano's 5 V, ground, SDA A4 and SCL A5 wiring.
- **Visual, 1:15-2:00:** the Nano, OLED, MAX30102 and button are shown on a
  breadboard. The MAX30102 is the red/green optical module.
- **Visual, 2:30-2:50 and 4:05 onward:** a finger is placed over the optical
  module while the OLED display is active.
- **Transcript, around 2:20-3:30:** the code/display section describes a pulse
  oximeter sketch. The exact values are not legible in the sampled frames.
- **Transcript, 4:00 onward:** the button is used for an average reading and the
  display turns off after about five seconds.

### Use in this project

- The useful behavioural lesson is placement and settling: a steady finger over
  the optical window, several seconds of stable samples, and a quality check
  before publishing a pulse or SpO2 estimate.
- This project keeps the MAX30102 on **3.3 V**, checks `PART_ID = 0x15`, uses a
  25 Hz effective sample rate, collects 100 samples (about 4 s), and requires
  the IR/red DC, AC and perfusion-index guards before accepting output.

### Not transferable

- **Do not copy the 5 V VIN wiring to the ESP32-S3.** The ESP32-S3 is a 3.3 V
  device and its I/O is not 5 V tolerant. The Arduino Nano setup is not the same
  electrical design.
- Do not copy the OLED or button wiring or assume the video's displayed values
  are correct.
- Do not lower this project's MAX thresholds merely to make a value appear.

## 6. Cross-video conclusions used in the implementation

| Topic | Supported conclusion | Not supported / not used |
|:---|:---|:---|
| TMP117 supply | Use 3.3 V and a common ground; keep the sensor thermally isolated | Using the video's display value as calibration |
| TMP117 bus | I2C SDA/SCL, conservative clock, periodic reads | A specific address; this project discovers `0x48`-`0x4B` and checks identity |
| TMP117 contact | Finger contact can change the reading quickly | Calling the sensor value wrist-skin or core temperature |
| MAX30102 placement | Finger over the optical window, still, several seconds | A guarantee that any finger placement produces a valid reading |
| MAX30102 wiring | Modules can be demonstrated on 5 V Arduino boards | Powering the ESP32-S3 or its I/O at 5 V |
| MAX30102 output | A demo can show pulse/SpO2 after settling | Clinical accuracy or permission to weaken quality checks |
| Code | Tutorials show library-based examples | Copying tutorial code or pin mappings into this project |

## 7. Evidence that remains unavailable

- Full-motion review of all four videos. Only sampled storyboard frames were
  inspected.
- Captions/transcript for Video 3. Captions are disabled.
- Legible code, library names, pin labels and output values from Videos 3 and 4
  at the available frame resolution.
- A calibrated reference thermometer or pulse oximeter in any video.
- Any clinical validation, patient study or regulatory approval.

These limitations are intentional in this report. No unreadable frame or
automatic-transcript phrase is presented as a verified measurement.
