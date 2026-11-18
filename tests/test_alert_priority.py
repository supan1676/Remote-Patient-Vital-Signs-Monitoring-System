"""Synthetic-policy correctness, leakage boundaries and real inference seams."""
import json
from pathlib import Path
import time

import joblib
import numpy as np
import pytest
from threadpoolctl import threadpool_limits

from alert_priority import AlertPriorityService, extract_features, policy_labels
from fixtures import packet
from ml.generate_priority import generate


def signals(hr=72, spo2=98, motion=1.0):
    x = np.empty((1, 60, 3), dtype=np.float32)
    x[:, :, :] = [hr, spo2, motion]
    return x


@pytest.mark.parametrize('hr,spo2,expected', [(72, 98, 0), (110, 93, 1), (150, 88, 2)])
def test_policy_colors_are_documented_synthetic_labels(hr, spo2, expected):
    f = extract_features(signals(hr, spo2), np.ones((1, 60), bool))
    assert policy_labels(f).tolist() == [expected]


def test_quality_and_persistence_boundaries_do_not_invent_values():
    x = signals()
    x[0, -9:, 1] = 88
    good = np.ones((1, 60), bool)
    assert policy_labels(extract_features(x, good))[0] == 1
    x[0, -10:, 1] = 88
    assert policy_labels(extract_features(x, good))[0] == 2
    good[0, -1] = False
    assert policy_labels(extract_features(x, good))[0] == -1
    good[:] = True
    good[0, :7] = False  # Less than 90% coverage.
    assert policy_labels(extract_features(x, good))[0] == -1


def test_generator_profiles_and_trajectory_families_are_disjoint(tmp_path):
    manifest = generate(tmp_path, scenarios=1000, batch_size=128)
    labels = np.load(tmp_path / 'labels.npy')
    splits = np.load(tmp_path / 'splits.npy')
    profiles = np.load(tmp_path / 'profiles.npy')
    families = np.load(tmp_path / 'families.npy')
    assert manifest['source'] == 'synthetic' and manifest['human_reviewed'] is False
    assert manifest['timepoints'] == 60000
    for i in range(3):
        for j in range(i):
            assert not set(profiles[splits == i]) & set(profiles[splits == j])
            assert not set(families[splits == i]) & set(families[splits == j])
    x = np.load(tmp_path / 'signals.npy')
    q = np.load(tmp_path / 'quality.npy')
    np.testing.assert_array_equal(labels, policy_labels(extract_features(x, q)))
    with pytest.raises(ValueError, match='already exists'):
        generate(tmp_path, scenarios=1000)


def observation(second, hr=72, spo2=98):
    p = packet(device_id='PRIORITY-TEST', heart_rate=hr, spo2=spo2)
    p['uptime_s'] = second
    for key in ('heart_rate_timestamp_ms', 'spo2_timestamp_ms', 'motion_timestamp_ms',
                'tmp117_sensor_temperature_timestamp_ms'):
        p['vitals'][key] = second * 1000
    return p


def trained_service():
    path = Path('models/alert_priority.joblib')
    if not path.exists():
        pytest.skip('Synthetic model is produced by the documented training command.')
    return AlertPriorityService(path)


def feed(service, hr=72, spo2=98, enrollment='P01'):
    for second in range(100, 160):
        service.submit(observation(second, hr, spo2), enrollment_id=enrollment)
        service.work.join()
    return observation(159, hr, spo2)


@pytest.mark.parametrize('hr,spo2,zone', [(72, 98, 'green'), (110, 93, 'yellow'), (150, 88, 'red')])
def test_trained_model_runtime_matches_batch_and_is_explicitly_synthetic(hr, spo2, zone):
    service = trained_service()
    try:
        latest = feed(service, hr, spo2)
        result = service.snapshot(latest)
        features = extract_features(signals(hr, spo2), np.ones((1, 60), bool))
        with threadpool_limits(limits=1):
            expected = service.model['estimator'].predict_proba(features)[0]
        assert result['zone'] == zone
        assert result['source'] == 'trained_model'
        assert result['synthetic_training'] is True and result['clinically_validated'] is False
        np.testing.assert_allclose(list(result['class_scores'].values()), expected)
    finally:
        service.close()


def test_unknown_gates_and_emergency_bypass_work_without_a_model(tmp_path):
    service = AlertPriorityService(tmp_path / 'absent.joblib')
    try:
        current = observation(1)
        current['alerts']['sos'] = True
        assert service.snapshot(current)['zone'] == 'red'
        assert service.snapshot(current)['source'] == 'device_alert'
        current['alerts']['sos'] = False
        assert service.snapshot(current)['zone'] == 'unknown'
        service.submit(current)
        service.work.join()
        assert service.snapshot(current)['observations'] == 1
        assert service.snapshot(None)['zone'] == 'unknown'
    finally:
        service.close()


def test_bad_current_quality_patient_change_and_disconnect_clear_a_prior_color():
    service = trained_service()
    try:
        current = feed(service)
        assert service.snapshot(current)['zone'] == 'green'
        current['vitals']['heart_rate_status'] = 'low_quality'
        current['vitals']['heart_rate'] = None
        assert service.snapshot(current)['zone'] == 'unknown'
        current = observation(160)
        optical = dict(device_id=current['device_id'], status='prediction', label='unreliable')
        assert service.snapshot(current, optical)['zone'] == 'unknown'
        service.submit(current, enrollment_id='P02')
        service.work.join()
        assert service.snapshot(current)['zone'] == 'unknown'
        assert service.snapshot(current)['observations'] == 1
        service.last_received = time.monotonic() - 6
        assert service.snapshot(current)['zone'] == 'unknown'
    finally:
        service.close()
