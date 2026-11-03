/**
 * Pure dashboard helpers. Kept separate from DOM code so they can be tested
 * with Node and so missing/invalid measurements are handled consistently.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.DashboardCore = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const FEVER_MESSAGE = 'Core temperature unavailable — confirmation required';
  const CORE_STATUS = 'not_available';
  const UNCERTAINTY =
    'No validated core-temperature estimate or core reference is available.';
  const LIMITATIONS =
    'Wrist skin temperature is affected by ambient conditions, blood flow, ' +
    'contact pressure and activity. A wrist reading alone cannot confirm or ' +
    'rule out fever.';
  const INSTALLED_SENSORS = ['max', 'mpu', 'tmp117'];
  const ACTIVE_MAX = 3;
  const TMP117_MIN_C = -55;
  const TMP117_MAX_C = 150;
  const STATUSES = [
    'valid', 'warming_up', 'low_quality', 'stale', 'sensor_error',
    'not_available', 'unverified',
  ];
  const SPECS = {
    heart_rate: {
      sensor: 'max', status: 'heart_rate_status', optical: true,
      label: 'Heart rate', unit: 'bpm',
    },
    spo2: {
      sensor: 'max', status: 'spo2_status', optical: true,
      label: 'Oxygen saturation', unit: '%',
    },
    wrist_skin_temperature: {
      sensor: 'tmp117', status: 'wrist_skin_temperature_status',
      field: 'wrist_skin_temperature_c',
      label: 'Wrist Skin Temperature (°C)', unit: '°C',
    },
    tmp117_sensor_temperature: {
      sensor: 'tmp117', status: 'tmp117_sensor_temperature_status',
      field: 'tmp117_sensor_temperature_c',
      label: 'TMP117 Sensor Temperature (°C)', unit: '°C',
    },
    motion_g: {
      sensor: 'mpu', status: 'motion_status',
      label: 'Movement', unit: 'g',
    },
    temp_object: {
      sensor: 'mlx', status: null,
      label: 'Legacy surface temperature', unit: '°C',
    },
  };

  function finite(value) {
    return (typeof value === 'number' && Number.isFinite(value)) ? value : null;
  }

  function rawCode(value) {
    return Number.isInteger(value) && value >= 0 && value <= 0xFFFF
      ? value : null;
  }

  function rawCelsius(raw) {
    const code = rawCode(raw);
    if (code === null) return null;
    const signed = code & 0x8000 ? code - 0x10000 : code;
    return signed * 0.0078125;
  }

  function timestamp(value) {
    return Number.isInteger(value) && value >= 0 ? value : null;
  }

  function sensorOnline(packet, sensor) {
    return packet?.sensors?.[sensor] === true;
  }

  function metricStatus(packet, key) {
    const spec = SPECS[key];
    if (!packet || !spec || !sensorOnline(packet, spec.sensor)) {
      return 'not_available';
    }
    if (!spec.status) return 'valid';
    const status = packet?.vitals?.[spec.status];
    if (!STATUSES.includes(status)) return 'not_available';

    if (key === 'tmp117_sensor_temperature') {
      if (status === 'unverified') return 'sensor_error';
      if (status === 'valid') {
        const value = finite(packet?.vitals?.tmp117_sensor_temperature_c);
        const raw = rawCode(packet?.vitals?.tmp117_sensor_temperature_raw);
        const sampleTime = timestamp(
          packet?.vitals?.tmp117_sensor_temperature_timestamp_ms);
        if (value === null || raw === null || sampleTime === null) {
          return 'sensor_error';
        }
        if (raw === 0 || raw === 0xFFFF) return 'sensor_error';
        if (value < TMP117_MIN_C || value > TMP117_MAX_C) return 'sensor_error';
        if (Math.abs(rawCelsius(raw) - value) > 0.02) return 'sensor_error';
      }
      return status;
    }

    if (key === 'wrist_skin_temperature') {
      const contact = packet?.vitals?.wrist_contact_status;
      if (contact !== 'verified') return 'unverified';
      if (status === 'unverified') return 'sensor_error';
      const raw = rawCode(packet?.vitals?.wrist_skin_temperature_raw);
      const value = finite(packet?.vitals?.wrist_skin_temperature_c);
      const sampleTime = timestamp(
        packet?.vitals?.wrist_skin_temperature_timestamp_ms);
      if (status === 'valid') {
        const sensorStatus = metricStatus(packet, 'tmp117_sensor_temperature');
        const sensorRaw = rawCode(
          packet?.vitals?.tmp117_sensor_temperature_raw);
        const sensorTime = timestamp(
          packet?.vitals?.tmp117_sensor_temperature_timestamp_ms);
        const sensorValue = finite(
          packet?.vitals?.tmp117_sensor_temperature_c);
        if (sensorStatus !== 'valid' || value === null || raw === null
            || sampleTime === null || sensorValue === null
            || sensorRaw !== raw || sensorTime !== sampleTime) {
          return 'sensor_error';
        }
        if (raw === 0 || raw === 0xFFFF) return 'sensor_error';
        if (value < -10 || value > 60) return 'sensor_error';
        if (Math.abs(rawCelsius(raw) - value) > 0.02) return 'sensor_error';
        if (Math.abs(sensorValue - value) > 0.02) return 'sensor_error';
      } else if (value !== null || raw !== null || sampleTime !== null) {
        return 'sensor_error';
      }
    }
    return status;
  }

  function metricValue(packet, key) {
    const spec = SPECS[key];
    if (!packet || !spec || !sensorOnline(packet, spec.sensor)) return null;
    if (spec.optical && packet?.vitals?.finger_on !== true) return null;
    if (metricStatus(packet, key) !== 'valid') return null;
    return finite(packet?.vitals?.[spec.field || key]);
  }

  function temperatureAssessment(packet) {
    const contactStatus =
      packet?.vitals?.wrist_contact_status === 'verified'
        ? 'verified' : 'unverified';
    const sensorStatus = metricStatus(packet, 'tmp117_sensor_temperature');
    const sensorValue = metricValue(packet, 'tmp117_sensor_temperature');
    const sensorRaw = sensorValue === null ? null : rawCode(
      packet?.vitals?.tmp117_sensor_temperature_raw);
    const sensorTimestamp = sensorValue === null ? null : timestamp(
      packet?.vitals?.tmp117_sensor_temperature_timestamp_ms);
    const status = metricStatus(packet, 'wrist_skin_temperature');
    const wrist = metricValue(packet, 'wrist_skin_temperature');
    const rawValue = wrist === null ? null : rawCode(
      packet?.vitals?.wrist_skin_temperature_raw);
    const wristTimestamp = wrist === null ? null : timestamp(
      packet?.vitals?.wrist_skin_temperature_timestamp_ms);
    const measured = wrist !== null;
    const input = {
      measurement: 'wrist_skin_temperature',
      value_c: wrist,
      unit: 'C',
      quality: status,
      measured,
      timestamp_ms: measured ? wristTimestamp : null,
      raw_register: measured ? rawValue : null,
    };
    return {
      tmp117_sensor_temperature_c: sensorValue,
      tmp117_sensor_temperature_status: sensorStatus,
      tmp117_sensor_temperature_raw: sensorRaw,
      tmp117_sensor_temperature_timestamp_ms: sensorTimestamp,
      wrist_contact_status: contactStatus,
      wrist_skin_temperature_c: wrist,
      wrist_skin_temperature_status: status,
      wrist_skin_temperature_raw: rawValue,
      wrist_skin_temperature_timestamp_ms: wristTimestamp,
      estimated_core_temperature_c: null,
      estimated_core_temperature_status: CORE_STATUS,
      estimated_core_available: false,
      fever_screening_status: 'not_available',
      fever_screening_available: false,
      fever_screening_input: input,
      fever_screening_rule: null,
      uncertainty: UNCERTAINTY,
      limitations: LIMITATIONS,
      message: FEVER_MESSAGE,
      measured,
    };
  }

  function activeSensorCount(packet) {
    if (!packet?.sensors) return 0;
    return INSTALLED_SENSORS.filter(key => packet.sensors[key] === true).length;
  }

  function sensorHealth(packet, key) {
    if (!packet) return {status: 'not_available', error: null};
    const health = packet?.sensor_health?.[key];
    if (!health) {
      return {
        status: sensorOnline(packet, key) ? 'warming_up' : 'not_available',
        error: null,
      };
    }
    return {
      status: STATUSES.includes(health.status) ? health.status : 'not_available',
      error: typeof health.error === 'string' ? health.error : null,
    };
  }

  function statusLabel(status) {
    return {
      valid: 'Valid',
      warming_up: 'Warming up',
      low_quality: 'Low quality',
      stale: 'Stale',
      sensor_error: 'Sensor error',
      not_available: 'Not available',
      unverified: 'Unverified',
    }[status] || 'Not available';
  }

  function gapAwarePath(points, key, x, y) {
    let path = '';
    let started = false;
    for (const point of points || []) {
      const value = finite(point?.[key]);
      if (value === null) {
        started = false;
        continue;
      }
      path += `${started ? 'L' : 'M'}${x(point.time).toFixed(2)},${y(value).toFixed(2)} `;
      started = true;
    }
    return path;
  }

  function csv(points) {
    const columns = ['time', 'heart_rate', 'spo2',
                     'wrist_skin_temperature', 'motion_g', 'samples'];
    const headers = ['timestamp', 'heart_rate_bpm', 'spo2_percent',
                     'wrist_skin_temperature_c', 'motion_g', 'samples'];
    const rows = (points || []).filter(point => (finite(point?.samples) || 0) > 0);
    return [headers.join(','), ...rows.map(point => columns.map(column => {
      if (column === 'time') return new Date(point.time * 1000).toISOString();
      const value = finite(point[column]);
      return value === null ? '' : value;
    }).join(','))].join('\n');
  }

  return {
    FEVER_MESSAGE,
    CORE_STATUS,
    ACTIVE_MAX,
    SPECS,
    finite,
    metricStatus,
    metricValue,
    temperatureAssessment,
    activeSensorCount,
    sensorHealth,
    statusLabel,
    gapAwarePath,
    csv,
  };
});
