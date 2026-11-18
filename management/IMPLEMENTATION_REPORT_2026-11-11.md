# Implemented software and remaining physical work — 2026-11-11

Implemented and checked locally; no commit, push, public deployment or device
upload was performed. The device scan contained no identifiable USB ESP32.
Follow [YOU_DO_NEXT.md](../YOU_DO_NEXT.md) for the physical and labeling steps.

## Completed

- Generated 1,000,000 synthetic one-minute HR/SpO2/movement scenarios across
  100,000 artificial profiles; trained a three-color histogram gradient-boosting
  alert-priority model with disjoint profiles and trajectory families per split.
  Held-out synthetic macro-F1 is 0.999202, measuring agreement with unreviewed
  engineering rules, not medical accuracy. The exact generating-rule baseline
  scores 1.0 by construction. [Model card](../models/ALERT_PRIORITY_MODEL.md).
- Integrated the priority worker, `/api/priority`, a dashboard panel with
  synthetic-training disclosure, insufficient-evidence Unknown and independent
  SOS/fall red override. Added an offline interactive held-out scenario demo;
  generated demo data are not mixed into production patient records.
- Integrated local Qwen3 1.7B explanations and actual Jeff v1.4 routing/grounding
  adapters. Jeff runs in a separate CPU environment/process; summary jobs use
  captured evidence and never block sensor ingestion. Added deterministic
  simulation labeling, numeric/time-span checks and enrollment-bound history.
  [Implementation and setup](JEFF_LLM_INTEGRATION.md).
- Replaced number-reciting summaries with symptom-aware **Health interpretation**:
  bounded possible explanations, general medical-review guidance, sources and a
  single not-final-evaluation notice. Severe-symptom warnings are immediate,
  with AI explanations generated in the background. Reference details and sources
  are collapsed under Evidence and sources. Jeff ranks actual evidence passages for interpretation
  requests. [Scope and primary sources](HEALTH_INTERPRETATION.md).
- Firmware `rpm-2.2.0`: raw red/IR batches at the effective 25 Hz output rate,
  boot identity, sequence numbers, FIFO-estimated sample timestamps and explicit
  dropped-sample counts. Raw output is skipped if the UART cannot accept the
  whole batch, preserving acquisition priority.
- TMP117 first-conversion wait serviced by the loop; MPU recovery calibration
  collected incrementally instead of blocking the runtime loop for seconds.
  Startup calibration remains stationary and blocking before normal operation.
- Defensive packet size/depth/integer checks and contained parsing failures.
  Sensor age checks mask old readings without discarding SOS/fall flags.
- Optical recording and inference in a bounded background worker, with
  continuity checks across timestamps, sequences, devices and reboots.
- A Random Forest trained from scratch on BUT PPG v2; participant-separated
  training, validation-based depth selection and final held-out evaluation.
  Results and limitations: [model card](../models/README.md).
- Real-recording extraction, standalone browser annotation, exclusion of
  uncertain labels, local retraining, split manifests, saved weights, per-clip
  predictions and a standalone confusion-matrix figure.
- Dashboard optical traces and model result, with explicit public-data domain
  and comparison-mode disclosure. Predictions do not change measured values.
- Persistent local incidents with acknowledge/resolve transitions and review
  notes stored against the active enrollment. Old browser notes remain in
  browser storage; no uncertain identity migration was attempted.
- Optional remote HTTP binding requires HTTPS and a password of at least 16
  characters. Localhost remains the default. Credentials and certificates must
  be supplied for any remote deployment.
- Pinned Python/direct firmware dependencies and CI for host checks plus main
  and diagnostic builds. The verified platform is Espressif32 7.1.1, Arduino
  core 2.0.17, PlatformIO 6.2.0.

## Verification

| Check | Result |
|---|---|
| Python regression and real HTTP integration suite | 134 passed, five subtests passed; focused guidance/orchestration tests also pass after the final prompt changes |
| Dashboard core suite | 10 passed |
| Python compilation, JS syntax, Git whitespace checks | Passed |
| Main firmware | Built; 327,521 flash bytes, 23,904 static RAM bytes |
| TMP117 raw diagnostic | Built |
| TMP117/MAX default diagnostic and three explicit stages | All four built |
| Browser at 1440×1100 and 390×844 | Waveform, incident acknowledgement, persisted review, no horizontal overflow or JS errors |
| Priority browser at 1440×1000 and 390×844 | Three colors and API, bad quality/disconnect Unknown, SOS override, interactive offline demo; no JS errors or overflow |
| Actual-model assistant browser at 1440×1000 and 390×844 | Generated supported drafts, simulation disclosure, valid capture time and expandable evidence; no JS errors or overflow |
| Symptom-aware browser at 1440×1000 and 390×844 | Four actual Qwen explanations accepted by Jeff, including emergency symptoms on both viewports; immediate action before inference, one evaluation notice, collapsed evidence/sources, old results cleared and no overflow or JS errors |
| Impeccable mechanical detector | No findings |
| Unprotected remote-bind attempt | Refused before opening a listening socket |
| Live hardware, reference accuracy, SOS switch and on-device timing | Not run; no USB ESP32 available |

Browser checks used a separate in-memory server and clearly synthetic test
fixtures. They did not insert demonstration measurements into the application
database. Screenshots and check metadata are in ignored
`data/verification-2026-11-11/`. Public training data are under ignored
`data/butppg/`; generated weights are `models/ppg_quality.joblib`, also ignored
by Git. Reports and prediction CSVs remain reviewable source artifacts.
Synthetic priority data are under `data/synthetic-priority-v1/` (about 855 MiB),
weights at `models/alert_priority.joblib`, and priority browser artifacts at
`data/verification-priority-2026-11-11/`. Data and binary weights are ignored by
Git. Scripts, model cards, metrics and reports remain reviewable.

The public model test macro-F1 is 0.635, versus 0.456 for its majority baseline.
It accepts 89/830 unreliable clips and 59/160 usable clips. These are research
results on smartphone PPG, with limited usable-signal recall. They do not
establish local sensor accuracy or calibrated clinical probabilities. No local
training labels, reference readings or hardware results have been invented.

## Remaining dependencies

The team must connect/flash the board, repair/check wiring, compare measurements
with reference equipment, and collect and independently label local recordings.
Recorded incidents persist after the bridge receives them; events that happen
entirely while disconnected are not uploaded later by this firmware.

Jeff and local Qwen3 1.7B are connected; their setup is documented separately.
The sensor models still operate independently and expose structured outputs at
`/api/optical` and `/api/priority`. Broader medical-domain evaluation is not done.
Remote hosting, certificate issuance and network configuration remain separate
from the implemented optional HTTPS server. There is no multi-user cloud service
or device-side offline upload queue in this change.
