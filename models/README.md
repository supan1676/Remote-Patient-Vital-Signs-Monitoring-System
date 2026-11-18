# Trained models

The project now also includes a **green/yellow/red alert-priority classifier**,
trained on one million generated one-minute scenarios. Its held-out synthetic
macro-F1 is 0.999202, measuring agreement with invented engineering rules rather
than clinical accuracy. See [its model card](ALERT_PRIORITY_MODEL.md) and
[interactive synthetic demo](alert_priority.demo.html). The dashboard loads it
automatically and displays Unknown when evidence is insufficient.

## PPG signal-quality model

`ppg_quality.joblib` was trained in this workspace from the public
[BUT PPG v2 dataset](https://physionet.org/content/butppg/2.0.0/).
Dataset attribution: Nemcova et al. (2024), BUT PPG version 2.0.0,
doi:10.13026/tn53-8153, CC BY 4.0.

The model is a Random Forest using 11 red-channel waveform features. Training
uses complete ten-second clips, resampled from 30 to 25 Hz. The source has both
transposed single-channel WFDB headers and RGB recordings; the loader handles
both explicitly and selects red from RGB. Features normalize DC polarity for
the inverted camera records. No synthetic training examples or patient illness
labels are used.

There are 3,888 clips from 50 people: 30 training participants (2,184 clips),
10 validation participants (714 clips), and 10 test participants (990 clips).
Tree depth is selected using validation macro-F1. Test participants are excluded
from fitting and depth selection. The random seeds, IDs, class counts,
hyperparameters, hashes and results are saved in `ppg_quality.report.json`.

| Test measure | Result |
|---|---:|
| Macro-F1 | 0.635 |
| Majority-class baseline macro-F1 | 0.456 |
| Unreliable clips mistakenly accepted | 89 / 830 (10.7%) |
| Usable clips accepted | 59 / 160 (36.9%) |
| Total readings retained | 148 / 990 (14.9%) |

The majority class is unreliable, so overall accuracy is not a sufficient
summary. These results support a first research comparison; sensitivity to usable
signals is limited. They do not establish performance on MAX30102, the accuracy
of HR/SpO2, or calibrated clinical probabilities. Host inference is deliberately
in shadow/comparison mode and cannot suppress manual SOS.

Artifacts:

- `ppg_quality.joblib`: bundled trained weights and feature contract.
- `ppg_quality.report.json`: metrics, provenance and participant split manifest.
- `ppg_quality.test.csv`: all held-out predictions.
- `ppg_quality.confusion.png`: standalone confusion-matrix figure.

Run from the project root:

```bash
.venv/bin/python -m ml.download_butppg
.venv/bin/python -m ml.train_quality --butppg data/butppg
```

Only load model artifacts you generated or trust. Retrain the same pipeline
using the independently reviewed local captures described in
[YOU_DO_NEXT.md](../YOU_DO_NEXT.md) before drawing conclusions about this node.
