# Jeff and local 2B LLM integration — 2026-11-11

Status: implemented and running with actual Jeff inference and Qwen3 1.7B through
local Ollama. Model weights are downloaded. Runtime requests remain local; no
monitoring evidence is sent to a cloud model. The simulator uses a temporary
database and visibly generated data.

## Verified environment and upstream source

- Jeff repository: <https://github.com/firelex/jeff>, inspected at
  `59898ae9e12621bd8e0199b86c951d366f5026b7` in `/tmp/rpm-jeff-review`.
- SDK/runtime version: 1.4.1; published base and adapter revision: v1.4.
- Host: Intel i5-13500HX, about 16 GB system RAM; confirmed outside the sandbox:
  NVIDIA GeForce RTX 4050 Laptop GPU with 6,141 MiB VRAM.
- Ollama 0.20.2 has `qwen3:1.7b` installed and selected. The earlier `gemma2:2b`
  remains installed but is no longer the default. The preexisting
  `qwen3.5:397b-cloud` entry is not used by this integration.
- Jeff is installed in `.venv-jeff` with CPU-only PyTorch. Its NumPy 2.5.3 stays
  separate from the main bridge's tested NumPy 2.5.4 environment.

Sources: [Jeff runtime dependencies](https://github.com/firelex/jeff/blob/59898ae9e12621bd8e0199b86c951d366f5026b7/runtime/python/pyproject.toml),
[operating guide](https://github.com/firelex/jeff/blob/59898ae9e12621bd8e0199b86c951d366f5026b7/docs/operating.md).
The README contains both pip-install examples and a statement that SDK packages
are not published yet. Check availability before choosing installation commands;
the inspected source revision is the reproducible reference.

## Give each component a separate job

The trained PPG quality classifier assesses waveform quality; the synthetic
alert-priority classifier produces the existing three-color prototype output.
Neither requires the LLM to run. Keep manual SOS and reported falls on the
existing immediate alert path.

The current implementation uses Jeff's existing **passage-ranking adapter** to
select relevant, already available evidence. Examples:

| Reviewer request | Proposed allowed tool |
|---|---|
| What are the current readings? | Latest validated telemetry |
| How has oxygen changed? | Timestamped SpO2 history |
| Is the optical waveform reliable? | Optical-quality snapshot |
| What incidents have been recorded? | Current enrollment's incident summary |
| Why is this color shown? | Priority result plus the documented prototype policy |

The actual selection function is `jeff.retrieval.ground.rerank`, alias
`ground.rerank`, with concrete evidence passages `t1`–`t4` and a `none` option.
The initially used tool router frequently asked for clarification on
interpretation questions. Its functionality remains in the setup smoke test,
but runtime selection now uses the dedicated evidence ranker. Selected IDs map
to a fixed allowlist; no arbitrary URLs, SQL, shell commands, incident resolution
or automatic review submission.

Use the **LLM** to summarize the retrieved evidence and draft a review note.
Supply timestamps, validity flags, unavailable measurements, the synthetic-model
limitation and simulation provenance. A draft does not itself become a clinician's
saved note. Summarize a frozen evidence snapshot rather than whichever readings
happen to be newest when generation finishes.

Use Jeff's existing **grounding adapter** on the draft against those same source
passages. Function: `jeff.retrieval.ground.grounding`, alias `ground.grounding`.
It takes `context.sources` and an answer and chooses `supported`,
`partly_supported`, `contradicted` or `unsupported`, with a confidence/abstention
result. Withhold or flag drafts that fail the check or abstain. A supported
classification is another fallible model judgment, not proof of truth or medical
correctness. The published calibration does not establish accuracy on this
project's numerical telemetry, so test numerical errors explicitly.

Sources: [tool-choice manifest](https://github.com/firelex/jeff/blob/59898ae9e12621bd8e0199b86c951d366f5026b7/catalogue/jeff.routing.tools/manifest.yaml),
[grounding manifest](https://github.com/firelex/jeff/blob/59898ae9e12621bd8e0199b86c951d366f5026b7/catalogue/jeff.retrieval.ground/manifest.yaml).

Jeff's `triage` adapter is explicitly for support tickets, with company/channel
context and customer sentiment/urgency. It is not a medically trained patient
triage model. Scoring patient-care actions would require a suitable new adapter,
reviewed labels and a separate evaluation. It should not be represented as an
existing capability of that adapter.

## Selected small LLM

The selected model is **Qwen3 1.7B via Ollama**, tag `qwen3:1.7b`: approximately
1.4 GB downloaded, Q4_K_M. The registry labels it 1.7B while its metadata reports
2.03B parameters. It generates short text with a 4,096-token context,
`think: false` and a 220-generated-token limit. Model selection remains configurable
with `--llm-model`.

Qwen3.5 2B was also investigated. The installed Ollama version rejected its
manifest with HTTP 412, saying a newer Ollama version is required. The integration
initially used Gemma, then switched to the compatible small Qwen3 model without
replacing the user's global Ollama installation. No 4B model was downloaded. Ollama's Qwen3.5 2B package is
listed at about 3.1 GB, including its multimodal artifacts.

Do not assume the LLM and Jeff's fast GPU engine can remain resident together.
Jeff documents about 2.8 GB for recorded CUDA graphs alone, in addition to model,
adapter and prefix memory. The implemented layout uses CPU-only Jeff in a
separate process, leaving the GPU available to Ollama. All inference runs outside
the serial-ingestion worker. Initial actual-model checks took approximately
6–13 seconds for completed summaries on this machine, including routing,
generation and grounding. These are a few functional checks, not a latency benchmark.

Ollama supports JSON-schema-constrained output on local models, followed by
application-side validation. Its cloud documentation currently says structured
outputs are unsupported. Do not silently redirect a configured local model to a
cloud model or assume identical provider behavior.

Sources: [Ollama Qwen3 1.7B](https://ollama.com/library/qwen3:1.7b),
[Ollama thinking controls](https://docs.ollama.com/capabilities/thinking),
[Qwen 3.5 2B candidate](https://ollama.com/library/qwen3.5:2b),
[Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs),
[Jeff engine memory notes](https://github.com/firelex/jeff/blob/59898ae9e12621bd8e0199b86c951d366f5026b7/docs/operating.md).

## Implemented boundary and checks

A bounded background service lives in `decision_support.py`; `jeff_worker.py`
owns the reusable CPU process and speaks JSON-lines with the bridge. The bridge
automatically enables the service; `--no-assistant` disables it. It never changes
measured values, priority colors, incident status or saved reviewer notes.

- `GET /api/assistant`: configured local model and availability.
- `POST /api/assistant`: capture evidence and queue one summary; returns 202.
- `GET /api/assistant/job?id=...`: progress, accepted summary, or withholding reason.
- Dashboard **Health interpretation**: reported symptoms, general next-step
  guidance, possible explanations, a question, generation status, draft, captured
  time, routing/grounding scores and expandable source evidence.

Requests use the existing authentication and origin checks. Only one job runs
at a time; completed jobs are bounded in memory. Results expire after five
minutes and are invalidated on enrollment/device changes. History buckets that
cross a wearer boundary are discarded. Previous wearers' incidents and reviewer
names/free-text notes are excluded. No historical context is inferred from a
device ID without an active enrollment.

Simulation disclosure is attached by application code even if the LLM omits it.
Additional checks reject invented numbers, unsupported long time spans and
selected clinical claims. A failed deterministic check permits one revised
generation; failed Jeff grounding or routing abstention withholds the draft.
Timeouts and unavailable models leave acquisition and device alarms running.

Actual checks found that Jeff missed a draft's incorrect "past hour" time span.
The deterministic time-span regression addresses that case. This is direct
evidence that a supported score does not establish factual correctness. Jeff
also sometimes asks for clarification rather than routing an incident request;
that result is shown honestly as withheld. No medical-domain calibration or
summary-accuracy score is claimed.

The Python suite includes asynchronous HTTP behavior, authentication,
origin rejection, patient changes, previous-wearer exclusion, numeric/time-span
checks, simulation disclosure, routing abstention, grounding failure and bounded
submissions. Ten JavaScript core tests also pass. Runtime smoke results are in
`models/jeff.smoke.json`; actual local-model synthetic flow results are in ignored
`data/assistant-verification.json`. Desktop/mobile artifacts are in ignored
`data/verification-assistant-2026-11-11/`. Unit tests use explicit test doubles;
the separate smoke/browser runs exercise downloaded weights.

## Reproduce setup on another machine

Use Python 3.13+ for Jeff (this machine uses 3.14), with Ollama installed and
running. Run from the repository root; source checkout and caches stay in `data/`:

```bash
git clone https://github.com/firelex/jeff.git data/jeff-source
git -C data/jeff-source checkout 59898ae9e12621bd8e0199b86c951d366f5026b7
python3.14 -m venv .venv-jeff
.venv-jeff/bin/python -m pip install -r requirements-jeff.txt
.venv-jeff/bin/python data/jeff-source/scripts/sync_shipped.py
.venv-jeff/bin/python jeff_worker.py --prepare
ollama pull qwen3:1.7b
.venv/bin/python telemetry_bridge.py --simulate
```

Jeff's prepare step downloads weights and runs routing plus supported/contradicted
smoke cases. Runtime Jeff uses the local cache with Hugging Face offline mode.
The bridge can also use `--serial-port PORT` for real hardware. Open
<http://localhost:8080/index.html>, scroll to Health interpretation, add symptoms,
and choose Explain and advise. To rerun actual-model checks against the simulator:

```bash
.venv/bin/python -m ml.check_assistant --url http://127.0.0.1:8080
```

The user's teacher requirement is already served by the project's separately
trained models; this proposal adds distinct roles for Jeff and the LLM without
claiming either has been trained for clinical use.
