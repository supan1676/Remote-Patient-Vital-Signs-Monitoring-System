"""Real HTTP requests against an isolated in-memory bridge, never a device."""
from functools import partial
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import threading
import urllib.error
import urllib.request

import pytest

import telemetry_bridge as bridge
from care_workflow import CareWorkflow
from personal_baseline import PersonalBaseline
from telemetry_store import TelemetryStore


@pytest.fixture
def http_bridge(monkeypatch):
    store = TelemetryStore(':memory:')
    baseline = PersonalBaseline(store)
    care = CareWorkflow(store)
    enrollment = baseline.start('TEST', 'P01')
    monkeypatch.setattr(bridge, 'telemetry_store', store)
    monkeypatch.setattr(bridge, 'personal_baseline', baseline)
    monkeypatch.setattr(bridge, 'care_workflow', care)
    monkeypatch.setattr(bridge, 'required_authorization', None)
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(
        bridge.TelemetryRequestHandler, directory=str(Path(__file__).resolve().parents[1])))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    yield f'http://127.0.0.1:{server.server_port}', enrollment, care
    server.shutdown()
    server.server_close()
    worker.join()
    store.db.close()


def request(base, path, data=None, headers=None, method=None):
    headers = {'Content-Type': 'application/json', **(headers or {})}
    req = urllib.request.Request(base + path, data=json.dumps(data).encode() if data is not None else None,
                                 headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def test_review_is_persisted_and_cross_origin_update_is_rejected(http_bridge):
    base, enrollment, care = http_bridge
    payload = dict(device_id='TEST', enrollment_id=enrollment['id'], author='Test reviewer',
                   decision='contact', note='Synthetic integration test')
    assert request(base, '/api/reviews', payload, {'Origin': 'https://another.example'})[0] == 403
    assert care.summary('TEST')['review'] is None
    status, body = request(base, '/api/reviews', payload)
    assert status == 200 and json.loads(body)['review']['author'] == 'Test reviewer'
    status, body = request(base, '/api/care?device_id=TEST')
    assert status == 200 and json.loads(body)['review']['note'] == 'Synthetic integration test'


def test_auth_and_resource_allowlist_cover_head_and_get(http_bridge, monkeypatch):
    base, _, _ = http_bridge
    monkeypatch.setattr(bridge, 'required_authorization', 'Basic dGVzdA==')
    assert request(base, '/api/care?device_id=TEST')[0] == 401
    assert request(base, '/index.html', method='HEAD')[0] == 401
    headers = {'Authorization': 'Basic dGVzdA=='}
    assert request(base, '/api/care?device_id=TEST', headers=headers)[0] == 200
    assert request(base, '/README.md', headers=headers)[0] == 404
    assert request(base, '/index.html', headers=headers, method='HEAD')[0] == 405


def test_incident_http_transition_and_stale_enrollment(http_bridge):
    base, enrollment, care = http_bridge
    care.observe(dict(device_id='TEST', alerts=dict(sos=True, fall=False)))
    incident = care.summary('TEST')['incidents'][0]
    payload = dict(device_id='TEST', incident_id=incident['id'], author='Test reviewer')
    assert request(base, '/api/incidents', dict(payload, action='resolve'))[0] == 400
    assert request(base, '/api/incidents', dict(payload, action='acknowledge'))[0] == 200
    assert request(base, '/api/incidents', dict(payload, action='resolve'))[0] == 200
    bridge.personal_baseline.end('TEST')
    bad_review = dict(device_id='TEST', enrollment_id=enrollment['id'], author='Test reviewer',
                      decision='reviewed', note='')
    assert request(base, '/api/reviews', bad_review)[0] == 400


def test_assistant_http_is_async_checks_origin_and_rejects_expired_patient_context(http_bridge, monkeypatch):
    from decision_support import DecisionSupportService
    from test_decision_support import FakeJeff, FakeLLM
    from fixtures import packet
    base, _, _ = http_bridge
    for name, value in dict(latest_telemetry=None, last_packet_time=None,
                            hardware_status=bridge.hardware_status.copy()).items():
        monkeypatch.setattr(bridge, name, value)
    bridge._accept_packet(packet(device_id='TEST'))
    service = DecisionSupportService(bridge.assistant_context, jeff=FakeJeff(),
        llm=FakeLLM(draft='Recorded SpO2 is 98%.'))
    monkeypatch.setattr(bridge, 'assistant_service', service)
    try:
        payload = dict(device_id='TEST', question='Summarize current readings.')
        assert request(base, '/api/assistant', payload, {'Origin': 'https://another.example'})[0] == 403
        assert request(base, '/api/assistant', dict(payload, device_id='OTHER'))[0] == 400
        status, body = request(base, '/api/assistant', payload)
        assert status == 202
        identity = json.loads(body)['id']
        service.work.join()
        status, body = request(base, '/api/assistant/job?id=' + identity)
        assert status == 200 and json.loads(body)['status'] == 'complete'
        bridge.personal_baseline.end('TEST')
        assert request(base, '/api/assistant/job?id=' + identity)[0] == 409
        assert request(base, '/api/assistant/job?id=missing')[0] == 404
    finally:
        service.close()


def test_disabled_assistant_is_explicit_and_covered_by_auth(http_bridge, monkeypatch):
    base, _, _ = http_bridge
    monkeypatch.setattr(bridge, 'assistant_service', None)
    status, body = request(base, '/api/assistant')
    assert status == 200 and json.loads(body)['enabled'] is False
    assert request(base, '/api/assistant', dict(device_id='TEST', question='Latest readings?'))[0] == 503
    monkeypatch.setattr(bridge, 'required_authorization', 'Basic dGVzdA==')
    assert request(base, '/api/assistant')[0] == 401
    assert request(base, '/api/assistant/job?id=anything')[0] == 401


def test_summary_history_does_not_cross_a_wearer_boundary(http_bridge, monkeypatch):
    import time
    from fixtures import packet
    _, _, _ = http_bridge
    for name, value in dict(latest_telemetry=None, last_packet_time=None,
                            hardware_status=bridge.hardware_status.copy()).items():
        monkeypatch.setattr(bridge, name, value)
    old = packet(device_id='TEST', heart_rate=180)
    bridge.telemetry_store.record(old, now=time.time() - 30)
    bridge._accept_packet(old)
    bridge.personal_baseline.end('TEST')
    bridge.personal_baseline.start('TEST', 'New wearer')
    with pytest.raises(ValueError, match='fresh reading'):
        bridge.assistant_evidence('TEST')
    bridge._accept_packet(packet(device_id='TEST', heart_rate=72))
    result = bridge.assistant_evidence('TEST')
    assert result['measurements']['heart_rate']['value'] == 72
    assert not result['trends'] or result['trends']['heart_rate']['maximum'] == 72
