"""Generate synthetic one-minute alert scenarios; never clinical training truth."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np

from alert_priority import (FEATURE_NAMES, FEATURE_VERSION, POLICY_VERSION,
                            WINDOW, extract_features, policy_labels)

FAMILIES = {
    'train': ('linear', 'step', 'plateau', 'oscillating'),
    'validation': ('sigmoid', 'exponential'),
    'test': ('staircase', 'late_transition'),
}
ALL_FAMILIES = sum(FAMILIES.values(), ())
PATTERNS = ('steady', 'activity', 'falling_oxygen', 'rising_pulse', 'slowing_pulse',
            'combined_change', 'recovery', 'brief_disturbance', 'persistent_low_oxygen',
            'vigorous_movement', 'missing_data', 'boundary_case', 'poor_quality', 'variation')


def _shape(name, n, rng):
    t = np.linspace(0, 1, WINDOW)[None, :]
    midpoint = rng.uniform(.2, .7, (n, 1))
    if name == 'linear':
        return np.broadcast_to(t, (n, WINDOW)).copy()
    if name == 'step':
        return (t >= midpoint).astype(float)
    if name == 'plateau':
        return np.clip(t / midpoint, 0, 1)
    if name == 'oscillating':
        return np.clip(t + .18 * np.sin(t * rng.uniform(5, 16, (n, 1))), 0, 1)
    if name == 'sigmoid':
        return 1 / (1 + np.exp(-rng.uniform(8, 20, (n, 1)) * (t - midpoint)))
    if name == 'exponential':
        rate = rng.uniform(1, 4, (n, 1))
        return np.expm1(rate * t) / np.expm1(rate)
    if name == 'staircase':
        levels = rng.integers(3, 8, (n, 1))
        return np.floor(t * levels) / levels
    if name == 'late_transition':
        return np.clip((t - midpoint) / rng.uniform(.08, .25, (n, 1)), 0, 1)
    raise ValueError(name)


def make_batch(profile_ids, profile_hr, profile_spo2, split, rng):
    n = len(profile_ids)
    family = rng.choice(FAMILIES[split], size=n)
    progression = np.empty((n, WINDOW))
    for name in FAMILIES[split]:
        mask = family == name
        progression[mask] = _shape(name, int(mask.sum()), rng)
    pattern = rng.integers(0, len(PATTERNS), n)
    base_hr = profile_hr[profile_ids, None]
    base_spo2 = profile_spo2[profile_ids, None]
    hr = np.broadcast_to(base_hr, (n, WINDOW)).copy()
    spo2 = np.broadcast_to(base_spo2, (n, WINDOW)).copy()
    motion = np.ones((n, WINDOW))
    quality = np.ones((n, WINDOW), dtype=bool)
    def selected(code):
        mask = pattern == code
        return mask, int(mask.sum()), progression[mask]
    for code in (1, 9):
        mask, count, p = selected(code)
        amplitude = rng.uniform(20, 80 if code == 9 else 60, (count, 1))
        hr[mask] += amplitude * p
        phase = np.arange(WINDOW)[None, :] * rng.uniform(1, 3, (count, 1))
        motion[mask] += rng.uniform(.3, 1.1, (count, 1)) * np.sin(phase) * (.5 + .5 * p)
        spo2[mask] -= rng.uniform(0, 1, (count, 1)) * p
    mask, count, p = selected(2)
    spo2[mask] += (rng.uniform(75, 95, (count, 1)) - base_spo2[mask]) * p
    hr[mask] += rng.uniform(0, 45, (count, 1)) * p
    mask, count, p = selected(3)
    hr[mask] += (rng.uniform(105, 200, (count, 1)) - base_hr[mask]) * p
    mask, count, p = selected(4)
    hr[mask] += (rng.uniform(25, 58, (count, 1)) - base_hr[mask]) * p
    mask, count, p = selected(5)
    hr[mask] += (rng.uniform(105, 175, (count, 1)) - base_hr[mask]) * p
    spo2[mask] += (rng.uniform(82, 95, (count, 1)) - base_spo2[mask]) * p
    mask, count, p = selected(6)
    hr[mask] += rng.uniform(25, 90, (count, 1)) * (1 - p)
    spo2[mask] -= rng.uniform(3, 20, (count, 1)) * (1 - p)
    mask, count, _ = selected(7)
    t = np.arange(WINDOW)[None, :]
    pulse = np.exp(-.5 * ((t - rng.uniform(10, 58, (count, 1))) / rng.uniform(.5, 4, (count, 1))) ** 2)
    hr[mask] += rng.uniform(-15, 70, (count, 1)) * pulse
    spo2[mask] -= rng.uniform(1, 18, (count, 1)) * pulse
    quality[mask] &= pulse < rng.uniform(.25, .85, (count, 1))
    mask, count, p = selected(8)
    spo2[mask] += (rng.uniform(72, 94, (count, 1)) - base_spo2[mask]) * (.7 + .3 * p)
    hr[mask] += rng.uniform(5, 35, (count, 1)) * p
    mask, count, _ = selected(10)
    quality[mask] = rng.random((count, WINDOW)) > rng.uniform(.1, .5, (count, 1))
    hr[mask] = np.where(quality[mask], hr[mask], np.nan)
    spo2[mask] = np.where(quality[mask], spo2[mask], np.nan)
    mask, count, p = selected(11)
    oxygen_boundary = rng.random(count) < .5
    h = rng.choice([40, 50, 120, 140, 190], (count, 1)) + rng.uniform(-1.5, 1.5, (count, 1))
    s = rng.choice([90, 93, 95, 96], (count, 1)) + rng.uniform(-.5, .5, (count, 1))
    h[oxygen_boundary] = base_hr[mask][oxygen_boundary]
    s[~oxygen_boundary] = base_spo2[mask][~oxygen_boundary]
    hr[mask] += (h - base_hr[mask]) * (.8 + .2 * p)
    spo2[mask] += (s - base_spo2[mask]) * (.8 + .2 * p)
    mask, count, _ = selected(12)
    quality[mask] = False
    hr[mask] = rng.uniform(20, 240, (count, WINDOW))
    spo2[mask] = rng.uniform(1, 100, (count, WINDOW))
    mask, count, p = selected(13)
    hr[mask] += rng.uniform(1, 12, (count, 1)) * np.sin(p * rng.uniform(4, 15, (count, 1)))
    # Correlated smooth noise plus small observation noise, independent of labels.
    for channel, scale in ((hr, rng.uniform(.3, 2, (n, 1))),
                           (spo2, rng.uniform(.03, .3, (n, 1)))):
        noise = rng.normal(size=(n, WINDOW))
        noise = (noise + np.roll(noise, 1, axis=1) + np.roll(noise, -1, axis=1)) / 3
        channel += noise * scale
    motion += rng.normal(0, .015, motion.shape)
    motion = np.clip(motion, 0, 4)
    # Missing motion is explicitly represented, not silently declared stationary.
    motion[rng.random(n) < .12] = np.nan
    signals = np.stack([np.clip(hr, 20, 240), np.clip(spo2, .1, 100), motion], axis=2).astype(np.float32)
    features = extract_features(signals, quality)
    labels = policy_labels(features)
    codes = np.asarray([ALL_FAMILIES.index(name) for name in family], dtype=np.uint8)
    return signals, quality, features, labels, codes, pattern.astype(np.uint8)


def generate(output, scenarios=1_000_000, seed=20261111, batch_size=8192):
    if scenarios < 1000:
        raise ValueError('Use at least 1,000 scenarios to exercise all splits.')
    if (output / 'manifest.json').exists():
        raise ValueError('Dataset already exists; choose a new output directory to preserve provenance.')
    estimate = scenarios * (WINDOW * 13 + len(FEATURE_NAMES) * 4 + 12)
    output.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(output).free < estimate * 1.2:
        raise ValueError('Insufficient free disk space for this dataset size.')
    profiles = (scenarios + 9) // 10
    child_seeds = np.random.SeedSequence(seed).spawn(4)
    profile_rng = np.random.default_rng(child_seeds[0])
    profile_hr = np.clip(profile_rng.normal(73, 10, profiles), 45, 103)
    profile_spo2 = profile_rng.uniform(96, 99.6, profiles)
    arrays = {}
    specifications = {
        'signals': (np.float32, (scenarios, WINDOW, 3)),
        'quality': (np.bool_, (scenarios, WINDOW)),
        'features': (np.float32, (scenarios, len(FEATURE_NAMES))),
        'labels': (np.int8, (scenarios,)), 'profiles': (np.int32, (scenarios,)),
        'families': (np.uint8, (scenarios,)), 'patterns': (np.uint8, (scenarios,)),
        'splits': (np.uint8, (scenarios,)),
    }
    for name, (dtype, shape) in specifications.items():
        path = output / f'{name}.npy'
        if path.exists():
            raise ValueError('An incomplete dataset exists here; choose a new output directory.')
        arrays[name] = np.lib.format.open_memmap(path, mode='w+', dtype=dtype, shape=shape)
    boundaries = [0, int(profiles * .7) * 10, int(profiles * .85) * 10, scenarios]
    counts = {}
    for split_code, split in enumerate(('train', 'validation', 'test')):
        rng = np.random.default_rng(child_seeds[split_code + 1])
        split_counts = np.zeros(4, dtype=np.int64)
        for start in range(boundaries[split_code], boundaries[split_code + 1], batch_size):
            end = min(start + batch_size, boundaries[split_code + 1])
            ids = np.arange(start, end, dtype=np.int64) // 10
            signals, quality, features, labels, family, pattern = make_batch(ids, profile_hr, profile_spo2, split, rng)
            for name, value in (('signals', signals), ('quality', quality), ('features', features),
                                ('labels', labels), ('profiles', ids), ('families', family), ('patterns', pattern)):
                arrays[name][start:end] = value
            arrays['splits'][start:end] = split_code
            split_counts += np.bincount(labels + 1, minlength=4)
        counts[split] = dict(zip(('unknown', 'green', 'yellow', 'red'), map(int, split_counts)))
        print(f'{split}: {boundaries[split_code + 1] - boundaries[split_code]:,} scenarios generated; {counts[split]}', flush=True)
    hashes = {}
    for name, array in arrays.items():
        array.flush()
        with (output / f'{name}.npy').open('rb') as stream:
            hashes[f'{name}.npy'] = hashlib.file_digest(stream, 'sha256').hexdigest()
    root = Path(__file__).resolve().parents[1]
    manifest = dict(completed=True, source='synthetic', human_reviewed=False,
        clinically_validated=False, generated_at=datetime.now(timezone.utc).isoformat(),
        seed=seed, profiles=profiles, scenarios=scenarios, timepoints=scenarios * WINDOW,
        seconds_per_scenario=WINDOW, channels=['heart_rate_bpm', 'spo2_percent', 'motion_g'],
        feature_version=FEATURE_VERSION, feature_names=list(FEATURE_NAMES), policy_version=POLICY_VERSION,
        split_families=FAMILIES, family_codes=ALL_FAMILIES, pattern_codes=PATTERNS, label_counts=counts,
        split_profile_ranges={'train': [0, int(profiles * .7) - 1],
                              'validation': [int(profiles * .7), int(profiles * .85) - 1],
                              'test': [int(profiles * .85), profiles - 1]},
        sha256=hashes, generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        policy_sha256=hashlib.sha256((root / 'alert_priority.py').read_bytes()).hexdigest(),
        limitations=['Engineering rule imitation, not medically reviewed risk labels.',
                     'Artificial profiles are not independent real patients.',
                     'Synthetic performance does not establish clinical accuracy.'])
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Saved {scenarios:,} scenarios / {scenarios * WINDOW:,} timepoints to {output}', flush=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('data/synthetic-priority-v1'))
    parser.add_argument('--scenarios', type=int, default=1_000_000)
    parser.add_argument('--seed', type=int, default=20261111)
    args = parser.parse_args()
    generate(args.output, args.scenarios, args.seed)


if __name__ == '__main__':
    main()
