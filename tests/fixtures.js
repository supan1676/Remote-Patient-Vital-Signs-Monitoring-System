'use strict';

function packet() {
  return {
    device_id: 'RPM-NODE-01',
    schema_version: 2,
    sensors: {
      oled: true, max: true, mpu: true, tmp117: true,
      sht40: false, mlx: false, active: 3, active_max: 3,
    },
    sensor_health: {
      max: { present: true, status: 'valid', error: 'none' },
      mpu: { present: true, status: 'valid', error: 'none' },
      tmp117: { present: true, status: 'valid', error: 'none' },
    },
    vitals: {
      heart_rate: 72,
      heart_rate_status: 'valid',
      spo2: 98,
      spo2_status: 'valid',
      finger_on: true,
      tmp117_sensor_temperature_c: 29.6484375,
      tmp117_sensor_temperature_status: 'valid',
      tmp117_sensor_temperature_raw: 3795,
      tmp117_sensor_temperature_timestamp_ms: 5000,
      wrist_contact_status: 'unverified',
      wrist_skin_temperature_c: null,
      wrist_skin_temperature_status: 'unverified',
      wrist_skin_temperature_raw: null,
      wrist_skin_temperature_timestamp_ms: null,
      motion_g: 1.0,
      motion_status: 'valid',
      estimated_core_temperature_c: null,
      estimated_core_temperature_status: 'not_available',
      fever_screening: {
        status: 'not_available',
        message: 'Core temperature unavailable — confirmation required',
        rule: null,
        input: {
          measurement: 'wrist_skin_temperature',
          value_c: null,
          unit: 'C',
          quality: 'unverified',
          measured: false,
          timestamp_ms: null,
          raw_register: null,
        },
        uncertainty: 'No validated core-temperature estimate or core reference is available.',
        limitations: 'Wrist skin temperature cannot confirm or rule out fever.',
      },
    },
    alerts: { sos: false, fall: false },
  };
}

function verifiedPacket() {
  const p = packet();
  p.vitals.tmp117_sensor_temperature_c = 29.6484375;
  p.vitals.tmp117_sensor_temperature_status = 'valid';
  p.vitals.tmp117_sensor_temperature_raw = 3795;
  p.vitals.tmp117_sensor_temperature_timestamp_ms = 5000;
  p.vitals.wrist_contact_status = 'verified';
  p.vitals.wrist_skin_temperature_c = 29.6484375;
  p.vitals.wrist_skin_temperature_status = 'valid';
  p.vitals.wrist_skin_temperature_raw = 3795;
  p.vitals.wrist_skin_temperature_timestamp_ms = 5000;
  p.vitals.fever_screening.input = {
    measurement: 'wrist_skin_temperature',
    value_c: 29.6484375,
    unit: 'C',
    quality: 'valid',
    measured: true,
    timestamp_ms: 5000,
    raw_register: 3795,
  };
  return p;
}

module.exports = { packet, verifiedPacket };
