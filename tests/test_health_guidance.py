"""Symptom overrides, explicit uncertainty and no invented diagnoses."""
import pytest
import threading

from health_guidance import clinical_context, make_guidance, validate_symptoms
from test_decision_support import evidence, FakeJeff, FakeLLM
from decision_support import DecisionSupportService, check_draft


def sample(symptoms=None, hr=76.1, oxygen=98.2, quality='usable'):
    e = evidence()
    e['measurements']['heart_rate'].update(value=hr, status='valid' if hr is not None else 'not_available')
    e['measurements']['spo2'].update(value=oxygen, status='valid' if oxygen is not None else 'not_available')
    e['optical']['label'] = quality
    e['clinical_context'] = clinical_context(symptoms)
    e['priority']['zone'] = 'green'
    return e


@pytest.mark.parametrize('symptom', ['severe_breathing', 'chest_pressure', 'confusion', 'blue_lips'])
def test_severe_reported_symptoms_override_normal_readings_and_green(symptom):
    result = make_guidance(sample(dict(status='reported', selected=[symptom])))
    assert result['level'] == 'emergency'
    assert 'Do not wait' in result['action']
    assert 'not a final medical evaluation' in result['disclaimer']


def test_palpitations_with_breathlessness_need_emergency_attention():
    e = sample(dict(status='reported', selected=['palpitations', 'breathless']))
    assert make_guidance(e)['level'] == 'emergency'


def test_emergency_output_does_not_anchor_on_a_less_serious_possible_cause():
    e = sample(dict(status='reported', selected=['cough', 'feverish', 'chest_pressure']))
    result = make_guidance(e)
    assert result['level'] == 'emergency'
    assert not any('respiratory infection' in text for text in result['possible_explanations'])
    assert 'Emergency assessment' in result['possible_explanations'][0]


def test_normal_readings_do_not_manufacture_an_illness_or_certify_safety():
    unknown = make_guidance(sample())
    assert unknown['level'] == 'symptoms_needed'
    assert 'do not support naming a particular illness' in unknown['possible_explanations'][0]
    none = make_guidance(sample(dict(status='none_reported', selected=[])))
    assert none['level'] == 'observe'
    assert 'does not establish medical safety' in none['reason']


def test_reported_cough_and_feverishness_add_possible_explanations_without_measured_fever():
    result = make_guidance(sample(dict(status='reported', selected=['cough', 'feverish'])))
    assert 'respiratory infection' in result['possible_explanations'][0]
    assert 'cannot confirm' in result['possible_explanations'][0]
    assert any('not measured' in v for v in result['missing_information'])
    assert result['level'] == 'symptom_review'


def test_missing_or_poor_quality_measurements_are_not_reassuring():
    assert make_guidance(sample(hr=None, oxygen=None))['level'] == 'insufficient_evidence'
    assert make_guidance(sample(oxygen=85, quality='unreliable'))['level'] == 'insufficient_evidence'
    assert make_guidance(sample(oxygen=88))['level'] == 'confirm_and_review'
    symptoms = dict(status='reported', selected=['breathless'])
    assert make_guidance(sample(symptoms, hr=None, oxygen=None))['level'] == 'prompt_review'


@pytest.mark.parametrize('value', [dict(status='none_reported', selected=['cough']),
    dict(status='reported', selected=['invented_symptom']), dict(status='reported', selected=[]),
    dict(status='reported', selected=['cough', 'cough']), dict(status='unknown', selected='cough')])
def test_symptom_contract_rejects_unknown_or_contradictory_input(value):
    with pytest.raises(ValueError):
        validate_symptoms(value)


def test_emergency_guidance_is_immediate_while_ai_generates_in_background():
    started, finish = threading.Event(), threading.Event()
    def slow_generation():
        started.set()
        assert finish.wait(timeout=5)
    llm = FakeLLM(draft='Simulated severe breathing difficulty is an emergency warning sign, even with ordinary pulse and oxygen readings.', hook=slow_generation)
    service = DecisionSupportService(lambda: ('TEST', 'P01'), jeff=FakeJeff(), llm=llm)
    try:
        original = sample()
        job = service.submit('Interpret latest readings.', original,
            dict(status='reported', selected=['severe_breathing']))
        assert job['assessment']['level'] == 'emergency'
        assert 'clinical_context' not in original or original['clinical_context']['status'] == 'unknown'
        assert started.wait(timeout=2)
        running = service.get(job['id'])
        assert running['status'] == 'running'
        assert running['assessment']['level'] == 'emergency'
        assert 'Do not wait' in running['assessment']['action']
        finish.set()
        service.work.join()
        result = service.get(job['id'])
        assert result['status'] == 'complete' and result['assessment']['level'] == 'emergency'
        assert result['summary'] == llm.draft
        assert [call['operation'] for call in service.jeff.calls] == ['route', 'ground']
    finally:
        finish.set()
        service.close()


def test_emergency_action_survives_a_failed_ai_check():
    service = DecisionSupportService(lambda: ('TEST', 'P01'), jeff=FakeJeff(ground='unsupported'), llm=FakeLLM())
    try:
        job = service.submit('Explain the symptoms.', sample(), dict(status='reported', selected=['chest_pressure']))
        service.work.join()
        result = service.get(job['id'])
        assert result['status'] == 'withheld'
        assert result['summary'] is None
        assert result['assessment']['level'] == 'emergency'
        assert 'Call your local emergency number' in result['assessment']['action']
    finally:
        service.close()


@pytest.mark.parametrize('draft', ['Simulated readings suggest this is not an emergency.',
    'Simulated readings suggest you should wait and see.',
    'Simulated symptoms are probably stress.',
    'Simulated readings suggest seeking help only if symptoms persist.'])
def test_emergency_draft_cannot_weaken_the_immediate_action(draft):
    e = sample(dict(status='reported', selected=['chest_pressure']))
    e['guidance'] = make_guidance(e)
    assert check_draft(draft, e) == 'The draft weakened the immediate emergency guidance.'


def test_reported_symptoms_and_guidance_reach_the_same_frozen_llm_and_jeff_evidence():
    llm, jeff = FakeLLM(draft='Simulated cough and feeling feverish could fit a respiratory infection.'), FakeJeff()
    service = DecisionSupportService(lambda: ('TEST', 'P01'), jeff=jeff, llm=llm)
    try:
        symptoms = dict(status='reported', selected=['cough', 'feverish'])
        job = service.submit('Interpret the latest readings.', sample(), symptoms)
        symptoms['selected'].clear()
        service.work.join()
        result = service.get(job['id'])
        assert llm.calls[0]['clinical_context']['selected'] == ['cough', 'feverish']
        assert llm.calls[0]['guidance']['possible_explanations'] == result['assessment']['possible_explanations']
        assert result['status'] == 'complete'
    finally:
        service.close()
