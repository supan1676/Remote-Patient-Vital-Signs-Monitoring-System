# Next Steps

- Audit date: 2026-10-28
- Branch / HEAD: `main` / `f67c13a`
- Current state: software tests and both PlatformIO builds pass; the working tree
  is uncommitted. Physical, clinical and regulatory validation is not complete.

## 1. Preserve the current evidence

1. Review the complete working-tree diff before any commit or release decision.
   The repository owner must decide whether and how to commit; no commit, push,
   reset, revert or discard has been performed by this audit.
2. Keep the current host results tied to the exact source state: 62 Python tests,
   10 dashboard tests, Ruff clean, Python compilation clean, JavaScript syntax
   checks clean, and both PlatformIO builds successful.
3. If any source file changes, rerun all checks and rebuild both firmware
   targets before treating the results as current.

## 2. Hardware verification: TMP117

All steps below are **HARDWARE VERIFICATION REQUIRED** until performed on the
actual board.

1. Run the raw diagnostic on the assembled board:
   ```bash
   pio run -d diagnostics/tmp117_raw -t upload --upload-port COM6
   pio device monitor -d diagnostics/tmp117_raw --port COM6
   ```
2. Capture at least five minutes of output. Verify:
   - the responding address is in `0x48`–`0x4B`;
   - `WHO_AM_I` is `0x0117`;
   - the configuration writable mask reads back as expected;
   - raw temperature is present and does not alternate with `0xFFFF` or `0x0000`;
   - data-ready behavior and read failures are recorded;
   - the summary counts are recorded, including all-ones/all-zeros incidents.
3. Compare the actual TMP117 reading with a validated reference thermometer under
   controlled conditions. Document ambient temperature, contact pressure,
   stabilization time and uncertainty. Do not add a fixed offset and do not
   convert the result into a core temperature.
4. Upload the main firmware and confirm:
   - the actual TMP117 reading appears in live telemetry and the
     **TMP117 Sensor Temperature (°C)** display;
   - `wrist_contact_status` remains `unverified`;
   - clinical `wrist_skin_temperature_c`, raw and timestamp remain `null`;
   - `estimated_core_temperature_c` remains `null` and fever screening remains
     `not_available` with the exact required message;
   - hot-plug removal and recovery produce nulls and `not_available`, not zero;
   - the OLED temperature page stays within the display and the alert paths work.

## 3. Clinical wrist contact

1. Define a contact-verification method before exposing any clinical wrist
   value. It must be independent of whether the temperature happens to look
   plausible; thresholds or trends must not be used to infer contact.
2. Once a method exists, validate it and require matching actual sensor value,
   raw register and timestamp plus the `-10..60 °C` clinical guard before
   populating `wrist_skin_temperature_*`.
3. Until then, do not change `wrist_contact_status` or the clinical wrist status
   from `unverified`, and do not use the actual TMP117 value as a substitute.

## 4. Other hardware checks

All are **HARDWARE VERIFICATION REQUIRED**:

1. Validate MAX30102 heart rate and SpO2 against appropriate references, including
   finger placement, motion, ambient light and signal-quality behavior.
2. Recheck MPU-6050/6500 range, axis signs, stationary bias, fall-candidate
   behavior and recovery. Do not describe the current bias as a full calibration.
3. Confirm the SOS button, OLED rendering, serial reconnect and dashboard alert
   paths on the assembled device.
4. Capture an end-to-end ESP32 → bridge → dashboard/history session and verify
   that gaps remain gaps and that actual sensor telemetry is not stored as the
   clinical wrist history metric.

## 5. Validation and release gates

1. Keep a hardware log containing the exact board, firmware commit, sensor
   addresses, reference instruments, conditions and results. Do not place patient
   identifiers in the repository.
2. Add CI for the existing host tests and both firmware builds after reviewing
   repository policy.
3. Do not claim clinical, research or medical-device readiness from these
   software checks. Core temperature and fever screening remain unavailable by
   design, and no clinical validation has been performed.
4. Only after the hardware and contact-verification evidence exists should the
   project consider a wider deployment or a regulated-device pathway.
