import pytest

from care_workflow import CareWorkflow
from fixtures import packet
from personal_baseline import PersonalBaseline
from telemetry_store import TelemetryStore


def test_incidents_survive_inactive_signal_and_restart_and_require_acknowledgement():
    store = TelemetryStore(':memory:')
    PersonalBaseline(store)
    care = CareWorkflow(store)
    p = packet()
    p['alerts']['sos'] = True
    care.observe(p)
    care.observe(p)
    incident = care.summary(p['device_id'])['incidents'][0]
    assert len(care.summary(p['device_id'])['incidents']) == 1
    p['alerts']['sos'] = False
    care.observe(p)
    restarted = CareWorkflow(store)
    assert restarted.summary(p['device_id'])['incidents'][0]['status'] == 'open'
    with pytest.raises(ValueError):
        restarted.update_incident(p['device_id'], incident['id'], 'resolve', 'Reviewer')
    restarted.update_incident(p['device_id'], incident['id'], 'acknowledge', 'Reviewer')
    result = restarted.update_incident(p['device_id'], incident['id'], 'resolve', 'Reviewer')
    assert result['incidents'][0]['resolved_by'] == 'Reviewer'
    assert result['incidents'][0]['status'] == 'resolved'


def test_review_cannot_be_attached_to_a_replaced_enrollment():
    store = TelemetryStore(':memory:')
    baseline = PersonalBaseline(store)
    care = CareWorkflow(store)
    first = baseline.start('TEST', 'P01')
    care.add_review('TEST', first['id'], 'Reviewer', 'reviewed', 'Original note')
    assert care.summary('TEST')['review']['note'] == 'Original note'
    baseline.end('TEST')
    second = baseline.start('TEST', 'P02')
    assert care.summary('TEST')['review'] is None
    with pytest.raises(ValueError):
        care.add_review('TEST', first['id'], 'Reviewer', 'reviewed', 'Wrong patient')
    with pytest.raises(ValueError):
        care.add_review('TEST', second['id'], '', 'reviewed', '')
    assert store.db.execute('SELECT COUNT(*) FROM reviews').fetchone()[0] == 1
