# What you need to do on the real device

The software, public-data model and local training tools are implemented. A
separate alert-priority model has also been trained on one million synthetic
scenarios; [inspect its demo and training report](models/ALERT_PRIORITY_MODEL.md).
You do not need to generate or train that model again. The dashboard automatically
loads it and needs one minute of usable pulse/SpO2 readings to show a color.
Colors reproduce invented alert rules, not validated patient risk. Real-world
use needs clinical label review and independent data beyond this classroom demo.
The ESP32 was not available over USB during implementation, so its new firmware has
been compiled but not flashed or physically validated.

## 1. Connect and flash the node

Connect the ESP32 using its USB-to-UART connector. Close serial monitors and the
bridge before uploading. Find its port:

```bash
pio device list
```

Replace `PORT` below with the actual port (for example `/dev/ttyACM0` or `COM3`):

```bash
pio run -e esp32-s3-devkitc-1 -t upload --upload-port PORT
```

Keep the MPU stationary during startup calibration. Check the OLED, SOS button,
MAX30102 and TMP117. Repair the MPU power/common ground and GPIO 17/18 wiring if
it is still absent. Compare optical estimates with an available reference pulse
oximeter. These checks need your hands and actual reference equipment.

## 2. Start the dashboard and record a session

The project virtual environment and public model are already present on this
machine. On another machine, use Python 3.12+:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

On Windows, use `.venv\Scripts\python.exe` instead of `.venv/bin/python`.

```bash
.venv/bin/python telemetry_bridge.py --serial-port PORT --record-ppg data/ppg/P01-session1.jsonl --participant P01 --session session1
```

Open <http://localhost:8080/index.html>. The waveform needs ten uninterrupted
seconds before a prediction. The public model is shown for comparison; it does
not modify HR/SpO2, suppress SOS, or establish measurement accuracy.

Use anonymous aliases. Aim for a small pilot of 8–12 consenting adults, with
two short sessions each. Include steady finger contact, ordinary hand movement,
and gentle placement/removal. Record a few minutes per session. Stop with Ctrl+C,
then restart with a **new file and session alias** for the next session or person.
The recorder refuses to overwrite or mix an existing file.

An example next run is `--record-ppg data/ppg/P02-session1.jsonl --participant P02
--session session1`. Changing an alias does not create a new independent person;
keep each volunteer's alias consistent across sessions.

## 3. Review the waveforms

```bash
.venv/bin/python -m ml.prepare_local --recordings data/ppg --output data/local-quality
```

Open `data/local-quality/review.html` in your browser. Mark windows usable,
unreliable or uncertain, based on waveform evidence and any reference recording.
Movement alone is not the label. Ask another team member to independently review
a copy and resolve disagreements. Download the reviewed `labels.csv` and save it
in `data/local-quality/`. Leave uncertain windows out of training.

You must supply the genuine recordings and human quality judgments. The tools
automate window extraction, training, participant separation and reporting.

## 4. Train on your own recordings

Once labels exist, these commands do the remaining software work:

```bash
.venv/bin/python -m ml.prepare_local --recordings data/ppg --output data/local-quality --labels data/local-quality/labels.csv
.venv/bin/python -m ml.train_quality --windows data/local-quality/training.npz --output models/ppg_quality_local.joblib
.venv/bin/python telemetry_bridge.py --serial-port PORT --quality-model models/ppg_quality_local.joblib
```

The pilot splitter needs at least five distinct participants and both labels
in each split. More independent participants are preferable. All recordings of
a person stay in one split. Inspect macro-F1, the confusion matrix, bad windows
accepted as good, and retained readings. The model remains in comparison mode.

For your teacher, show the training script, labeled-data description,
participant split, saved model, held-out report, confusion plot and live
waveform/classification. The public model can be retrained with:

```bash
.venv/bin/python -m ml.download_butppg
.venv/bin/python -m ml.train_quality --butppg data/butppg
```

## Optional access from another computer

Local USB operation works without hosting. Remote binding is implemented but
requires a host you control, a trusted TLS certificate/key, and a password of
at least 16 characters in `RPM_DASHBOARD_PASSWORD`. Supply the password through
your terminal or host's secret settings, then run:

```bash
.venv/bin/python telemetry_bridge.py --serial-port PORT --host 0.0.0.0 --tls-cert /path/to/cert.pem --tls-key /path/to/private.key
```

The HTTPS login username is `rpm`. Choose your hostname and network access;
no cloud account, public deployment, domain purchase or firewall change was
performed. Patient data stays in this bridge's SQLite database. This is
authenticated prototype access, with no multi-user account or device-cloud
upload service.

Existing browser-only review notes remain in their original browser storage;
new notes are saved in SQLite. Copy any historical note you need into a new
review under the correct enrollment.

Jeff and the local **Qwen3 1.7B** explanation model are now connected. On this machine,
their weights and isolated Jeff environment are already installed. Open the
dashboard, scroll to **Health interpretation**, add reported symptoms and
choose **Explain and advise**. Jeff ranks the available evidence passages and
checks the generated explanation. General next-step guidance and the medical
evaluation disclaimer are supplied by the app; emergency warnings do not wait
for AI. See [the clinical scope and sources](management/HEALTH_INTERPRETATION.md).
Uncertain or unsupported drafts are withheld. The app supplies simulation labels
directly, so an LLM omission does not hide where the data came from.

See [setup and implementation details](management/JEFF_LLM_INTEGRATION.md) for
another machine. Use `--no-assistant` to disable summaries or `--llm-model` to
select another installed local model. Inference does not change alerts or save
clinician notes automatically.
