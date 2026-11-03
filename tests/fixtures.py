"""Shared synthetic protocol fixtures for host-side tests.

These are protocol-shape fixtures only. They are not clinical data, are never
served by the dashboard, and are not written to the application database.
"""
import copy

FEVER_MESSAGE = "Core temperature unavailable — confirmation required"


def packet(device_id="RPM-NODE-01", **vitals_overrides):
    vitals = {
        "heart_rate": 72,
        "heart_rate_status": "valid",
        "heart_rate_timestamp_ms": 5000,
        "spo2": 98,
        "spo2_status": "valid",
        "spo2_timestamp_ms": 5000,
        "finger_on": True,
        "raw_ir": 70000,
        "raw_red": 68000,
        "optical_signal_quality": "good",
        "optical_perfusion_index": 1.2,
        "tmp117_sensor_temperature_c": 29.6484375,
        "tmp117_sensor_temperature_status": "valid",
        "tmp117_sensor_temperature_raw": 3795,
        "tmp117_sensor_temperature_timestamp_ms": 5000,
        "wrist_contact_status": "unverified",
        "wrist_skin_temperature_c": None,
        "wrist_skin_temperature_status": "unverified",
        "wrist_skin_temperature_raw": None,
        "wrist_skin_temperature_timestamp_ms": None,
        "estimated_core_temperature_c": None,
        "estimated_core_temperature_status": "not_available",
        "temp_core": None,
        "temp_skin": None,
        "temp_object": None,
        "temp_amb": None,
        "sht40_temp_c": None,
        "sht40_humidity_pct": None,
        "acceleration": {
            "x_g": 0.0, "y_g": 0.0, "z_g": 1.0, "magnitude_g": 1.0,
        },
        "gyroscope": {
            "x_dps": 0.0, "y_dps": 0.0, "z_dps": 0.0, "magnitude_dps": 0.0,
        },
        "imu_raw": {
            "accel_counts": [0, 0, 4096],
            "gyro_counts": [0, 0, 0],
            "accel_lsb_per_g": 4096,
            "gyro_lsb_per_dps": 131,
        },
        "motion_g": 1.0,
        "motion_status": "valid",
        "motion_timestamp_ms": 5000,
        "activity_state": "stationary",
        "orientation": "z_up",
        "steps": 0,
        "fever_screening": {
            "status": "not_available",
            "message": FEVER_MESSAGE,
            "rule": None,
            "input": {
                "measurement": "wrist_skin_temperature",
                "value_c": None,
                "unit": "C",
                "quality": "unverified",
                "measured": False,
                "timestamp_ms": None,
                "raw_register": None,
            },
            "uncertainty": "No validated core-temperature estimate or core reference is available.",
            "limitations": (
                "Wrist skin temperature is affected by ambient conditions, blood flow, "
                "contact pressure and activity. A wrist reading alone cannot confirm or "
                "rule out fever."
            ),
        },
    }
    vitals.update(vitals_overrides)
    return {
        "uptime_s": 10,
        "device_id": device_id,
        "firmware_version": "rpm-2.1.0",
        "schema_version": 2,
        "board": {"flash_bytes": 16_777_216, "psram_bytes": 8_388_608},
        "risk": "GREEN",
        "urgent": False,
        "sensors": {
            "oled": True,
            "max": True,
            "mpu": True,
            "tmp117": True,
            "sht40": False,
            "mlx": False,
            "active": 3,
            "active_max": 3,
        },
        "sensor_health": {
            "max": {"present": True, "status": "valid", "error": "none"},
            "mpu": {
                "present": True, "status": "valid", "error": "none",
                "calibration_status": "basic_complete",
                "calibration": {
                    "status": "basic_complete", "samples": 80, "attempts": 1,
                    "stationary": True, "orientation": "z_up",
                    "gyro_bias_valid": True, "accel_bias_valid": True,
                    "gyro_bias_dps": [0.0, 0.0, 0.0],
                    "accel_bias_g": [0.0, 0.0, 0.0],
                    "accel_bias_status": "estimated_single_orientation",
                    "method": "80 samples at 50 Hz",
                    "timestamp_ms": 4000,
                },
            },
            "tmp117": {
                "present": True, "status": "valid", "error": "none",
                "address": "0x48", "who_am_i": 279,
                "configuration": 416, "offset_raw": 0, "error_count": 0,
            },
        },
        "vitals": vitals,
        "alerts": {"sos": False, "fall": False},
        "status_summary": (
            "No configured optical alert threshold crossed. Wrist skin temperature "
            "is not core temperature; core temperature unavailable — confirmation required."
        ),
    }


def verified_packet(device_id="RPM-NODE-01", value=29.6484375, raw=3795,
                    timestamp_ms=5000):
    """Protocol fixture for a future, separately validated contact check."""
    result = copy.deepcopy(packet(device_id))
    result["vitals"].update({
        "tmp117_sensor_temperature_c": value,
        "tmp117_sensor_temperature_status": "valid",
        "tmp117_sensor_temperature_raw": raw,
        "tmp117_sensor_temperature_timestamp_ms": timestamp_ms,
        "wrist_contact_status": "verified",
        "wrist_skin_temperature_c": value,
        "wrist_skin_temperature_status": "valid",
        "wrist_skin_temperature_raw": raw,
        "wrist_skin_temperature_timestamp_ms": timestamp_ms,
    })
    result["vitals"]["fever_screening"]["input"].update({
        "value_c": value,
        "quality": "valid",
        "measured": True,
        "timestamp_ms": timestamp_ms,
        "raw_register": raw,
    })
    return result


def copy_packet(**vitals_overrides):
    return copy.deepcopy(packet(**vitals_overrides))
