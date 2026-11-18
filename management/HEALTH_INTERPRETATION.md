# Symptom-aware interpretation — prototype scope

The dashboard's **Health interpretation** panel now addresses what the pattern
could mean and whether medical review should be considered. Repeating sensor
values is not the main output. The existing trained alert-color model is still
separate and remains trained on synthetic engineering labels, not disease labels.

## Input and output

The reviewer explicitly selects **Not yet asked**, **No symptoms reported**, or
**Symptoms reported**, then selects relevant symptoms. Feeling feverish is a
reported symptom, not a measured fever. The TMP117 still supplies no validated
core-temperature measurement. No symptoms are inferred from missing inputs.

The main output includes a next-step action and a generated AI explanation.
Reasons, reference possibilities, missing information, sources and model decisions
are available under **Evidence and sources**. With no symptoms and ordinary
readings, the system does not invent a disease. For reported cough plus feeling
feverish, a respiratory infection can be listed as one possibility, with an
explicit statement that the recording cannot confirm it. Conditions are not
assigned probabilities or represented as the most likely diagnosis.

Every output has the application-supplied notice:

> This is not a final medical evaluation or diagnosis. Consult a qualified
> healthcare professional for assessment.

This notice is independent of the LLM. Simulation provenance is also supplied
by application code rather than relying on generated wording.

## General next-step logic

`health_guidance.py` selects general guidance through explicit prototype rules.
These rules are not a medically validated triage system. They make no claims
about performance across ages, illnesses or settings.

| Input | Displayed response |
|---|---|
| Severe breathing difficulty, tight/heavy chest, sudden confusion, blue/grey lips, or palpitations with breathlessness | Emergency-help guidance regardless of sensor values or color |
| Active SOS/fall | Check the person immediately; the device alert does not identify an illness |
| New/worse breathlessness or feeling very unwell | Prompt clinical assessment, with emergency escalation for severe symptoms |
| A usable oxygen estimate below 95%, or pulse outside 50–120 bpm | Confirm the measurement and contact a healthcare professional about persistent abnormalities |
| Missing/unreliable measurements | Insufficient evidence; assess symptoms and obtain reliable measurements |
| Other reported symptoms | Medical review for persistent, recurring or worsening symptoms |
| No symptom information | Ask about symptoms before deciding about a visit |
| No reported symptoms and no configured concerning measurement pattern | Continue observing; no declaration of medical safety |

The numerical cutoffs are conservative **engineering review prompts**, not
universal clinical thresholds. Movement does not prove rest; exercise and known
medical conditions can change interpretation. No medication or treatment is
selected. Age, medical history, medicines, duration and a clinical examination
remain unavailable. Palpitations advice includes escalation if they do not settle
or occur with chest pain, breathlessness or feeling faint.

The browser shows the severe-symptom warning as soon as a relevant checkbox is
selected, including when the bridge/model is unavailable. The server includes
guidance in the initial job response. Emergency and active-device-alarm cases
also run AI generation in the background; their immediate action is displayed
before inference and remains visible if generation or an evidence check fails.
The checkbox warning is replaced by that action after submission rather than
duplicated. The evaluation notice appears once, beneath the explanation.

## LLM and Jeff roles

Qwen3 1.7B (`qwen3:1.7b`) explains only the supplied findings and bounded possible explanations.
It runs locally with thinking disabled and JSON-schema output. The earlier
configuration used Gemma 2 2B; it is no longer the default. Emergency explanations
describe why the reported warning sign matters without suggesting a benign cause
or making immediate help conditional on symptoms persisting.
It must not invent symptoms, infer a measured fever, recommend treatment, label
a disease probable or alter the separately displayed care recommendation.
Explicit checks still reject unsupported numbers, long time spans and selected
certainty/clinical claims. Jeff checks the draft against the same evidence and
supplied guidance. An accepted draft remains fallible.

Evidence selection uses Jeff's existing `ground.rerank` adapter over concrete
passages (current readings and guidance, trends, quality, incidents, or none).
The earlier tool router often asked for clarification when given interpretation
questions, so it is no longer the main selection path. Jeff's `ground.grounding`
still performs the final learned support check. This is not medical calibration
or validation of the care rules. A failed AI check withholds the prose while the
separately sourced general guidance remains visible.

Selections and results are per-request snapshots. Changing symptoms clears the
previous result; changing enrollment clears symptoms and results. Historical
data remain restricted to the current enrollment. The interpretation panel does
not modify recorded incidents, reviewer notes or the trained model's color.

## Primary sources

These support the general educational statements and symptom escalation advice.
The combination of these statements with prototype measurements is an
engineering implementation, not an official NHS/FDA scoring tool.

- [NHS: shortness of breath](https://www.nhs.uk/symptoms/shortness-of-breath/):
  emergency warning symptoms, prompt assessment for new breathing trouble and
  examples of possible causes. Local emergency wording replaces UK phone numbers.
- [NHS: heart palpitations](https://www.nhs.uk/symptoms/heart-palpitations/):
  possible triggers, recurrence and symptom combinations requiring emergency care.
- [NHS: chest infection](https://www.nhs.uk/conditions/chest-infection/): symptom
  combinations that can occur with infection and when to obtain medical review.
- [FDA: pulse oximeters](https://www.fda.gov/medical-devices/products-and-medical-procedures/pulse-oximeters):
  do not base decisions on an oxygen estimate alone; symptoms and concerns matter.

Verification covers symptom/input validation, severe-symptom overrides despite
green readings, absent data, symptom freezing, unsupported certainty, and
application-supplied disclosures. The actual-model simulator check is
`python -m ml.check_interpretation`; it records results under ignored `data/`.
These software checks do not establish clinical accuracy.

The final desktop/mobile browser run exercised four real Qwen3 explanations
(cough with feeling feverish, then those symptoms with chest pressure, on each
viewport). All four completed and passed the Jeff support check. Immediate
emergency guidance appeared before inference, evidence stayed collapsed, one
evaluation notice was visible, and changing symptoms cleared the old result.
Screenshots and exact request/output metadata are saved under ignored
`data/verification-health-qwen-2026-11-11/`. These are functional checks, not a
medical-domain accuracy evaluation; generation and grounding remain fallible.
