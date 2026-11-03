#!/usr/bin/env python3
"""
IoMT Patient Vitals Monitor & Threshold Alert Engine
Connects directly to the ESP32-S3 live serial stream,
parses JSON telemetry packets, and checks vitals against baseline thresholds
to alert caregivers of abnormal readings or emergency events.
"""

import math
import sys
import time
from datetime import datetime

# Windows console encoding guard
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from telemetry_bridge import find_serial_port, parse_packet, serial
from temperature_safety import (
    FEVER_MESSAGE,
    evaluate_temperature_safety,
)

VITAL_SENSOR_MAX = 3
INSTALLED_SENSORS = ('max', 'mpu', 'tmp117')


def _measurement(value):
    """Return a finite numeric measurement, or None for null/missing/invalid data."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) else None


def _validated(vitals, key, status_key, sensor, sensors):
    if sensors.get(sensor) is not True:
        return None
    if vitals.get(status_key) != 'valid':
        return None
    return _measurement(vitals.get(key))


def evaluate_clinical_status(packet):
    """Summarize measured fields without inventing missing readings or core temperature."""
    vitals = packet.get("vitals", {})
    sensors = packet.get("sensors", {})
    alerts = packet.get("alerts", {})
    finger = sensors.get("max") is True and vitals.get("finger_on") is True
    hr = _validated(vitals, "heart_rate", "heart_rate_status", "max", sensors)
    spo2 = _validated(vitals, "spo2", "spo2_status", "max", sensors)
    if not finger:
        hr = spo2 = None
    motion = _validated(vitals, "motion_g", "motion_status", "mpu", sensors)
    temperature = evaluate_temperature_safety(packet)
    wrist = temperature["wrist_skin_temperature_c"]
    wrist_status = temperature["wrist_skin_temperature_status"]
    # Optional legacy modules are never part of the current inventory.
    legacy_surface = (_measurement(vitals.get("temp_object", vitals.get("temp_skin")))
                      if sensors.get("mlx") is True else None)
    sht40_temp = (_measurement(vitals.get("sht40_temp_c"))
                  if sensors.get("sht40") is True else None)
    sht40_humidity = (_measurement(vitals.get("sht40_humidity_pct"))
                      if sensors.get("sht40") is True else None)
    findings, actions = [], []
    status = "UNKNOWN (MISSING DATA)"
    if alerts.get("sos") or alerts.get("fall"):
        status = "RED (EMERGENCY)"
        findings.append("SOS button active." if alerts.get("sos")
                        else "Fall alert active.")
        actions.append("Check on the person immediately.")
    elif ((hr is not None and (hr < 50 or hr > 120)) or
          (spo2 is not None and spo2 < 90)):
        status = "YELLOW (WARNING)"
        findings.append("A configured optical measurement threshold was crossed.")
        actions.append("Check sensor placement and notify a caregiver if the reading persists.")
    elif hr is not None and spo2 is not None:
        status = "GREEN (NO OPTICAL ALERT)"
        findings.append("No configured optical alert threshold crossed.")
    if hr is None or spo2 is None:
        findings.append(
            "Optical readings are unavailable or not valid "
            f"(heart rate: {vitals.get('heart_rate_status', 'missing')}, "
            f"SpO2: {vitals.get('spo2_status', 'missing')}); no value was substituted.")
    sensor_temp = temperature["tmp117_sensor_temperature_c"]
    sensor_status = temperature["tmp117_sensor_temperature_status"]
    if sensor_temp is not None:
        findings.append(
            f"TMP117 sensor temperature is {sensor_temp:.2f} °C with quality "
            f"'{sensor_status}'. This is the actual sensor reading, not a "
            "clinical wrist-skin or core-body temperature.")
    else:
        findings.append(
            "TMP117 sensor temperature is unavailable "
            f"(status: {sensor_status}); no value was substituted.")
    if wrist is not None:
        findings.append(
            f"Wrist skin temperature is {wrist:.2f} °C with quality "
            f"'{wrist_status}'. This is not a core-body temperature.")
    else:
        findings.append(
            "Wrist skin temperature is unavailable "
            f"(status: {wrist_status}); no value was substituted.")
    findings.append(FEVER_MESSAGE)
    findings.append(
        "Fever screening is not available because no core-temperature method "
        "has been validated; wrist skin temperature is context only.")
    if legacy_surface is not None:
        findings.append(
            "Optional legacy MLX90614 surface temperature is available; "
            "it is not a core-body measurement and is not counted.")
    if sht40_temp is not None or sht40_humidity is not None:
        findings.append(
            "Optional SHT40 environmental readings are context only; "
            "they do not trigger a medical alert.")
    actions.append(
        "If fever is suspected, confirm with a validated clinical thermometer "
        "and clinician assessment; do not diagnose fever from wrist skin.")
    # The installed inventory is fixed: optional legacy modules do not count.
    online = sum(sensors.get(key) is True for key in INSTALLED_SENSORS)
    display = "display online" if sensors.get("oled") is True else "display offline"
    health = f"{online}/{VITAL_SENSOR_MAX} measurement sensors online; {display}"
    return {
        "timestamp": datetime.now().isoformat(),
        "uptime_seconds": packet.get("uptime_s"),
        "overall_status": status,
        "patient_metrics": {
            "heart_rate_bpm": hr if hr is not None else "UNAVAILABLE",
            "heart_rate_status": vitals.get("heart_rate_status"),
            "spo2_percent": spo2 if spo2 is not None else "UNAVAILABLE",
            "spo2_status": vitals.get("spo2_status"),
            "raw_ir": vitals.get("raw_ir"),
            "wrist_skin_temperature_c": (wrist if wrist is not None
                                          else "UNAVAILABLE"),
            "wrist_skin_temperature_status": wrist_status,
            "wrist_contact_status": temperature["wrist_contact_status"],
            "tmp117_sensor_temperature_c": (temperature["tmp117_sensor_temperature_c"]
                                           if temperature["tmp117_sensor_temperature_c"] is not None
                                           else "UNAVAILABLE"),
            "tmp117_sensor_temperature_status": temperature["tmp117_sensor_temperature_status"],
            "estimated_core_temperature_c": None,
            "estimated_core_temperature_status": "not_available",
            "fever_screening_status": temperature["fever_screening"]["status"],
            "fever_screening_message": FEVER_MESSAGE,
            "surface_temp_c": (legacy_surface if legacy_surface is not None
                               else "UNAVAILABLE"),
            "sht40_temp_c": (sht40_temp if sht40_temp is not None
                             else "UNAVAILABLE"),
            "sht40_humidity_pct": (sht40_humidity if sht40_humidity is not None
                                   else "UNAVAILABLE"),
            "step_count": (vitals.get("steps") if sensors.get("mpu") is True
                           else "UNAVAILABLE"),
            "motion_g": round(motion, 2) if motion is not None else "UNAVAILABLE",
            "motion_status": vitals.get("motion_status"),
            "hardware_health": health,
        },
        "temperature": temperature,
        "status_summary": packet.get("status_summary", ""),
        "findings": findings,
        "recommended_actions": actions,
    }


def print_alert_card(summary):
    """Prints a clean, honest Vital Signs & Alert Card in the terminal."""
    status = summary["overall_status"]
    metrics = summary["patient_metrics"]

    print("\n" + "=" * 65)
    print(f" PATIENT VITALS & ALERT CHECKER — [{summary['timestamp'][:19]}]")
    print("=" * 65)
    print(f"  PATIENT STATUS       : {status}")
    print(f"  Hardware Health      : {metrics['hardware_health']}")
    print("-" * 65)
    print("  Vitals Snapshot:")
    print(f"    * Heart Rate       : {metrics['heart_rate_bpm']} BPM")
    print(f"    * SpO2             : {metrics['spo2_percent']} %")
    print(f"    * TMP117 Sensor    : {metrics['tmp117_sensor_temperature_c']} °C"
          f" ({metrics['tmp117_sensor_temperature_status']}; actual sensor, not core)")
    print(f"    * Wrist Skin Temp. : {metrics['wrist_skin_temperature_c']} °C"
          f" ({metrics['wrist_skin_temperature_status']}; not core)")
    print(f"    * Estimated Core   : {metrics['estimated_core_temperature_c']}"
          " (not available)")
    print(f"    * Fever Screening  : {metrics['fever_screening_message']}")
    if metrics["surface_temp_c"] != "UNAVAILABLE":
        print(f"    * Legacy MLX       : {metrics['surface_temp_c']} °C"
              " (optional, not core)")
    if metrics["sht40_temp_c"] != "UNAVAILABLE":
        print(f"    * SHT40 Env.       : {metrics['sht40_temp_c']} °C | "
              f"{metrics['sht40_humidity_pct']} %RH (context only)")
    print(f"    * Step Count       : {metrics['step_count']} steps | "
          f"Motion: {metrics['motion_g']} g")
    print("-" * 65)
    print("  Threshold Observations:")
    for finding in summary["findings"]:
        print(f"    - {finding}")
    print("  Caregiver Recommendations:")
    for action in summary["recommended_actions"]:
        print(f"    > {action}")
    print("=" * 65 + "\n")


def listen_serial(port=None, baud=115200):
    """Listens to the ESP32 serial stream and checks every JSON telemetry packet."""
    if port is None:
        port = find_serial_port()
    if port is None:
        print("[ERROR] No unique USB serial device found. Pass its port explicitly.")
        return
    if serial is None:
        print("[ERROR] pyserial is not installed. Install via: pip install pyserial")
        return

    print(f"[INFO] Connecting to ESP32-S3 on {port} at {baud} baud...")
    try:
        ser = serial.Serial(port=None, baudrate=baud, timeout=1.0)
        ser.dtr = ser.rts = False
        ser.port = port
        ser.open()
        time.sleep(1.0)
        print("[SUCCESS] Connected! Listening for real-time telemetry stream...\n")
    except Exception as exc:
        print(f"[ERROR] Could not open {port}: {exc}")
        print("Tip: Make sure pio device monitor is closed so the port is free.")
        return

    try:
        while True:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            if line.startswith("[JSON]"):
                packet = parse_packet(line)
                if packet is None:
                    continue
                summary = evaluate_clinical_status(packet)
                print_alert_card(summary)
    except KeyboardInterrupt:
        print("\n[INFO] Stopped by user.")
    finally:
        ser.close()


if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else None
    listen_serial(port)
