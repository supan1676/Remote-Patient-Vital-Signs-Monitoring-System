# Synthetic alert policy v1

Policy ID: `engineering-alert-policy-v1`. Source of truth:
`alert_priority.py::policy_labels`. These are unreviewed engineering assumptions
for a classroom training demonstration. They are not a medical scoring standard,
clinical advice, a diagnosis, or labels supplied by an expert.

## Evidence gate

Each example contains sixty one-second observations. Optical usability must be
true and HR must be finite within 20–250 bpm and SpO2 finite within (0, 100] %
for an observation to be counted. A full window, at least 54 usable observations
and three usable final observations are required. Otherwise the output is
Unknown. Runtime additionally checks current sensor status, finger contact,
optical quality and freshness. No previous green survives a disconnected or
currently unreliable input.

Movement is acceleration magnitude in g. The pulse rules use a rest-or-unknown
condition when magnitude is unavailable or its absolute difference from 1 g is
less than 0.12 g. This heuristic is not a validated activity classifier and
absence of movement data does not establish rest. Motion coverage is recorded
as an input feature rather than replacing missing values with a normal value.

## Label precedence: red, then yellow, then green

For eligible windows, any one of these conditions generates **red**:

| Condition at the end of the minute | Consecutive duration |
|---|---:|
| SpO2 ≤90% | ≥10 seconds |
| HR ≤40 bpm | ≥10 seconds |
| HR ≥140 bpm with rest-or-unknown movement | ≥15 seconds |
| HR ≥190 bpm regardless of movement | ≥15 seconds |
| SpO2 <93% and HR >120 bpm with rest-or-unknown movement | ≥20 seconds |

Otherwise, any one of these generates **yellow**:

- Current SpO2 <95%.
- Current HR <50 bpm, or >120 bpm with rest-or-unknown movement.
- At least 20% of usable observations in the last 30 seconds have SpO2 <95%.
- At least 20% of usable observations in the last 30 seconds have HR <50 bpm,
  or HR >120 bpm with rest-or-unknown movement.
- Mean SpO2 in the final ten seconds is at least three percentage points below
  the first ten seconds, and current SpO2 <96%.
- Mean HR in the final ten seconds is at least 25 bpm above the first ten
  seconds, current HR ≥100 bpm and current movement is rest-or-unknown.

Other eligible windows generate **green**: no configured concerning pattern in
the available signals. Green does not mean the person is medically safe.
Missing-data Unknowns are excluded from fitting the three-color model.

At runtime, SOS or a reported fall overrides the model with red immediately,
even without a minute of data. The API labels this source `device_alert` rather
than `trained_model` so a manual/device alarm is not attributed to AI.

## Deliberate scope

There is no core-temperature, respiratory-rate, blood-pressure, consciousness,
supplemental-oxygen, symptoms or known-condition input. The current TMP117
package temperature must not be interpreted as core temperature. The model is
not NEWS2: that standard uses additional physiological parameters and defined
clinical procedures; see the [Royal College of Physicians NEWS2 resource](https://rcp.ac.uk/resources/national-early-warning-score-news-2/).
The thresholds and durations above have not been validated for children,
chronic hypoxemia, pregnancy, altitude, exercise or any other patient population.

Synthetic benchmark scores test whether the classifier reproduces this policy.
The policy itself is an exact baseline and scores perfectly by construction.
Real-person outcome prediction would require a different label source and an
appropriate independent evaluation. Adding more simulated rows cannot establish
that validity.
