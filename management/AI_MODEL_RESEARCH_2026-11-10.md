# Project improvements and self-trained AI recommendation — 2026-11-10

Recommendation for the clarified **one-week deadline**: build a **Random Forest
PPG signal-quality classifier**, with a small 1D-CNN as an optional comparison
or the main model if the teacher specifically requires a neural network.
Its purpose is to identify unreliable
optical windows before their heart-rate estimates reach the dashboard and
downstream decision system. This addresses an observed project problem and can
operate without the currently offline MPU. A fall/activity classifier is the
best alternative once the IMU works reliably and body placement is fixed.

This recommendation is an engineering judgment based on the code and primary
sources below. No model was trained and no new physical measurements were made
for this note. “Jeff” refers only to the user's description of their planned
option-scoring model; its exact implementation has not been identified.

## Current project assessment and engineering priorities

The reviewed checkout was `362dd31`. Fresh checks on 2026-11-10 passed:
`python -m pytest -q` (66 tests, five subtests) and
`node tests/dashboard_core.test.js` (10 tests). Isolated parser probes used
synthetic test fixtures and did not touch a device or the live database.
Firmware was reviewed but not rebuilt or uploaded in this analysis. Physical
status below comes from the recorded November 3 evidence, not a new bench test.

The existing strengths are strict status/value validation, explicit missing
measurements, separate sensor/wrist/core temperature meanings, SQLite history,
gap-aware charts, per-person baselines, and automated contract tests. Preserve
these while adding ML. The baseline already permits individual metrics to become
ready; the README's all-or-nothing description is outdated. Its wrist metric
cannot qualify while contact remains unverified.

| Priority | Evidence in this checkout | Recommended improvement |
|---|---|---|
| This week: measurement reliability | The latest optical report shows transported values without reference accuracy validation; the MPU was offline. | Stabilize sensor mounting and acquisition, check optical readings against an available reference, and train the quality classifier on complete recordings. Treat MPU repair as a prerequisite to a fall-model demo. |
| This week: continuous acquisition | `initTmp117()` in [main.cpp](../src/main.cpp) waits 600 ms. The repair report documents a recovery pause resetting optical acquisition. | Make conversion/retry waits nonblocking; record sample gaps and sequence numbers. Batch raw samples without recreating the UART starvation fault. |
| This week: bridge resilience | [_number and parse_packet](../telemetry_bridge.py) raised `OverflowError` for a fixture with `uptime_s = 10**400` and `RecursionError` for deeply nested JSON. The serial worker catches neither exception. | Bound packet complexity and numeric values, reject invalid packets without terminating acquisition, and test recovery with the next valid packet. |
| This week: sample freshness | A synthetic valid packet at uptime 1,000 s with TMP117 sample timestamp 1 ms was accepted. Arrival freshness is checked, but sensor timestamp age is not independently enforced. | Define sample-age bounds with boot identity and wrap handling; preserve acquisition timestamps through raw logging and inference. |
| This week: a measurable AI demonstration | Once-per-second raw optical scalars are stored, but full waveforms, labels and model artifacts are absent. | Add a reproducible training pipeline, recorded-data replay, model/version metadata, and a dashboard waveform plus quality result. Retain rejected raw data for analysis while keeping invalid clinical values null. |
| Next: caregiver workflow | [Firmware](../src/main.cpp) clears fall indication after six seconds and SOS after 15 seconds; the backend logs events, but there is no caregiver acknowledgement workflow. [Review notes](../assets/dashboard.js) live in browser local storage. | Keep backend incident state until acknowledged/resolved, preserve who acted and when, and store review notes against the enrollment on the backend. Keep the manual SOS path independent of learned judgments. |
| Next: remote operation | [The bridge](../telemetry_bridge.py) reads USB serial and binds HTTP to `127.0.0.1`. It has no implemented internet monitoring path. | Add an authenticated gateway/service with encrypted transport, device identity, reconnection and queued uploads. Keep the working serial path as a diagnostic fallback. |
| Supporting work: maintainability | Firmware combines acquisition, telemetry and display in one large file; Python dependencies lack a project manifest; PlatformIO versions float; evidence documents disagree. | Pin a working environment, add CI for current tests/builds, reconcile the current-state document, and separate acquisition, serialization and inference as those components are changed. |

Run ML, Jeff and any LLM work through bounded background processing so slow
inference cannot stall serial ingestion. The current `ai_decision_engine.py`
is a separate serial consumer; integrate new inference beside the bridge's
single serial owner. Keep window timestamps and expiry with each result so a
late prediction cannot be applied to a newer reading. These improvements are a
prioritized roadmap; the one-week deliverable below does not assume all of them
will be completed.

## Why this fits the current project

The [latest MAX30102 repair report](../MAX30102_FIX_REPORT_2026-11-03.md)
records successful optical display and persistence, but algorithm-valid estimates
of **31–214 bpm and 3–100% SpO2** during placement/removal, without reference
validation. It also records the MPU offline. This is newer evidence than the
README's general unverified-hardware status.

[Firmware](../src/main.cpp) currently feeds a 100-sample optical window at an
effective 25 Hz, with red and infrared channels. IMU reads are scheduled every
20 ms when available. The roughly once-per-second telemetry contains recent
optical and IMU snapshots. [SQLite](../telemetry_store.py) stores optical raw
scalar snapshots, but neither those snapshots nor the dashboard history preserve
the complete optical waveform or six-axis IMU time series. **Add a raw-data
recording mode before attempting waveform training.**

The existing [decision engine](../ai_decision_engine.py) implements rules; naming
it AI does not demonstrate model training. A trained waveform classifier has a
distinct role: sensor evidence → learned quality/movement class → structured
input for the planned option scorer → optional LLM explanation. Preserve
deterministic sensor-error handling and the independent SOS path.

## Options compared

| Model | What the team trains | Useful demonstration | Main dependency | Ranking |
|---|---|---|---|---|
| PPG quality classifier | Random Forest on signal features; optional small 1D-CNN on red/IR windows | Recognize unusable pulse waveforms during movement/contact changes; request a repeat reading | Full-rate logging, independently assigned quality labels, test subjects using this hardware | Best fit to the failure and one-week deadline |
| Fall/activity classifier | Small 1D-CNN on acceleration/rotation; Random Forest baseline | Distinguish a fall candidate from ordinary movement | Repair MPU, choose fixed placement, collect full-rate six-axis data | Best event-recognition alternative |
| Personal anomaly detector | Isolation Forest, optionally a small autoencoder, fitted to good-quality personal history | Flag deviation from the person's usual pattern | Several days of representative, trustworthy data and evidence for evaluating alerts | Later extension |

Anomaly detection learns what differs from its training distribution; it does
not establish illness. Scikit-learn distinguishes outlier detection from
novelty detection depending on the training assumptions. Use time-separated
future evaluation for a personal model, and compare it with the existing robust
baseline. Do not manufacture missing wrist temperature to enable training.
([Official anomaly-detection guide](https://scikit-learn.org/stable/modules/outlier_detection.html))

A Random Forest is a trained supervised ML model: it fits decision trees from
examples. It is valid evidence of training, although a teacher may specifically
expect a neural network. A CNN comparison is useful if time permits; the CNN
should not automatically be declared better. No accuracy or successful live
validation is guaranteed within a week.
([Official RandomForestClassifier documentation](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestClassifier.html))

## Dataset choices and their limits

| Dataset | Verified contents and access | Fit and limitations |
|---|---|---|
| [BUT PPG v2, PhysioNet](https://physionet.org/content/butppg/2.0.0/) | 3,888 ten-second smartphone PPG recordings from 50 people, 30 Hz, ECG reference and binary good/poor quality labels; open access, CC BY 4.0 | Useful labeled quality benchmark. Finger/ear camera measurements differ from MAX30102 photodiodes and red/IR LEDs. Labels concern HR usability, not SpO2 accuracy. Train on whole labeled clips; a poor ten-second clip does not prove every shorter crop is poor. |
| [PPG-DaLiA, UCI](https://archive.ics.uci.edu/dataset/495/ppg%2Bdalia) | 15 subjects; wrist BVP 64 Hz and acceleration 32 Hz; chest ECG supplies HR ground truth; download offered under CC BY 4.0 | Intended for HR estimation and motion compensation. Native HR/activity labels are not independent signal-quality labels. Useful later for motion-aware HR experiments, not a ready-made clean/noisy dataset. |
| [SisFall original paper](https://www.mdpi.com/1424-8220/17/1/198) | Waist-mounted acceleration and gyroscope at 200 Hz; 19 ADL types and 15 fall types; 38 participants. Authors link raw text recordings and README. | Suitable when deployment placement matches. Most older participants performed ADLs only; one older judo expert also simulated falls. Controlled falls do not establish performance on real elderly falls. The linked institutional download timed out during this review; dataset licensing was not independently verified. The article's CC BY license alone is insufficient evidence of the external dataset's terms. |
| [UP-Fall authors' site](https://sites.google.com/up.edu.mx/har-up/) and [original paper](https://www.mdpi.com/1424-8220/19/9/1988) | 17 young adults, six ADLs and five simulated fall types; IMUs include wrist and waist. Original IMU acquisition was 100 Hz, but the published consolidated dataset is approximately 18.4 Hz. The site documents downloads and missing trials. | Select the intended wearable location and only channels actually available on this node. Do not train using all body sensors or camera data then deploy with one IMU. Check actual timestamps; upsampling consolidated data cannot recover lost impact detail. No explicit standalone dataset license was confirmed on the authors' page. |

PPG-DaLiA's Empatica E4 reports BVP from an optical system using green and red
LEDs, while this project has MAX30102 red/IR samples. Resampling does not remove
the device/site/wavelength difference. In particular, neither BUT PPG quality
labels nor DaLiA HR targets validate this node's SpO2 estimates.
([Empatica's technical specification](https://box.empatica.com/documentation/20141119_E4_TechSpecs.pdf))

## Achievable PPG model experiment

1. **Record the actual inputs.** Save every red/IR sample with sample sequence,
   acquisition time, measured sampling rate, sensor configuration, participant
   pseudonym, session, placement and condition. Include no-contact, clipping and
   signal-gap events rather than logging only already-accepted measurements.
   Batch records so serial output cannot starve the optical FIFO again.
2. **Collect and label independently.** A pilot planning target is 8–12 consenting
   adult volunteers, two short sessions each, with steady contact, ordinary hand
   movement and gentle placement/removal. These are targets, not a validated
   minimum dataset size or evidence of population-wide reliability. Label waveform windows as usable/unusable using a
   written rubric and independent review; keep disagreement as uncertain. An
   ECG reference, if the laboratory has one, supports pulse/HR evaluation.
   Without it, restrict the claim to waveform-quality classification. Do not use
   the firmware's current validity flag as the sole ground truth.
3. **Train and compare.** Prioritize the Random Forest for the week. Use
   ten-second windows at the existing effective 25 Hz: 250 samples × 2 optical
   channels, accumulated by the new logger/host buffer. This keeps the initial
   label duration consistent with BUT PPG's ten-second clips; it does not change
   the current firmware's four-second HR calculation. The first quality result
   needs ten seconds of samples; subsequent windows can advance each second.
   Candidate CNN: two or three small Conv1D blocks → global average
   pooling → binary output. Random Forest features can include amplitude/DC
   ratios, clipping, periodicity, spectral concentration and red/IR agreement.
   Compare trained models against today's deterministic quality guard on the same labels.
   Fit preprocessing using training data only; retain amplitude information
   needed for quality detection.
4. **Keep public-data transfer optional.** For the one-week build, prefer matched
   local data and the simple supervised model. A Random Forest trained from
   scratch on BUT PPG is also a valid academic experiment; retrain it on local
   features for the local task, rather than describing this as neural-network
   fine-tuning. Optional later work is a single-channel CNN trained on BUT PPG
   and fine-tuned using the same input configuration on this node's red channel.
   A two-channel red/IR model needs its own matching input/training strategy.
   Do not assume public-data performance
   transfers to this node, or inherit ten-second labels onto arbitrary shorter
   crops without reviewing them.
5. **Hold out people before windowing.** Keep all sessions and overlapping
   windows from each participant on one side of the train/validation/test split.
   Use grouped validation within training participants; reserve final test
   participants for one final evaluation. Report macro-F1, class-wise recall,
   confusion matrix, and especially **bad windows accepted as good**. Also
   report the fraction of readings retained; rejecting everything is not useful.
   Where reference measurements exist, compare HR error before/after gating at
   the reported coverage. Grouped splits address dependence between samples
   from the same person.
   ([Official grouped cross-validation guidance](https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-iterators-for-grouped-data))
6. **Integrate on the host first.** Run inference in Python beside the bridge;
   emit class, score, model version, window time and validity. A high classifier
   score is not automatically a calibrated probability. Initially compare it in
   shadow mode with current behavior before enabling rejection. Bad or uncertain
   windows should prompt a new measurement, not be replaced with invented vital
   signs. A good quality result must not bypass existing sensor/status checks or
   certify SpO2 accuracy.

If fall/activity recognition is chosen instead, train on matching six-axis
windows after unit conversion and appropriate anti-alias filtering. Compare
against the existing free-fall/impact heuristic. Evaluate entire held-out
recordings with sliding windows, reporting event recall, detection latency and
false alerts per hour of ordinary activity. Testing only windows centered on
known impacts gives an unrealistically easy task. Use public simulated falls
and safe ordinary-activity recordings; dropping the board is not a labeled human
fall.

After host validation, a quantized CNN is a possible ESP32-S3 extension.
Espressif maintains an ESP-IDF TensorFlow Lite Micro component with S3 examples
and optimized kernels. This is an optional integration project for the current
Arduino/PlatformIO firmware, not a guaranteed drop-in dependency. Measure actual
RAM, flash, latency and sampling continuity before moving inference onto the
board. ([Espressif's official implementation](https://github.com/espressif/esp-tflite-micro))

For the teacher, deliver the training script, data/label description, participant
split manifest, saved model, baseline comparison, held-out results and a live
quality demonstration. That provides concrete evidence of a self-trained model
with a useful role independent of the planned option scorer and LLM.

## One-week scope

| Day | Concrete deliverable |
|---|---|
| 1 | Reliable full-rate optical logger, repeatable placement, label rubric; verify whether a neural network is explicitly required |
| 2–3 | Small consented pilot dataset, reviewed labels, participant split fixed before experiments |
| 4 | Train Random Forest and evaluate against existing quality rules; save reproducible preprocessing and model |
| 5 | Held-out participant evaluation; optional tiny CNN only if the core experiment is already sound |
| 6 | Host inference and dashboard quality status, with a recorded demonstration |
| 7 | Repeatability check, final report, training evidence and contingency time |

AI coding tools can shorten implementation work. They cannot manufacture sensor
ground truth, independent participants, or valid generalization evidence. If
hardware collection fails, finish a clearly labeled public-dataset quality
benchmark and recorded-data demonstration; state explicitly that it has not
been validated on this node. Avoid spending the week on both fall detection and
quality classification, on anomaly detection, or on an embedded deployment.
