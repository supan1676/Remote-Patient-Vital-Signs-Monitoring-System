"""Train a Random Forest with participant-separated train/validation/test sets."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
from scipy.signal import resample_poly
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (classification_report, confusion_matrix, f1_score,
                             brier_score_loss)
from sklearn.model_selection import GroupShuffleSplit

from ppg_quality import FEATURE_NAMES, FEATURE_VERSION, RATE, WINDOW_SAMPLES, extract_features


def public_dataset(directory):
    cache = directory / f'features-v{FEATURE_VERSION}.npz'
    if cache.exists():
        return cache
    import wfdb
    annotations = list(directory.rglob('quality-hr-ann.csv'))
    if len(annotations) != 1:
        raise ValueError('Expected exactly one quality-hr-ann.csv in the BUT PPG directory.')
    headers = {p.stem.removesuffix('_PPG'): p for p in directory.rglob('*_PPG.hea')}
    labels = []
    waves = []
    identities = []
    for row in csv.reader(annotations[0].read_text().splitlines()):
        if not row or not row[0].strip().isdigit():
            continue
        identity, label = row[0].strip(), int(row[1])
        record = wfdb.rdrecord(str(headers[identity].with_suffix('')))
        names = [name.split()[-1] if name else '' for name in record.sig_name]
        # Some original WFDB headers encode one row with 300 channels instead
        # of 300 rows with one channel. Both carry the same 300 time samples.
        if record.fs != 30:
            raise ValueError(f'Unexpected waveform contract in {identity}.')
        if record.p_signal.size == 300 and 1 in record.p_signal.shape:
            red = record.p_signal.reshape(-1)
        elif record.p_signal.shape == (300, 3) and 'PPG_R' in names:
            red = record.p_signal[:, names.index('PPG_R')]
        else:
            raise ValueError(f'No complete ten-second red channel in {identity}.')
        waveform = resample_poly(red, 5, 6, padtype='line')
        if not np.isfinite(waveform).all() or label not in (0, 1):
            raise ValueError(f'Invalid waveform/label in {identity}.')
        labels.append(label)
        waves.append(waveform)
        identities.append(identity)
    if not labels:
        raise ValueError('No annotated public recordings were found.')
    np.savez_compressed(cache, red=np.asarray(waves), labels=labels,
                        groups=[identity[:3] for identity in identities], ids=identities,
                        domain='BUT PPG v2 smartphone', sample_rate_hz=RATE)
    return cache


def metrics(y, predicted, scores=None):
    result = dict(macro_f1=float(f1_score(y, predicted, average='macro', zero_division=0)),
                  confusion_matrix=confusion_matrix(y, predicted, labels=[0, 1]).tolist(),
                  classes=classification_report(y, predicted, labels=[0, 1],
                      target_names=['unreliable', 'usable'], output_dict=True, zero_division=0),
                  bad_accepted_fraction=float(np.mean(predicted[y == 0] == 1)),
                  retained_fraction=float(np.mean(predicted == 1)))
    if scores is not None:
        result['brier_score'] = float(brier_score_loss(y, scores))
    return result


def split_participants(y, groups, seed=42):
    if len(set(groups)) < 5:
        raise ValueError('At least five independently labeled participants are required for this pilot split.')
    indices = np.arange(len(y))
    trainval, test = next(GroupShuffleSplit(n_splits=1, test_size=.2,
                                            random_state=seed).split(indices, y, groups))
    train_rel, val_rel = next(GroupShuffleSplit(n_splits=1, test_size=.25,
        random_state=seed + 1).split(trainval, y[trainval], groups[trainval]))
    splits = dict(train=trainval[train_rel], validation=trainval[val_rel], test=test)
    for name, rows in splits.items():
        if set(y[rows]) != {0, 1}:
            raise ValueError(f'{name} needs examples of both quality classes; collect more participants.')
    return splits


def train(dataset, output):
    with np.load(dataset, allow_pickle=False) as data:
        red, y = data['red'], data['labels'].astype(int)
        groups, identities = data['groups'].astype(str), data['ids'].astype(str)
        domain = str(data['domain'].item())
        if int(data['sample_rate_hz']) != RATE or red.shape != (len(y), WINDOW_SAMPLES):
            raise ValueError('Dataset must contain complete ten-second red-channel windows at 25 Hz.')
        if set(y) != {0, 1} or len(identities) != len(set(identities)):
            raise ValueError('Dataset needs distinct window IDs and binary 0/1 quality labels.')
        ir = data['ir'] if 'ir' in data else None
    features = np.asarray([extract_features(wave) for wave in red])
    splits = split_participants(y, groups)
    train_rows, val, test = (splits[name] for name in ('train', 'validation', 'test'))
    candidates = []
    for depth in (6, 10, None):
        estimator = RandomForestClassifier(n_estimators=200, max_depth=depth,
            min_samples_leaf=3, class_weight='balanced', random_state=42, n_jobs=2)
        estimator.fit(features[train_rows], y[train_rows])
        score = float(f1_score(y[val], estimator.predict(features[val]), average='macro'))
        candidates.append((score, estimator))
    score, estimator = max(candidates, key=lambda item: item[0])
    # The final test set is used only after selecting depth on validation data.
    probability = estimator.predict_proba(features[test])[:, 1]
    predicted = estimator.predict(features[test])
    dummy = DummyClassifier(strategy='most_frequent').fit(features[train_rows], y[train_rows])
    output.parent.mkdir(parents=True, exist_ok=True)
    version = 'ppg-rf-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    artifact = dict(estimator=estimator, feature_version=FEATURE_VERSION,
        feature_names=list(FEATURE_NAMES), sample_rate_hz=RATE, window_samples=WINDOW_SAMPLES,
        domain=domain, model_version=version, mode='shadow', channel='red',
        dataset_sha256=hashlib.sha256(dataset.read_bytes()).hexdigest())
    joblib.dump(artifact, output)
    report = dict(model_version=version, domain=domain, seed=42,
        dataset_sha256=artifact['dataset_sha256'], model_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        samples=len(y), participants=len(set(groups)), feature_names=list(FEATURE_NAMES),
        hyperparameters=estimator.get_params(), validation_macro_f1=score,
        splits={name: dict(participants=sorted(set(groups[rows])),
                          ids=identities[rows].tolist(), samples=len(rows),
                          class_counts=np.bincount(y[rows], minlength=2).tolist())
                for name, rows in splits.items()},
        test=metrics(y[test], predicted, probability),
        majority_baseline=metrics(y[test], dummy.predict(features[test])),
        feature_importance=dict(zip(FEATURE_NAMES, estimator.feature_importances_.tolist())),
        limitations=['Signal quality for pulse analysis; does not validate SpO2 accuracy.',
                     'Public smartphone results do not establish MAX30102 performance.',
                     'Scores have not been calibrated for clinical decisions.'])
    if ir is not None:
        legacy = []
        for red_wave, ir_wave in zip(red[test], ir[test]):
            # Match the current minimum contact/amplitude guard, rather than
            # training labels from this guard.
            legacy.append(int(min(red_wave.min(), ir_wave.min()) >= 50000
                              and max(red_wave.max(), ir_wave.max()) < 262143
                              and np.ptp(ir_wave) >= 1000
                              and np.ptp(ir_wave) / max(ir_wave.mean(), 1) * 100 >= .1))
        report['existing_quality_guard'] = metrics(y[test], np.asarray(legacy))
    output.with_suffix('.report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    with output.with_suffix('.test.csv').open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['id', 'participant', 'true_label', 'predicted_label', 'usable_score'])
        writer.writerows(zip(identities[test], groups[test], y[test], predicted, probability))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(5, 4), constrained_layout=True)
    matrix = np.asarray(report['test']['confusion_matrix'])
    ax.imshow(matrix, cmap='Blues')
    for (row, col), value in np.ndenumerate(matrix):
        ax.text(col, row, str(value), ha='center', va='center',
                color='white' if value > matrix.max() / 2 else 'black')
    ax.set(xticks=[0, 1], yticks=[0, 1], xticklabels=['Unreliable', 'Usable'],
           yticklabels=['Unreliable', 'Usable'], xlabel='Predicted', ylabel='Reviewed label',
           title='Participants excluded from training')
    fig.savefig(output.with_suffix('.confusion.png'), dpi=160)
    plt.close(fig)
    print(json.dumps({key: report[key] for key in ('model_version', 'domain', 'samples', 'participants', 'test')}, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--butppg', type=Path)
    source.add_argument('--windows', type=Path, help='Reviewed local NPZ from ml.prepare_local')
    parser.add_argument('--output', type=Path, default=Path('models/ppg_quality.joblib'))
    args = parser.parse_args()
    train(public_dataset(args.butppg) if args.butppg else args.windows, args.output)


if __name__ == '__main__':
    main()
