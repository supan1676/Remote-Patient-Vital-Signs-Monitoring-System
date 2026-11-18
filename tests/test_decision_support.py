"""Scope, missing evidence, actual orchestration boundaries and withholding behavior."""
import copy
import threading
import time

import pytest

from decision_support import (DecisionSupportService, OllamaSummary, capture_evidence,
                              check_draft, select_evidence, attach_provenance)
from fixtures import packet


def evidence():
    p = packet(device_id='TEST')
    p['vitals']['heart_rate'] = None
    p['vitals']['heart_rate_status'] = 'low_quality'
    return capture_evidence(dict(status=dict(connected=True, simulation=True), telemetry=p,
        priority=dict(zone='unknown', synthetic_training=True, clinically_validated=False),
        optical=dict(status='prediction', label='unreliable')),
        dict(points=[dict(time=time.time(), heart_rate=72, spo2=98, motion_g=1)], bucket_seconds=1),
        [dict(kind='sos', status='open', created_at=time.time(), acknowledged_by='PRIVATE AUTHOR')], 'P01')


class FakeJeff:
    def __init__(self, route='t1', ground='supported', abstain=False):
        self.route, self.ground, self.abstain = route, ground, abstain
        self.calls = []

    def call(self, **request):
        self.calls.append(request)
        return dict(value=self.route if request['operation'] == 'route' else self.ground,
                    abstained=self.abstain, confidence=.9, function='synthetic-test-double')

    def close(self):
        pass


class FakeLLM:
    def __init__(self, draft='These simulated readings have unavailable heart rate and SpO2 of 98%.', hook=None):
        self.draft, self.hook, self.calls = draft, hook, []

    def summarize(self, question, selected, feedback=None):
        self.calls.append(copy.deepcopy(selected))
        if self.hook:
            self.hook()
        return self.draft, dict(model='synthetic-test-double')


def test_freeze_preserves_missing_values_and_excludes_free_text():
    e = evidence()
    assert e['measurements']['heart_rate']['value'] is None
    assert e['measurements']['heart_rate']['status'] == 'low_quality'
    assert e['simulation'] is True
    assert 'PRIVATE AUTHOR' not in str(e)
    assert 'trends' not in select_evidence(e, 't1')
    assert 'trends' in select_evidence(e, 't2')
    assert 'enrollment_id' not in select_evidence(e, 't2')


def test_simulation_disclosure_is_attached_even_when_the_llm_omits_it():
    e = evidence()
    original = 'SpO2 is 98%. Heart rate is unavailable.'
    rendered = attach_provenance(original, e)
    assert rendered == 'Simulated readings. ' + original
    assert check_draft(rendered, e) is None
    service = DecisionSupportService(lambda: ('TEST', 'P01'), jeff=FakeJeff(), llm=FakeLLM(draft=original))
    try:
        job = service.submit('Latest readings?', e)
        service.work.join()
        assert service.get(job['id'])['status'] == 'complete'
        assert service.get(job['id'])['summary'] == rendered
    finally:
        service.close()


@pytest.mark.parametrize('draft', [
    'Heart rate is 72 bpm.',  # No simulation disclosure.
    'Simulated SpO2 is 22%.',  # Invented number.
    'The simulated patient is medically safe.',
    'Simulated oxygen readings stayed stable over the past hour.',
    'The simulated patient probably has a respiratory infection.',
])
def test_deterministic_draft_checks_withhold_bad_claims(draft):
    assert check_draft(draft, evidence())


@pytest.mark.parametrize('url,model', [('https://outside.example', 'gemma2:2b'),
    ('http://127.0.0.1.evil.example', 'gemma2:2b'),
    ('http://127.0.0.1:11434', 'qwen3.5:397b-cloud')])
def test_summary_configuration_does_not_silently_send_data_to_cloud(url, model):
    with pytest.raises(ValueError):
        OllamaSummary(model, url)


def test_supported_summary_uses_the_same_frozen_evidence_for_generation_and_grounding():
    jeff, llm = FakeJeff(route='t2'), FakeLLM()
    service = DecisionSupportService(lambda: ('TEST', 'P01'), jeff=jeff, llm=llm)
    try:
        job = service.submit('Summarize recent oxygen trends.', evidence())
        service.work.join()
        result = service.get(job['id'])
        assert result['status'] == 'complete'
        assert result['summary'] == llm.draft
        assert result['tool'] == 'Recent trends'
        assert jeff.calls[-1]['operation'] == 'ground'
        import json
        assert json.loads(jeff.calls[-1]['sources']) == llm.calls[0]
        assert result['evidence_sha256']
    finally:
        service.close()


@pytest.mark.parametrize('ground,abstain', [('contradicted', False), ('unsupported', False), ('supported', True)])
def test_grounding_failure_or_abstention_never_publishes_a_draft(ground, abstain):
    jeff = FakeJeff(ground=ground)
    if abstain:
        original = jeff.call
        def call(**request):
            result = original(**request)
            if request['operation'] == 'ground':
                result['abstained'] = True
            return result
        jeff.call = call
    service = DecisionSupportService(lambda: ('TEST', 'P01'), jeff=jeff, llm=FakeLLM())
    try:
        job = service.submit('Latest readings?', evidence())
        service.work.join()
        assert service.get(job['id'])['status'] == 'withheld'
        assert service.get(job['id'])['summary'] is None
    finally:
        service.close()


def test_patient_change_during_inference_invalidates_the_result():
    current = ['TEST', 'P01']
    llm = FakeLLM(hook=lambda: current.__setitem__(1, 'P02'))
    service = DecisionSupportService(lambda: tuple(current), jeff=FakeJeff(), llm=llm)
    try:
        job = service.submit('Latest readings?', evidence())
        service.work.join()
        with pytest.raises(ValueError, match='earlier patient'):
            service.get(job['id'])
        assert service.jobs[job['id']]['summary'] is None
    finally:
        service.close()


def test_slow_generation_is_nonblocking_and_duplicate_submissions_are_bounded():
    started, finish = threading.Event(), threading.Event()
    def wait():
        started.set()
        assert finish.wait(timeout=5)
    service = DecisionSupportService(lambda: ('TEST', 'P01'), jeff=FakeJeff(), llm=FakeLLM(hook=wait))
    try:
        job = service.submit('Latest readings?', evidence())
        assert started.wait(timeout=2)
        assert service.get(job['id'])['status'] == 'running'
        with pytest.raises(ValueError, match='already being prepared'):
            service.submit('Another summary?', evidence())
        finish.set()
        service.work.join()
        assert service.get(job['id'])['status'] == 'complete'
    finally:
        finish.set()
        service.close()


def test_route_abstention_does_not_run_the_llm():
    llm = FakeLLM()
    service = DecisionSupportService(lambda: ('TEST', 'P01'), jeff=FakeJeff(abstain=True), llm=llm)
    try:
        job = service.submit('Latest readings?', evidence())
        service.work.join()
        assert service.get(job['id'])['status'] == 'withheld'
        assert not llm.calls
    finally:
        service.close()
