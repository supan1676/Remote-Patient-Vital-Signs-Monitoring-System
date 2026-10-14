#!/usr/bin/env python3
"""
IoMT Patient Vitals Monitor & Threshold Alert Engine
Connects directly to the ESP32-S3 live serial stream,
parses JSON telemetry packets, and checks vitals against baseline thresholds
to alert caregivers of abnormal readings or emergency events.
"""

import sys
import json
import time
from datetime import datetime
from telemetry_bridge import serial, find_serial_port, parse_packet


def evaluate_clinical_status(packet):
    """Summarize measured fields without inventing missing readings or core temperature."""
    v = packet.get("vitals", {})
    sensors = packet.get("sensors", {})
    alerts = packet.get("alerts", {})
    finger = sensors.get("max") is True and v.get("finger_on") is True
    hr = v.get("heart_rate") if finger else None
    spo2 = v.get("spo2") if finger else None
    motion = v.get("motion_g") if sensors.get("mpu") is True else None
    surface = v.get("temp_object", v.get("temp_skin")) if sensors.get("mlx") is True else None
    findings, actions = [], []
    status = "UNKNOWN (MISSING DATA)"
    if alerts.get("sos") or alerts.get("fall"):
        status = "RED (EMERGENCY)"
        findings.append("SOS button active." if alerts.get("sos") else "Fall alert active.")
        actions.append("Check on the person immediately.")
    elif (hr is not None and hr > 0 and (hr < 50 or hr > 120)) or (spo2 is not None and 0 < spo2 < 90):
        status = "YELLOW (WARNING)"
        findings.append("A configured optical measurement threshold was crossed.")
        actions.append("Check sensor placement and notify a caregiver if the reading persists.")
    elif hr is not None and hr > 0 and spo2 is not None and spo2 > 0:
        status = "GREEN (NO OPTICAL ALERT)"
        findings.append("No configured optical alert threshold crossed.")
    if hr is None or hr <= 0 or spo2 is None or spo2 <= 0:
        findings.append("Optical readings unavailable; keep a finger steady on MAX30102.")
    findings.append("MLX90614 measures object/surface temperature; core temperature is unavailable.")
    return {
        "timestamp": datetime.now().isoformat(),
        "uptime_seconds": packet.get("uptime_s"),
        "overall_status": status,
        "patient_metrics": {
            "heart_rate_bpm": hr if hr is not None and hr > 0 else "UNAVAILABLE",
            "spo2_percent": spo2 if spo2 is not None and spo2 > 0 else "UNAVAILABLE",
            "raw_ir": v.get("raw_ir"),
            "core_temp_c": "NOT MEASURED",
            "surface_temp_c": surface if surface is not None else "UNAVAILABLE",
            "step_count": v.get("steps") if sensors.get("mpu") else "UNAVAILABLE",
            "motion_g": round(motion, 2) if motion is not None else "UNAVAILABLE",
            "hardware_health": f"{sum(sensors.get(k) is True for k in ('oled', 'max', 'mlx', 'mpu'))}/4 sensors online"
        },
        "status_summary": packet.get("status_summary", ""),
        "findings": findings, "recommended_actions": actions
    }


def print_alert_card(summary):
    """Prints a clean, honest Vital Signs & Alert Card in the terminal."""
    status = summary["overall_status"]
    metrics = summary["patient_metrics"]

    print("\n" + "=" * 65)
    print(f" 📊 PATIENT VITALS & ALERT CHECKER — [{summary['timestamp'][:19]}]")
    print("=" * 65)
    print(f"  PATIENT STATUS       : {status}")
    print(f"  Hardware Health      : {metrics['hardware_health']}")
    print("-" * 65)
    print(f"  Vitals Snapshot:")
    print(f"    • Heart Rate  : {metrics['heart_rate_bpm']} BPM")
    print(f"    • SpO2 (O2)   : {metrics['spo2_percent']} %")
    print(f"    • Surface Temp: {metrics['surface_temp_c']} °C")
    print(f"    • Step Count  : {metrics['step_count']} steps | Motion: {metrics['motion_g']} g")
    print("-" * 65)
    print("  📋 Threshold Observations:")
    for f in summary["findings"]:
        print(f"    - {f}")
    print("  💡 Caregiver Recommendations:")
    for a in summary["recommended_actions"]:
        print(f"    ▶ {a}")
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
    except Exception as e:
        print(f"[ERROR] Could not open {port}: {e}")
        print("Tip: Make sure pio device monitor is closed so the port is free.")
        return

    try:
        while True:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            # Look for structured JSON telemetry lines
            if line.startswith("[JSON]"):
                json_str = line[6:].strip()
                try:
                    packet = parse_packet(json_str)
                    if packet is None:
                        continue
                    summary = evaluate_clinical_status(packet)
                    print_alert_card(summary)
                except json.JSONDecodeError as err:
                    print(f"[WARN] Failed to parse JSON: {err}")
    except KeyboardInterrupt:
        print("\n[INFO] Stopped by user.")
    finally:
        ser.close()


if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else None
    listen_serial(port)

