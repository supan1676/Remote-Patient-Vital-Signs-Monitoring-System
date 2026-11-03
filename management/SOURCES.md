# Technical Sources, Datasheets, and Engineering References

- Document ID: MGT-SRC-001
- Version: 1.0.0
- Date: 2026-11-01
- Project: Remote Patient Vital Signs Monitoring System (RPMIOMTproject)
- Author: Chief Engineering Manager

---

## 1. Hardware Datasheets & Application Notes

1. **Texas Instruments TMP117**
   - Title: *TMP117 High-Accuracy, Low-Power, Digital Temperature Sensor With SMBus- and I2C-Compatible Interface*
   - Document: SBOS933C – March 2018 – Revised September 2020
   - Key specifications: ±0.1°C accuracy (-20°C to +50°C), 16-bit resolution (0.0078125°C / LSB), I2C addresses 0x48 to 0x4B, Device ID 0x0117.
   - Application Note: *Design Considerations for Surface Temperature Sensing* (SNOA986).

2. **Analog Devices / Maxim Integrated MAX30102**
   - Title: *High-Sensitivity Pulse Oximeter and Heart-Rate Sensor for Wearable Health*
   - Document: 19-7529; Rev 0; 11/15
   - Key specifications: Dual LED (Red 660nm, IR 880nm), 18-bit ADC, 32-sample FIFO, fixed 7-bit I2C address 0x57, Part ID 0x15.
   - Application Note: *Application Note 6845: Guidelines for MAX30101/MAX30102 Component Placement*.

3. **InvenSense / TDK MPU-6050**
   - Title: *MPU-6000 and MPU-6050 Product Specification Revision 3.4*
   - Document: PS-MPU-6000A-00, Rev 3.4
   - Key specifications: 3-axis accelerometer, 3-axis gyroscope, Digital Motion Processor (DMP), I2C address 0x68 (AD0=0) or 0x69 (AD0=1), WHO_AM_I register 0x75 (returns 0x68 or 0x70 for MPU-6500).

4. **Solomon Systech SSD1306**
   - Title: *128 x 64 Dot Matrix OLED/PLED Segment/Common Driver with Controller*
   - Document: Rev 1.1, Apr 2008
   - Key specifications: 128x64 monochrome graphic OLED, I2C address 0x3C (or 0x3D), charge pump regulator.

5. **Espressif Systems ESP32-S3**
   - Title: *ESP32-S3 Series Datasheet v1.8*
   - Document: Espressif Systems 2024
   - Key specifications: Dual-core Xtensa LX7 @ 240MHz, 512KB SRAM, 16MB Flash / 8MB PSRAM (N16R8), dual hardware I2C peripheral controllers, flexible GPIO matrix.
   - Technical Reference Manual: *ESP32-S3 Technical Reference Manual v1.5 - Chapter 12: I2C Controller*.

---

## 2. Reference Video Demonstrations

1. **DroneBot Workshop**: *TMP117 Precision Temperature Sensor - Build a WiFi Thermometer*
   - URL: `https://www.youtube.com/watch?v=XHfyc8TiGmM`
   - Publication: August 2023
   - Code & Article: `https://dronebotworkshop.com/tmp117/`

2. **Adafruit Industries**: *JP's Product Pick of the Week Recap TMP117 Precision Temperature Sensor*
   - URL: `https://www.youtube.com/watch?v=kZ7-vQgognc`
   - Publication: Adafruit Learning System

3. **UtGo Tech / ShillehTek**: *What is MAX30102 and how to use it | Heart Beat Sensor / MPU6050 Setup*
   - URL: `https://www.youtube.com/watch?v=V5UvNVQsUsY`
   - Publication: ShillehTek Tutorials

4. **MOUNT DYNAMICS**: *Measure Heart Rate and Oxygen Saturation using Max30102, Arduino and Oled Display*
   - URL: `https://www.youtube.com/watch?v=W_3ljVlt7Sk`
   - Publication: MOUNT DYNAMICS

---

## 3. Standards, Metrology, and Clinical References

1. **ASTM E1112 - 00(2018)**
   - Title: *Standard Specification for Electronic Thermometer for Intermittent Determination of Patient Temperature*
   - Requirement: Clinical thermometer maximum allowable laboratory error is ±0.1°C (±0.2°F) in the range of 37.0°C to 39.0°C. TMP117 meets this raw silicon accuracy requirement, but clinical surface-to-core translation requires validated physiological calibration.

2. **ISO 80601-2-61:2019**
   - Title: *Medical electrical equipment — Part 2-61: Particular requirements for basic safety and essential performance of pulse oximeter equipment*
   - Principle: PPG measurement validity depends heavily on perfusion index, motion artifact absence, and finger boundary conditions.

3. **FDA Guidance for Pulse Oximeters (February 2021 Safety Communication)**
   - Requirement: Non-clinical pulse oximeter devices must clearly state accuracy limitations, especially in low perfusion, motion, and ambient light interference.

---

## 4. Software Libraries & Open Source Repositories

1. **SparkFun MAX3010x Pulse and Proximity Sensor Library**
   - Author: SparkFun Electronics (Nathan Seidle / Peter Jansen)
   - Repository: `https://github.com/sparkfun/SparkFun_MAX3010x_Sensor_Library`
   - Version: 1.1.2 (PlatformIO registered)

2. **Adafruit SSD1306 & GFX Library**
   - Author: Adafruit Industries
   - Repository: `https://github.com/adafruit/Adafruit_SSD1306`
   - Versions: Adafruit SSD1306 @ 2.5.17, Adafruit GFX @ 1.13.0

3. **Jeff Rowberg i2cdevlib**
   - Author: Jeff Rowberg
   - Repository: `https://github.com/jrowberg/i2cdevlib`
   - Components: Reference MPU-6050 register maps and scale factors.

