# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Doctors reviewing remotely collected patient readings in a university-project prototype. The patient wearing the device does not use this dashboard. Doctors use the data and changes from a patient baseline to decide whether review or a visit is needed; the software does not diagnose health automatically.

## Product Purpose

A local ESP32-S3 remote patient monitoring prototype showing actual optical pulse, estimated oxygen saturation, surface temperature when available, and movement. The next workflow establishes a seven-day personal reference and compares future measurements with it.

## Operating Context

The ESP32 streams serial JSON into a local Python bridge. The browser receives server-sent events. The bridge must run for recording to continue; a closed browser does not stop server recording. No cloud account is required.

## Capabilities and Constraints

- Arduino C++ firmware; Python bridge; browser interface.
- MAX30102 optical sensor, MPU-compatible motion sensor, MLX90614 temperature channel, SSD1306 device display. The temperature sensor is currently absent but must remain supported.
- Null values are missing observations. Optical values require a detected finger and valid algorithm output.
- No ECG measurement, core-temperature inference, invented patient data, or fabricated historical graphs.
- Requested seven-day baseline and anomaly comparison. Implementation scope continued by the user: local statistical reference with coverage requirements, clear collection states, and one patient per enrollment.
- The user mentioned a later “jev model”; its meaning and integration are open, and it is outside this implementation.
- Prototype measurements and statistical departures are not medical diagnoses.

## Brand Commitments

The user requests an entirely new professional, sleek, distinctive dashboard. Light mode is the default. The old dashboard was explicitly rejected. The user accepted the new light visual direction on 2026-10-11 and requested doctor-facing terminology and workflow.

## Evidence on Hand

Real ESP32 serial telemetry and working sensor status. No seven-day dataset exists. OLED, motion and optical devices were responsive during the prior check; temperature was unavailable. Previous screenshots are evidence of the rejected design only.

## Product Principles

- Show measured data and uncertainty together.
- Never confuse hardware connectivity with valid measurement availability.
- Compare a person with their own recorded reference only after adequate coverage.
- Keep recording state, missing sensors and disconnects visible.

## Clinical workflow

Patient identity is assigned explicitly. Observations and baseline departures support clinician review, not automatic healthy/unhealthy labels. A clinician can record the latest review and follow-up decision in this browser, scoped to the enrolled patient. The current task focuses on local UI/UX; remote data sharing is deferred. Remote transmission, authentication and clinician identity verification are not implemented in this local university prototype.
