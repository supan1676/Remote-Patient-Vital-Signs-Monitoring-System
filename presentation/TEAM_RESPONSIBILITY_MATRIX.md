# Team Responsibility Matrix

> **Project:** Remote Patient Vital Signs Monitoring System / RPM IoMT Patient Monitoring Node
>
> **Repository:** `RPMIOMTproject`, branch `main`, HEAD `f67c13a`
>
> **Purpose:** divide substantial technical ownership for the HOD individual discussions, define interfaces and handoffs, and prevent “everyone owns everything” answers.
>
> **Authorship warning:** this is a **proposed** responsibility matrix. Names are placeholders because no names were supplied. It does not prove that any placeholder author wrote a file. The team must confirm the real allocation and revise this matrix if needed. Until confirmed, use **“the team implemented”** for source-backed shared work.

## 1. Ownership rules

1. **Every member owns a technical domain, not a slide deck.** Each area includes files, behavior, failure modes, tests and evidence.
2. **Ownership means responsibility to explain and defend**, not exclusive authorship.
3. **Cross-module behavior is shared.** No member may “hand off” the temperature semantics, null policy or evidence classification.
4. **Names are placeholders.** `[MEMBER 1 NAME]` … `[MEMBER 5 NAME]` must be replaced by the team after the real allocation is agreed.
5. **Source does not establish personal authorship.** A commit history or a team statement is needed before making a personal authorship claim.
6. **One decision owner per cross-cutting rule.** The owner coordinates changes; implementation remains shared.
7. **No production source was changed by this documentation task.** The matrix describes the current working tree, including prior uncommitted repairs.

## 2. The five substantial ownership areas

| Area | Member | Primary technical ownership | Deep files / artefacts | Evidence the member must be able to show | Main dependencies |
|:---|:---|:---|:---|:---|:---|
| **A. Firmware and system integration** | `[MEMBER 1 NAME]` | Boot/loop scheduling; I2C integration; sensor state machine; JSON serialization; OLED; SOS/fall; hot-plug; build configuration | `src/main.cpp`; `platformio.ini`; `boards/esp32-s3-devkitc-1-n16r8.json`; `src/tmp117_protocol.h` (consumer) | Main and diagnostic build results; firmware walkthrough; status/null paths; SOS/fall logic; hardware limitations | Hardware truth from Area B; schema consumed by Areas C/D; safety rules from Area E |
| **B. Hardware, sensors and measurement reliability** | `[MEMBER 2 NAME]` | Wiring/bus topology; TMP117 protocol and raw diagnostic; MAX30102 quality guards; MPU scaling/calibration; physical validation method | `src/tmp117_protocol.h`; `src/sensor_math.h`; `diagnostics/tmp117_raw/`; `wiring-guide.html`; `README.md` hardware sections | TMP117 raw conversion/identity/config; diagnostic build; MAX/MPU explanation; prior-observation labels; reference-test procedure | Firmware integration from Area A; bridge/dashboard revalidation from C/D; policy from E |
| **C. Communication and backend** | `[MEMBER 3 NAME]` | Serial discovery/reader; framing; duplicate and duplicate-key handling; strict schema/status/range validation; freshness; SSE/HTTP APIs; storage handoff; local security posture | `telemetry_bridge.py`; `tests/test_telemetry.py`; `tests/fixtures.py`; `README.md` telemetry/API sections | Parser/validator walkthrough; rejection cases; stale/no-replay test; API map; storage-error behavior; 62-test evidence | Firmware contract from A; raw rules from B/E; storage/dashboard expectations from D |
| **D. Dashboard and storage** | `[MEMBER 4 NAME]` | Exact labels; live DOM/SSE behavior; null/gap-aware chart and CSV; SQLite schema/migration/retention; verified wrist storage; device isolation | `index.html`; `assets/dashboard.js`; `assets/dashboard_core.js`; `assets/dashboard.css`; `telemetry_store.py`; `tests/dashboard_core.test.js`; `tests/test_history.py` | Label/display walkthrough; 10 Node tests; history tests; gap/CSV behavior; schema/migration; browser/E2E limits | Backend API/SSE from C; safety/contact policy from E; producer fields from A |
| **E. Analytics, safety and quality** | `[MEMBER 5 NAME]` | Temperature/fever policy; baseline statistics; deterministic alert engine; audit/evidence classification; quality gates | `temperature_safety.py`; `personal_baseline.py`; `ai_decision_engine.py`; `tests/test_temperature_safety.py`; `tests/test_baseline.py`; `tests/test_decision_engine.py`; audit documents | Exact semantics; baseline formula/qualification; deterministic thresholds; C-01–C-14/O-01–O-07 status; evidence labels; test/build limits | Measurements from B/D; packet fields from A/C; storage/baseline API from D |

### 2.1 Why these are substantial

- **Area A** owns the integration that makes the whole repository a system rather than isolated sensor sketches.
- **Area B** owns the raw measurement chain and the physical-verification gap; it is not “just wiring.”
- **Area C** owns the trust boundary that rejects malformed or contradictory packets and prevents stale replay.
- **Area D** owns the clinical display/history semantics: exact labels, nulls, gaps, CSV and verified-contact-only storage.
- **Area E** owns the safety policy, statistical baseline, deterministic alerting and evidence discipline.

No area is merely “documentation” or “presentation.” Each has code and testable behavior.

## 3. Domain charters

### 3.1 Area A — Firmware and system integration (`[MEMBER 1 NAME]`)

**Owns the explanation of:**

- `setup()` and `loop()` execution order.
- Primary `Wire` (GPIO 8/9, 50 kHz) and dedicated `Wire1` (GPIO 17/18, 400 kHz).
- Sensor initialization and status propagation: `valid`, `warming_up`, `low_quality`, `stale`, `sensor_error`, `not_available`.
- `outputTelemetry()` schema-2 JSON, `[JSON]` prefix, `115200` baud, `rpm-2.1.0`.
- Actual TMP117 versus clinical wrist fields at the firmware boundary.
- SOS GPIO 5 active-low path, 300 ms debounce, 15 s auto-clear.
- Fall candidate: free fall `<0.6 g`, impact `>2.5 g`, 60–600 ms, 6 s active.
- Hot-plug probes and 3 s retry.
- OLED compact-text limitation.
- Build flags: `RPM_ENABLE_OPTIONAL_SHT40=0`, `RPM_ENABLE_OPTIONAL_MLX90614=0`.

**Must not claim:** physical sensor/OLED/SOS validation; TMP117 accuracy; wrist/core temperature.

**Primary handoff:** packet contract and statuses to Area C; actual/wrist semantics to Areas D/E; raw hardware questions to Area B.

### 3.2 Area B — Hardware, sensors and measurement reliability (`[MEMBER 2 NAME]`)

**Owns the explanation of:**

- Installed inventory and explicit non-installed modules.
- Power/ground/address strapping, primary/IMU buses and pull-ups.
- TMP117 `WHO_AM_I=0x0117`, configuration `0x01A0`, `DATA_READY`, offset, signed conversion `0.0078125 °C/LSB`.
- Raw diagnostic: address scan `0x48–0x4B`, config readback, raw/failure/stuck counters.
- Rejection of `0x0000`/`0xFFFF`, `-55..150 °C` actual range, `>5 °C` confirmation.
- MAX30102 DC/AC/PI guards and HR/SpO2 limits.
- MPU ±8 g/±250 dps, `4096 LSB/g`, `131 LSB/dps`, single-orientation bias limits.
- Reference-measurement and contact-verification protocols.

**Must not claim:** accuracy without a reference; prior `0x49`/raw observations as reproduced; SHT40/MLX as installed; wrist/core temperature from TMP117.

**Primary handoff:** raw/electrical evidence and caveats to Areas A/E; hardware status expectations to Areas C/D.

### 3.3 Area C — Communication and backend (`[MEMBER 3 NAME]`)

**Owns the explanation of:**

- Serial discovery (`find_serial_port()` unique USB VID), reader thread, 115200 baud, buffer framing.
- `DuplicateSuppressor` 1.5 s versus duplicate JSON-key rejection.
- `parse_packet()` and `_validate_packet()`; `[JSON]` producer convention.
- `_validate_measurement()`, `_validate_temperature()`, `_validate_fever()`, `_validate_imu()`.
- Sensor/active/active_max consistency (`active_max = 3`).
- `snapshot()` freshness at 5 s and no stale replay.
- SSE `/api/stream` queue 8/drop-oldest.
- HTTP routes and status codes; 127.0.0.1 binding; POST baseline origin/size/device checks.
- Storage handoff and nonfatal `storage_error`.

**Must not claim:** real serial/load/security validation; clinical accuracy; full authentication/TLS.

**Primary handoff:** accepted packet shape/API to Area D; rejection reasons and schema limits to Areas A/D/E.

### 3.4 Area D — Dashboard and storage (`[MEMBER 4 NAME]`)

**Owns the explanation of:**

- Four active metrics and exact labels **Wrist Skin Temperature (°C)** / **TMP117 Sensor Temperature (°C)**.
- `DashboardCore.metricStatus()`, `metricValue()`, `temperatureAssessment()`, `gapAwarePath()`, `csv()`.
- Live SSE consumption, `_received_at` duplicate-render guard, history request token.
- Gap-aware chart; blank CSV cells; active columns only.
- SQLite schema/migration/retention; `measurements()` verified-contact-only wrist; `history()` buckets/gaps/device isolation.
- Core/fever display with exact message.
- Browser/accessibility/security evidence limits.

**Must not claim:** full browser E2E/WCAG/security audit; wrist currently populated; actual TMP117 in history/CSV.

**Primary handoff:** storage/API expectations to Area C; baseline/event display needs to Area E; label/evidence gaps to all.

### 3.5 Area E — Analytics, safety and quality (`[MEMBER 5 NAME]`)

**Owns the explanation of:**

- `temperature_safety.py` actual/wrist/core/fever rules and exact message.
- Raw tolerance/stuck/range checks; no fixed offset.
- Baseline: 7 days/30 minutes/day, minute means, median/MAD, noise floors, freeze, partial/ready states, deviation rules.
- Deterministic engine: RED/YELLOW/GREEN/UNKNOWN, HR 50/120, SpO2 90, missing optical data.
- No trained model/LLM.
- Audit/cleanup/next-step evidence: C-01–C-14 closed in software; O-01–O-07 open.
- Test/build evidence labels and release gates.

**Must not claim:** clinical validation, core/fever capability, AI model, all audit items closed, hardware accuracy.

**Primary handoff:** policy and evidence rules to Areas A–D; baseline expectations to Area D; hardware/clinical open items to all.

## 4. Cross-cutting shared ownership

These topics are **shared by all five members** and must not be left to one person:

| Shared topic | Why everyone needs it | Decision coordinator |
|:---|:---|:---|
| Actual TMP117 ≠ clinical wrist ≠ core | Prevents the project’s most serious semantic error | Area E |
| Null instead of zero/stale | Applies to firmware, API, store, dashboard, CSV | Area C |
| Exact clinical labels/message | Appears in JSON, dashboard, OLED shorthand, terminal | Area D/E |
| `active_max = 3`; SHT40/MLX absent | Inventory claim repeated across modules | Area A/B |
| Evidence classification | Prevents tests turning into hardware/clinical claims | Area E |
| No core/fever invention | Safety boundary for all outputs | Area E |
| Schema-2 contract | Producer/consumer change control | Area C |
| Hardware validation gap | Must be stated by every member | Area B |
| No personal authorship without evidence | Protects team honesty | All |

### 4.1 Decision rights

| Decision | Coordinator | Required consultation |
|:---|:---|:---|
| Firmware packet/field/status change | `[MEMBER 1 NAME]` | Areas C, D, E |
| Sensor range/raw/protocol/hardware claim | `[MEMBER 2 NAME]` | Areas A, E |
| Validation/API/SSE/security behavior | `[MEMBER 3 NAME]` | Areas A, D |
| Storage schema/label/history/CSV behavior | `[MEMBER 4 NAME]` | Areas C, E |
| Temperature/baseline/alert policy | `[MEMBER 5 NAME]` | Areas A–D (all implement) |
| Evidence classification in documents | `[MEMBER 5 NAME]` | All source owners |
| Final HOD claim wording | Team consensus | All five |

A coordinator does not own every line; they own consistency of the decision and the evidence trail.

## 5. Interface handoffs

### 5.1 Handoff table

| From → To | Artefact | Acceptance condition | Failure mode if skipped |
|:---|:---|:---|:---|
| A → B | Firmware TMP117 read/config/status behavior; raw diagnostic need | Raw issue can be reproduced without main firmware ambiguity | Hardware debugging blames software or vice versa |
| B → A | Confirmed electrical/identity/range constraints | Address/`WHO_AM_I`/config/raw expectations align | Firmware accepts wrong device or rejects valid hardware |
| A → C | Schema-2 sample packet and status semantics | `parse_packet()` + `_validate_packet()` accept the intended null/valid pattern | Live dashboard empty or invalid packets |
| B → C | Raw/stuck/range/tolerance rules | Bridge enforces independent equivalent checks | A stuck raw value reaches UI/history |
| C → D | SSE/API payloads; history/baseline/events routes | Dashboard can render connected/disconnected/error states | UI shows stale/blank incorrectly |
| D → C | Required fields/labels/gap behavior | API returns data the dashboard can validate/display | Label/value mismatch |
| D → E | Stored minute means/events/baseline API | Baseline can compute qualified days and comparisons | Baseline uses raw/unverified data |
| E → A–D | Exact temperature/fever/baseline policy | Every layer has matching tests and labels | One layer invents core/wrist/fever |
| E → all | Evidence tags and open-item status | Claims match source/test/build/HW reality | Tests presented as hardware/clinical proof |
| All → E | Test/build/hardware evidence with dates | Audit document reflects current state | Stale claims in viva |

### 5.2 Handoff quality rules

1. **State the exact source path and function**, not just “the backend.”
2. **State the evidence tag and date** for every test/build/hardware claim.
3. **State the failure mode** the receiver must handle (null, stale, error, gap).
4. **Preserve the distinction** between actual sensor temperature and clinical wrist.
5. **Never hand off a fabricated “working” claim**; hand off the limitation and the next test.

## 6. Evidence ownership

| Evidence | Owner of explanation | Who may be asked |
|:---|:---|:---|
| Main firmware build success and sizes | `[MEMBER 1 NAME]` | All |
| TMP117 diagnostic build/raw procedure | `[MEMBER 2 NAME]` | All |
| `src/tmp117_protocol.h` vectors | `[MEMBER 2 NAME]` | 1, 5 |
| Bridge validation/tests | `[MEMBER 3 NAME]` | All |
| Dashboard Node tests | `[MEMBER 4 NAME]` | 3, 5 |
| History Python tests | `[MEMBER 4 NAME]` | 3, 5 |
| Temperature/fever tests | `[MEMBER 5 NAME]` | All |
| Baseline/engine tests | `[MEMBER 5 NAME]` | 4 |
| Audit register/cleanup/next steps | `[MEMBER 5 NAME]` | All |
| Prior hardware observations | `[MEMBER 2 NAME]` | 1, 5 |
| Hardware validation gap | `[MEMBER 2 NAME]` | All |

### 6.1 Exact current evidence summary

- `python -m pytest -q` → **62 passed** (fresh 2026-10-29).
- `node --test tests/dashboard_core.test.js` → **10 passed** (fresh 2026-10-29).
- Ruff, Python compilation and JavaScript syntax checks → passed.
- `pio run -e esp32-s3-devkitc-1` → **SUCCESS**; RAM 21,424/327,680 bytes; flash 326,001/6,553,600 bytes.
- `pio run -d diagnostics/tmp117_raw` → **SUCCESS**; RAM 18,916/327,680 bytes; flash 282,377/6,553,600 bytes.
- No fresh hardware upload, serial capture, reference thermometer, contact verification or assembled end-to-end test.

Prior hardware observations (`0x49`, raw `0x0ED3 → 29.6484375 °C`, raw `0xFFFF → -0.0078125 °C`, diagnostic `0x0DA7 → 27.30469 °C`, 60 reads/0 failures/0 stuck patterns) remain **RECORDED HW OBS — not reproduced; HARDWARE VERIFICATION REQUIRED.**

## 7. Substantial ownership coverage check

Use this table before the viva to ensure no member is presenting only superficial material.

| Member | Code they can trace | Debug scenario they can lead | Test/build evidence they can explain | Cross-module question they can answer |
|:---|:---|:---|:---|:---|
| 1 | `src/main.cpp` boot/loop/output/OLED | SOS/fall/stale/hot-plug | Main + diagnostic builds, Python/Node counts | Why actual TMP117 is not wrist; how bridge consumes packet |
| 2 | TMP117 header/diagnostic; MAX/MPU init | TMP raw anomaly/identity; MAX quality; MPU calibration | Vector/compile-time tests; diagnostic build | How bridge/dashboard recheck raw/range |
| 3 | Serial reader/validators/SSE/APIs | malformed packet; duplicate/stale; storage error; no port | 62 Python suite; schema rejection tests | How dashboard gets fresh/history data; why unverified wrist rejected |
| 4 | Dashboard core/DOM; SQLite store | blank wrist; chart gap; CSV zero bug; migration | 10 Node; history tests | How store/baseline handle unverified wrist; exact labels |
| 5 | safety/baseline/engine | conflation; baseline not ready; UNKNOWN; AI-name | 62 Python; temperature/baseline/engine tests; C/O audit items | Where policy is enforced across layers; baseline/storage interaction |

If a member cannot fill a row, the allocation is not yet substantial enough; reassign or deepen the preparation before the HOD meeting.

## 8. Conflict and error protocol

1. **Source wins over memory.** Check the file/function before repeating a claim.
2. **Tests win over intuition**, but only for the behavior they exercise.
3. **Hardware evidence wins over both**, once captured with a dated protocol.
4. **A safety concern stops the claim.** If actual sensor temperature is being called wrist/core, the answer is wrong regardless of UI convenience.
5. **Do not fix the demo by weakening validation.** Fix the producer or version the contract.
6. **Do not invent an owner.** If authorship is unknown, say the team implemented it and identify the source path.
7. **Do not use prior hardware observations as current validation.**
8. **Escalate unresolved semantic conflicts to Area E**, and unresolved packet/API conflicts to Area C, before the viva.

## 9. Red lines for every member

- Never present actual TMP117 temperature as clinical wrist or core temperature.
- Never claim core estimation or fever screening; core is null/`not_available`, fever message is exact.
- Never present SHT40/MLX90614 as installed/tested.
- Never claim sensor accuracy without a reference measurement.
- Never claim a trained AI model/LLM exists.
- Never claim the physical device/OLED/SOS/fall was validated in this pass.
- Never claim all audit items are closed.
- Never claim personal authorship without team confirmation.
- Never hide a gap as zero or a line through missing history.
- Never call this prototype a clinically validated diagnostic/emergency system.

## 10. Team sign-off checklist

- [ ] Real names replace all `[MEMBER n NAME]` placeholders.
- [ ] Each member confirms the files/behaviors they can defend.
- [ ] Each member can answer the two cross-module questions in their document.
- [ ] The team agrees on exact labels/message/range semantics.
- [ ] The team agrees on the evidence tags and current test/build counts.
- [ ] The team agrees that prior TMP117 observations are not reproduced.
- [ ] The team agrees that SHT40/MLX are not installed.
- [ ] The team agrees that the engine is deterministic, not AI/LLM.
- [ ] The team agrees on the hardware/clinical validation gaps.
- [ ] The team agrees no production source was changed by this documentation task.
- [ ] The matrix is dated and retained with the eight presentation documents.

## 11. Closing statement

**Substantial ownership is distributed across firmware, hardware, backend, dashboard/storage and analytics/safety/quality. Cross-cutting safety semantics remain shared. Source-backed work is described as “the team implemented”; personal authorship is claimed only after the team confirms it.**
