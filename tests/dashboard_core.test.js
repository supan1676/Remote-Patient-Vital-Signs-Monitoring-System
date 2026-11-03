'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const core = require('../assets/dashboard_core.js');
const { packet, verifiedPacket } = require('./fixtures.js');

test('actual TMP117 sensor is exposed separately from unverified wrist contact', () => {
  const p = packet();
  assert.equal(core.metricValue(p, 'tmp117_sensor_temperature'), 29.6484375);
  assert.equal(core.metricStatus(p, 'tmp117_sensor_temperature'), 'valid');
  assert.equal(core.metricValue(p, 'wrist_skin_temperature'), null);
  assert.equal(core.metricStatus(p, 'wrist_skin_temperature'), 'unverified');
  assert.equal(core.metricValue(p, 'heart_rate'), 72);
  assert.equal(core.activeSensorCount(p), 3);
});

test('verified contact exposes the clinical wrist value only with matching evidence', () => {
  const p = verifiedPacket();
  assert.equal(core.metricValue(p, 'wrist_skin_temperature'), 29.6484375);
  assert.equal(core.metricStatus(p, 'wrist_skin_temperature'), 'valid');

  const mismatch = verifiedPacket();
  mismatch.vitals.tmp117_sensor_temperature_raw = 0x0F00;
  mismatch.vitals.tmp117_sensor_temperature_c = 30;
  assert.equal(core.metricStatus(mismatch, 'wrist_skin_temperature'),
    'sensor_error');
  assert.equal(core.metricValue(mismatch, 'wrist_skin_temperature'), null);
});

test('non-valid status, offline sensor and no finger are never substituted', () => {
  const p = verifiedPacket();
  p.vitals.wrist_skin_temperature_status = 'low_quality';
  p.vitals.wrist_skin_temperature_c = null;
  p.vitals.wrist_skin_temperature_raw = null;
  p.vitals.wrist_skin_temperature_timestamp_ms = null;
  assert.equal(core.metricValue(p, 'wrist_skin_temperature'), null);
  assert.equal(core.metricStatus(p, 'wrist_skin_temperature'), 'low_quality');
  p.sensors.tmp117 = false;
  assert.equal(core.metricValue(p, 'wrist_skin_temperature'), null);
  assert.equal(core.metricStatus(p, 'wrist_skin_temperature'), 'not_available');
  p.vitals.finger_on = false;
  assert.equal(core.metricValue(p, 'heart_rate'), null);
});

test('temperature assessment never invents core temperature or fever', () => {
  const t = core.temperatureAssessment(packet());
  assert.equal(t.tmp117_sensor_temperature_c, 29.6484375);
  assert.equal(t.tmp117_sensor_temperature_status, 'valid');
  assert.equal(t.tmp117_sensor_temperature_raw, 3795);
  assert.equal(t.tmp117_sensor_temperature_timestamp_ms, 5000);
  assert.equal(t.wrist_contact_status, 'unverified');
  assert.equal(t.wrist_skin_temperature_c, null);
  assert.equal(t.wrist_skin_temperature_status, 'unverified');
  assert.equal(t.wrist_skin_temperature_raw, null);
  assert.equal(t.wrist_skin_temperature_timestamp_ms, null);
  assert.equal(t.estimated_core_temperature_c, null);
  assert.equal(t.estimated_core_temperature_status, 'not_available');
  assert.equal(t.estimated_core_available, false);
  assert.equal(t.fever_screening_status, 'not_available');
  assert.equal(t.fever_screening_available, false);
  assert.equal(t.fever_screening_rule, null);
  assert.equal(t.fever_screening_input.measurement, 'wrist_skin_temperature');
  assert.equal(t.fever_screening_input.quality, 'unverified');
  assert.equal(t.fever_screening_input.measured, false);
  assert.equal(t.fever_screening_input.value_c, null);
  assert.equal(t.fever_screening_input.timestamp_ms, null);
  assert.equal(t.fever_screening_input.raw_register, null);
  assert.match(t.uncertainty, /No validated core-temperature/);
  assert.match(t.limitations, /cannot confirm or rule out fever/);
  assert.equal(t.message,
    'Core temperature unavailable — confirmation required');

  const contradictory = packet();
  contradictory.vitals.fever_screening.message = 'Fever detected';
  contradictory.vitals.fever_screening.rule = 'temperature > 38 C';
  contradictory.vitals.fever_screening.uncertainty = 'none';
  contradictory.vitals.fever_screening.limitations = 'none';
  const c = core.temperatureAssessment(contradictory);
  assert.equal(c.message,
    'Core temperature unavailable — confirmation required');
  assert.equal(c.fever_screening_rule, null);
  assert.match(c.uncertainty, /No validated core-temperature/);
  assert.match(c.limitations, /cannot confirm or rule out fever/);
  assert.equal(c.fever_screening_input.measured, false);
});

test('verified assessment keeps core and fever unavailable', () => {
  const t = core.temperatureAssessment(verifiedPacket());
  assert.equal(t.wrist_contact_status, 'verified');
  assert.equal(t.wrist_skin_temperature_c, 29.6484375);
  assert.equal(t.wrist_skin_temperature_raw, 3795);
  assert.equal(t.fever_screening_input.measured, true);
  assert.equal(t.fever_screening_input.value_c, 29.6484375);
  assert.equal(t.estimated_core_temperature_c, null);
  assert.equal(t.fever_screening_status, 'not_available');
  assert.equal(t.message,
    'Core temperature unavailable — confirmation required');
});

test('stuck, missing and inconsistent sensor evidence is masked', () => {
  const p = packet();
  p.vitals.tmp117_sensor_temperature_raw = 0xFFFF;
  p.vitals.tmp117_sensor_temperature_c = -0.0078125;
  assert.equal(core.metricStatus(p, 'tmp117_sensor_temperature'),
    'sensor_error');
  assert.equal(core.metricValue(p, 'tmp117_sensor_temperature'), null);
  const t = core.temperatureAssessment(p);
  assert.equal(t.tmp117_sensor_temperature_c, null);
  assert.equal(t.tmp117_sensor_temperature_status, 'sensor_error');
  assert.equal(t.tmp117_sensor_temperature_raw, null);

  const missingRaw = packet();
  missingRaw.vitals.tmp117_sensor_temperature_raw = null;
  assert.equal(core.metricStatus(missingRaw, 'tmp117_sensor_temperature'),
    'sensor_error');
  assert.equal(core.metricValue(missingRaw, 'tmp117_sensor_temperature'), null);
  const missing = core.temperatureAssessment(missingRaw);
  assert.equal(missing.tmp117_sensor_temperature_c, null);
  assert.equal(missing.tmp117_sensor_temperature_raw, null);
  assert.equal(missing.wrist_skin_temperature_c, null);

  const mismatch = packet();
  mismatch.vitals.tmp117_sensor_temperature_raw = 0x0F00;
  assert.equal(core.metricStatus(mismatch, 'tmp117_sensor_temperature'),
    'sensor_error');
  assert.equal(core.metricValue(mismatch, 'tmp117_sensor_temperature'), null);

  const outOfRange = packet();
  outOfRange.vitals.tmp117_sensor_temperature_c = 160;
  outOfRange.vitals.tmp117_sensor_temperature_raw = 0x5000;
  assert.equal(core.metricStatus(outOfRange, 'tmp117_sensor_temperature'),
    'sensor_error');
  assert.equal(core.metricValue(outOfRange, 'tmp117_sensor_temperature'), null);

  const contactStatus = packet();
  contactStatus.vitals.tmp117_sensor_temperature_c = null;
  contactStatus.vitals.tmp117_sensor_temperature_status = 'unverified';
  contactStatus.vitals.tmp117_sensor_temperature_raw = null;
  contactStatus.vitals.tmp117_sensor_temperature_timestamp_ms = null;
  assert.equal(core.metricStatus(contactStatus, 'tmp117_sensor_temperature'),
    'sensor_error');
  assert.equal(core.metricValue(contactStatus, 'tmp117_sensor_temperature'), null);
  assert.equal(core.metricStatus(contactStatus, 'wrist_skin_temperature'),
    'unverified');
});

test('actual sensor can be valid outside the clinical wrist range', () => {
  const p = packet();
  p.vitals.tmp117_sensor_temperature_c = 70;
  p.vitals.tmp117_sensor_temperature_raw = 0x2300;
  assert.equal(core.metricValue(p, 'tmp117_sensor_temperature'), 70);
  assert.equal(core.metricStatus(p, 'tmp117_sensor_temperature'), 'valid');
  assert.equal(core.metricValue(p, 'wrist_skin_temperature'), null);
  assert.equal(core.metricStatus(p, 'wrist_skin_temperature'), 'unverified');
});

test('chart path starts a new segment across a missing value', () => {
  const points = [
    { time: 0, heart_rate: 70 },
    { time: 1, heart_rate: null },
    { time: 2, heart_rate: 80 },
  ];
  const path = core.gapAwarePath(
    points, 'heart_rate', t => t * 10, v => v);
  assert.equal(path.match(/M/g).length, 2);
  assert.equal((path.match(/L/g) || []).length, 0);
  assert.match(path, /M0\.00,70\.00/);
  assert.match(path, /M20\.00,80\.00/);
});

test('CSV exports clinical wrist data and leaves gaps blank', () => {
  const csv = core.csv([
    { time: 0, heart_rate: 70, spo2: 98, wrist_skin_temperature: null,
      motion_g: 1, samples: 1 },
    { time: 60, heart_rate: null, spo2: null, wrist_skin_temperature: 29.6,
      motion_g: null, samples: 1 },
  ]);
  const lines = csv.split('\n');
  assert.match(lines[0], /wrist_skin_temperature_c/);
  assert.match(lines[0], /heart_rate_bpm/);
  assert.doesNotMatch(lines[0], /temp_object/);
  assert.doesNotMatch(lines[0], /tmp117_sensor_temperature/);
  assert.equal(lines[1], '1970-01-01T00:00:00.000Z,70,98,,1,1');
  assert.equal(lines[2], '1970-01-01T00:01:00.000Z,,,29.6,,1');
});

test('sensor health and labels distinguish missing from valid', () => {
  const p = packet();
  assert.equal(core.sensorHealth(p, 'tmp117').status, 'valid');
  assert.equal(core.statusLabel('low_quality'), 'Low quality');
  assert.equal(core.statusLabel('sensor_error'), 'Sensor error');
  assert.equal(core.statusLabel('unverified'), 'Unverified');
  p.sensor_health.tmp117.status = 'stale';
  assert.equal(core.sensorHealth(p, 'tmp117').status, 'stale');
});
