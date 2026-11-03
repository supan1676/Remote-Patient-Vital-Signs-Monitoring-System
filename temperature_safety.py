"""Temperature semantics shared by the backend, CLI, and tests.

Wrist skin temperature is a peripheral observation. It is not a core-body
temperature and must never be converted into one with a fixed offset. Fever
screening remains unavailable until a validated core reference and method exist.

The TMP117 sensor temperature and the clinical wrist-skin observation are kept
separate. While wrist contact is unverified, the clinical wrist value is null
and fever screening is unmeasured; the actual TMP117 sensor reading may still be
returned for display and diagnostic context.
"""
from __future__ import annotations

import math

FEVER_MESSAGE = "Core temperature unavailable — confirmation required"
CORE_STATUS = "not_available"
WRIST_STATUSES = {
    "valid",
    "warming_up",
    "low_quality",
    "stale",
    "sensor_error",
    "not_available",
    "unverified",
}
# "unverified" describes contact, not a hardware sensor reading.
SENSOR_STATUSES = WRIST_STATUSES - {"unverified"}
CONTACT_STATUSES = ("verified", "unverified")
TMP117_MIN_C = -55.0
TMP117_MAX_C = 150.0
WRIST_MIN_C = -10.0
WRIST_MAX_C = 60.0
RAW_LSB_C = 0.0078125
RAW_TOLERANCE_C = 0.02
LIMITATIONS = (
    "Wrist skin temperature is affected by ambient conditions, blood flow, "
    "contact pressure and activity. A wrist reading alone cannot confirm or "
    "rule out fever."
)
UNCERTAINTY = (
    "No validated core-temperature estimate or core reference is available."
)


def _finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _optional_int(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _status(value, allowed):
    if not isinstance(value, str) or value not in allowed:
        return None
    return value


def _raw_code(value):
    code = _optional_int(value)
    return code if code is not None and code <= 0xFFFF else None


def _converted_celsius(raw):
    if raw is None:
        return None
    signed = raw - 0x10000 if raw & 0x8000 else raw
    return signed * RAW_LSB_C


def _is_usable_raw(raw):
    return raw is not None and raw not in (0x0000, 0xFFFF)


def evaluate_temperature_safety(packet):
    """Return the conservative clinical assessment without inventing data."""
    vitals = packet.get("vitals") if isinstance(packet.get("vitals"), dict) else {}
    sensors = packet.get("sensors") if isinstance(packet.get("sensors"), dict) else {}

    sensor_status = _status(
        vitals.get("tmp117_sensor_temperature_status"), SENSOR_STATUSES)
    sensor_value = _finite(vitals.get("tmp117_sensor_temperature_c"))
    sensor_timestamp = _optional_int(
        vitals.get("tmp117_sensor_temperature_timestamp_ms"))
    sensor_raw = _raw_code(vitals.get("tmp117_sensor_temperature_raw"))

    raw_contact = vitals.get("wrist_contact_status")
    contact_status = raw_contact if raw_contact in CONTACT_STATUSES else "unverified"

    raw_status = vitals.get("wrist_skin_temperature_status")
    status = _status(raw_status, WRIST_STATUSES) or "not_available"
    wrist = _finite(vitals.get("wrist_skin_temperature_c"))
    timestamp = _optional_int(vitals.get("wrist_skin_temperature_timestamp_ms"))
    raw = _raw_code(vitals.get("wrist_skin_temperature_raw"))

    if sensors.get("tmp117") is not True:
        sensor_status = "not_available"
        sensor_value = None
        sensor_raw = None
        sensor_timestamp = None
        contact_status = "unverified"
    elif sensor_status == "valid":
        converted = _converted_celsius(sensor_raw)
        if (
            sensor_value is None
            or not _is_usable_raw(sensor_raw)
            or sensor_timestamp is None
            or not TMP117_MIN_C <= sensor_value <= TMP117_MAX_C
            or converted is None
            or abs(converted - sensor_value) > RAW_TOLERANCE_C
        ):
            sensor_status = "sensor_error"
            sensor_value = None
            sensor_raw = None
            sensor_timestamp = None
    else:
        # A non-valid sensor has no usable reading or evidence to publish.
        if sensor_status is None:
            sensor_status = "not_available"
        sensor_value = None
        sensor_raw = None
        sensor_timestamp = None

    if contact_status == "unverified":
        status = "unverified"
        wrist = None
        timestamp = None
        raw = None
    elif contact_status == "verified":
        wrist_converted = _converted_celsius(raw)
        verified = (
            sensor_status == "valid"
            and status == "valid"
            and wrist is not None
            and timestamp is not None
            and raw is not None
            and _is_usable_raw(raw)
            and sensor_value is not None
            and sensor_raw == raw
            and sensor_timestamp == timestamp
            and WRIST_MIN_C <= wrist <= WRIST_MAX_C
            and abs(sensor_value - wrist) <= RAW_TOLERANCE_C
            and wrist_converted is not None
            and abs(wrist_converted - wrist) <= RAW_TOLERANCE_C
        )
        if status == "unverified":
            verified = False
        if not verified:
            if (status in ("valid", "unverified") or wrist is not None
                    or raw is not None or timestamp is not None):
                status = "sensor_error"
            wrist = None
            timestamp = None
            raw = None

    input_payload = {
        "measurement": "wrist_skin_temperature",
        "value_c": wrist,
        "unit": "C",
        "quality": status,
        "measured": wrist is not None,
        "timestamp_ms": timestamp if wrist is not None else None,
        "raw_register": raw if wrist is not None else None,
    }
    fever = {
        "status": "not_available",
        "screening_supported": False,
        "message": FEVER_MESSAGE,
        "rule": None,
        "input": input_payload,
        "uncertainty": UNCERTAINTY,
        "limitations": LIMITATIONS,
    }
    return {
        "tmp117_sensor_temperature_c": sensor_value,
        "tmp117_sensor_temperature_status": sensor_status,
        "tmp117_sensor_temperature_raw": sensor_raw,
        "tmp117_sensor_temperature_timestamp_ms": sensor_timestamp,
        "wrist_contact_status": contact_status,
        "wrist_skin_temperature_c": wrist,
        "wrist_skin_temperature_status": status,
        "wrist_skin_temperature_timestamp_ms": timestamp,
        "wrist_skin_temperature_raw": raw,
        "estimated_core_temperature_c": None,
        "estimated_core_temperature_status": CORE_STATUS,
        "fever_screening": fever,
    }
