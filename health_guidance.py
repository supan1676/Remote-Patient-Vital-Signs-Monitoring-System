"""Conservative symptom-aware prototype guidance, separate from learned alert colors.

This selects general educational information; it is not a validated triage tool
or a disease classifier. The LLM may explain these bounded possibilities only.
"""
import math

DISCLAIMER = ('This is not a final medical evaluation or diagnosis. '
              'Consult a qualified healthcare professional for assessment.')
SYMPTOMS = {
    'cough': 'Cough', 'feverish': 'Feeling feverish (reported, not measured)',
    'breathless': 'New or worse shortness of breath', 'palpitations': 'Racing or irregular heartbeat sensation',
    'very_unwell': 'Feeling very unwell or worsening',
    'severe_breathing': 'Severe breathing difficulty / unable to speak normally',
    'chest_pressure': 'Tight or heavy chest', 'confusion': 'Sudden confusion',
    'blue_lips': 'Blue or grey lips or skin',
}
EMERGENCY = {'severe_breathing', 'chest_pressure', 'confusion', 'blue_lips'}
SOURCES = {
    'breathing': {'title': 'NHS: shortness of breath', 'url': 'https://www.nhs.uk/symptoms/shortness-of-breath/'},
    'palpitations': {'title': 'NHS: heart palpitations', 'url': 'https://www.nhs.uk/symptoms/heart-palpitations/'},
    'infection': {'title': 'NHS: chest infection', 'url': 'https://www.nhs.uk/conditions/chest-infection/'},
    'oximetry': {'title': 'FDA: interpreting pulse-oximeter readings',
                 'url': 'https://www.fda.gov/medical-devices/products-and-medical-procedures/pulse-oximeters'},
}


def validate_symptoms(value=None):
    if value is None:
        return dict(status='unknown', selected=[])
    if not isinstance(value, dict) or set(value) - {'status', 'selected'}:
        raise ValueError('Send a symptom status and a list of selected symptoms.')
    status, selected = value.get('status'), value.get('selected')
    if status not in ('unknown', 'none_reported', 'reported'):
        raise ValueError('Choose whether symptoms were asked about.')
    if (not isinstance(selected, list) or len(selected) > len(SYMPTOMS)
            or any(not isinstance(s, str) or s not in SYMPTOMS for s in selected)
            or len(set(selected)) != len(selected)):
        raise ValueError('Select symptoms from the supplied list.')
    if status != 'reported' and selected:
        raise ValueError('Selected symptoms require the symptoms-reported option.')
    if status == 'reported' and not selected:
        raise ValueError('Select at least one reported symptom.')
    return dict(status=status, selected=sorted(selected))


def clinical_context(value=None):
    symptoms = validate_symptoms(value)
    return dict(**symptoms, descriptions=[SYMPTOMS[s] for s in symptoms['selected']],
                source='Reported by the user for this request; not detected by a sensor.')


def make_guidance(evidence):
    context = evidence.get('clinical_context') or clinical_context()
    selected = set(context['selected'])
    measurements = evidence.get('measurements', {})
    def value(name):
        m = measurements.get(name, {})
        v = m.get('value')
        return v if (m.get('status') == 'valid' and isinstance(v, (int, float))
                     and not isinstance(v, bool) and math.isfinite(v)) else None
    hr, oxygen = value('heart_rate'), value('spo2')
    optical = evidence.get('optical', {})
    usable = optical.get('label') != 'unreliable' and hr is not None and oxygen is not None
    # Engineering review prompts; these cutoffs do not diagnose disease or
    # independently establish a clinical emergency on this unvalidated sensor.
    low_oxygen = usable and oxygen < 95
    unusual_pulse = usable and (hr < 50 or hr > 120)
    emergency = bool(selected & EMERGENCY) or {'palpitations', 'breathless'} <= selected
    device_alarm = any(evidence.get('device_alerts', {}).values())
    explanations, source_keys = [], {'oximetry'}
    if selected & {'cough', 'feverish', 'breathless'}:
        source_keys.update(('breathing', 'infection'))
        if 'cough' in selected and selected & {'feverish', 'breathless'}:
            explanations.append('A respiratory infection is one possible explanation for this symptom combination; the readings cannot confirm an infection or its cause.')
        if 'breathless' in selected:
            explanations.append('Breathlessness can have several causes, including an airway problem such as asthma or a chest infection. Assessment is needed to distinguish them.')
    if 'palpitations' in selected:
        source_keys.add('palpitations')
        explanations.append('Palpitations can occur with activity, stress or caffeine, but a heart-rhythm problem is also possible. Pulse readings alone cannot distinguish these causes.')
    if low_oxygen:
        explanations.append('A lower oxygen estimate can reflect a breathing problem or an inaccurate sensor reading. Confirm it with reliable equipment and assess how the person feels.')
    if unusual_pulse and 'palpitations' not in selected:
        explanations.append('An unusual pulse estimate can have several explanations, including activity or a measurement problem. The cause cannot be inferred from this short recording.')
    if not explanations:
        explanations.append('These inputs do not support naming a particular illness. Symptoms and clinical history are needed even when the displayed pulse and oxygen look unremarkable.')
    if emergency:
        level, title = 'emergency', 'Seek emergency help now'
        explanations = ['The cause cannot be established here. Emergency assessment is needed before considering possible explanations; do not assume a less serious cause.']
        reason = 'The reported symptom combination includes an emergency warning sign, regardless of the displayed readings or alert color.'
        action = 'Call your local emergency number or obtain emergency medical care now. Do not wait for the AI explanation or drive yourself.'
        source_keys.add('breathing')
        if 'palpitations' in selected:
            source_keys.add('palpitations')
    elif device_alarm:
        level, title = 'check_now', 'Check on the person now'
        reason = 'A device SOS or fall alert needs a direct check; it does not identify an illness.'
        action = 'Check the person immediately. Obtain emergency help for severe symptoms or injury; seek prompt medical advice if the situation is uncertain.'
    elif 'breathless' in selected or 'very_unwell' in selected:
        level, title = 'prompt_review', 'Seek prompt medical assessment'
        reason = 'New breathing difficulty or feeling very unwell warrants assessment even if the displayed readings look normal.'
        action = 'Contact a healthcare professional or local urgent-care service promptly. If breathing becomes severe or other emergency signs appear, seek emergency help.'
        source_keys.update(('breathing', 'infection'))
    elif low_oxygen or unusual_pulse:
        level, title = 'confirm_and_review', 'Confirm the readings and contact a clinician'
        reason = 'A concerning measurement pattern is present, but the prototype cannot establish its cause or accuracy.'
        action = 'Repeat the measurement with a validated device and contact a healthcare professional about readings that stay unusual. If the person feels unwell, seek advice without waiting for another reading.'
    elif not usable:
        level, title = 'insufficient_evidence', 'The readings cannot determine whether a visit is needed'
        reason = 'Pulse or oxygen is missing or unreliable; absence of a valid reading is not a reassuring finding.'
        action = 'Check sensor contact and obtain a reliable measurement. Contact a healthcare professional if symptoms are concerning, persistent or worsening.'
    elif context['status'] == 'reported':
        level, title = 'symptom_review', 'Arrange a medical review if symptoms persist or recur'
        reason = 'Symptoms can matter even when pulse and oxygen estimates look unremarkable.'
        action = 'Arrange a clinician review for persistent, recurrent or worsening symptoms. Seek earlier help if you are worried or have an existing medical condition.'
    elif context['status'] == 'unknown':
        level, title = 'symptoms_needed', 'Ask about symptoms before deciding on a visit'
        reason = 'The current measurements do not identify a particular illness; symptoms have not been supplied.'
        action = 'Ask how the person feels and add symptoms below. Concerning or worsening symptoms should prompt medical advice even with a green alert.'
    else:
        level, title = 'observe', 'Continue observing; seek advice if concerns develop'
        reason = 'No concerning pulse/oxygen pattern was identified in this limited snapshot and no symptoms were reported. This does not establish medical safety.'
        action = 'Keep monitoring how the person feels. A clinician review is appropriate if symptoms develop, recur or cause concern; these readings cannot rule out illness.'
    if 'palpitations' in selected and level not in ('emergency', 'check_now'):
        action += ' If palpitations do not settle, or are accompanied by chest pain, breathlessness or feeling faint, seek emergency help.'
    return dict(version='symptom-guidance-v1', level=level, title=title, reason=reason, action=action,
        possible_explanations=explanations, disclaimer=DISCLAIMER,
        missing_information=['Age, medical history, medicines, symptom duration and a validated examination are not available.',
                             'Feeling feverish is a reported symptom; core temperature is not measured.'],
        sources=[SOURCES[k] for k in sorted(source_keys)],
        provenance='General guidance selected by explicit prototype rules from the linked sources; not a trained disease or triage model.',
        simulation=evidence.get('simulation') is True)
