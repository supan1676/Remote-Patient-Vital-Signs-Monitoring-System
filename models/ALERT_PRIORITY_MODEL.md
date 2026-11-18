# Synthetic alert-priority model

This is a trained gradient-boosted tree classifier that assigns green, yellow or
red **alert priority under an invented engineering rulebook**. It does not
predict illness, diagnose a condition or establish that someone is medically
safe. Labels have not been reviewed by a clinician. The earlier PPG quality
Random Forest remains a separate model.

## What was generated and trained

Generation produced 1,000,000 sixty-second scenarios: 60,000,000 time points,
100,000 artificial profiles and approximately 855 MiB on disk. The seed is
20261111. There are fourteen scenario patterns including activity, falling
oxygen, pulse changes, recovery, brief disturbances, boundary cases, missing
measurements and poor optical quality. Correlations and noise are simulated;
these are not recordings from people or evidence of physiological realism.

The input is a rolling minute of heart rate, SpO2, movement magnitude and optical
usability. Twenty-seven features describe current values, ranges, trends,
coverage and persistence. Profile IDs, scenario types, labels and split IDs are
excluded from model inputs. Temperature is excluded: the installed TMP117 is
not a validated core-temperature measurement.

| Split | Generated scenarios | Eligible for three-color training/evaluation |
|---|---:|---:|
| Training | 700,000 | 586,303 |
| Validation | 150,000 | 125,864 |
| Test | 150,000 | 125,539 |

Profiles are disjoint across splits. Trajectory families are also disjoint:
linear/step/plateau/oscillating for training, sigmoid/exponential for validation,
and staircase/late-transition for testing. This reduces reuse of generator
templates across splits, but all splits still share the invented labeling
policy. It is not external or real-person validation.

The estimator is scikit-learn `HistGradientBoostingClassifier`: 150 boosting
iterations, 31 leaves per tree, learning rate 0.1, balanced class weights,
L2 regularization 1 and seed 42. Training took approximately 21 seconds here.

## Results and their meaning

| Held-out synthetic test measure | Result |
|---|---:|
| Macro-F1 | 0.999202 |
| Accuracy | 0.999132 |
| Majority-class baseline macro-F1 | 0.201749 |
| Exact generating-rule baseline macro-F1 | 1.000000 |

There were 109 mismatches among 125,539 eligible test scenarios: 31 green cases
were predicted yellow and 78 yellow cases green. All 31,916 rule-labeled red
examples were predicted red in this test. That does not guarantee future red
recall. The high scores measure imitation of the generated rules, **not clinical
accuracy**. Directly applying those rules is a simpler exact baseline for this
synthetic task; the model is useful here as a reproducible training experiment.

Validation macro-F1 was 0.998010 with 10,000 training examples, 0.999061 with
100,000 and 0.998991 with all 586,303 eligible training examples. Additional
copies of similar simulated cases have diminishing value. Better labels and
independent real-world evaluation matter more than increasing the row count.

## Runtime behavior

The bridge automatically loads `models/alert_priority.joblib` and performs
inference in a bounded background worker. The dashboard displays synthetic
training provenance. It needs a complete one-minute window, at least 90% usable
observations and valid last-three-second readings. Current unreliable readings,
disconnection, absent weights or a fresh enrollment/history return **Unknown**.
Unknown is a deterministic evidence gate, not a fourth learned class.

Manual SOS and reported falls produce red immediately and independently of
model availability. The existing incident workflow remains responsible for
acknowledgment and resolution. PPG quality can withhold an unreliable input;
this does not certify the accuracy of readings it accepts. Missing movement
stays missing and is treated conservatively for pulse thresholds. Model class
scores are not calibrated probabilities of illness or safety.

The exact labeling assumptions and units are in
[the policy document](../management/SYNTHETIC_PRIORITY_POLICY.md).

## Inspect or reproduce

- [Interactive held-out scenario demo](alert_priority.demo.html): twelve
  explicitly synthetic examples with traces, including Unknown and model errors.
- [Evaluation figure](alert_priority.evaluation.png): confusion matrix and
  validation learning curve.
- `alert_priority.report.json`: metrics, splits, parameters, provenance and hashes.
- `alert_priority.test.csv`: all eligible test predictions.
- `alert_priority.joblib`: trained estimator, feature contract and metadata.
- `../data/synthetic-priority-v1/manifest.json`: dataset schema, counts and hashes.

From the repository root, with the development requirements installed:

```bash
.venv/bin/python -m ml.generate_priority --output data/synthetic-priority-v1 --scenarios 1000000
.venv/bin/python -m ml.train_priority --dataset data/synthetic-priority-v1
.venv/bin/python -m ml.priority_demo
.venv/bin/python telemetry_bridge.py --serial-port PORT
```

The data and weights already exist in this workspace. Generation refuses to
overwrite an existing dataset; use a new output directory for another run and
point training at it. Bulk data and model binaries are ignored by Git. Only
load model artifacts you generated or trust. No GPU or paid API was required.

For a claim about actual patient risk, the remaining human work is clinical
review of the intended population and labels, genuine appropriately obtained
recordings, and independent evaluation against a relevant reference. The current
artifact should be presented as a synthetic alert-priority prototype.
