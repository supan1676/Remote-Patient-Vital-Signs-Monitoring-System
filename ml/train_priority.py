"""Train and evaluate three-color imitation of a documented synthetic rulebook."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from threadpoolctl import threadpool_limits

from alert_priority import FEATURE_NAMES, FEATURE_VERSION, LABELS, POLICY_VERSION


def scores(y, predicted):
    matrix = confusion_matrix(y, predicted, labels=[0, 1, 2])
    return dict(macro_f1=float(f1_score(y, predicted, average='macro')),
                confusion_matrix=matrix.tolist(),
                classes=classification_report(y, predicted, labels=[0, 1, 2],
                    target_names=LABELS, zero_division=0, output_dict=True),
                red_labeled_as_green=int(matrix[2, 0]),
                label_source='unreviewed synthetic engineering rules')


def train(dataset, output, max_iter=150, threads=4):
    started = time.monotonic()
    manifest_path = dataset / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if (not manifest.get('completed') or manifest.get('source') != 'synthetic'
            or manifest['feature_version'] != FEATURE_VERSION
            or manifest['feature_names'] != list(FEATURE_NAMES)
            or manifest['policy_version'] != POLICY_VERSION):
        raise ValueError('Dataset contract does not match this priority implementation.')
    features, labels, splits, profiles, families, patterns = (
        np.load(dataset / f'{name}.npy', mmap_mode='r', allow_pickle=False)
        for name in ('features', 'labels', 'splits', 'profiles', 'families', 'patterns'))
    indices = {name: np.flatnonzero((splits == code) & (labels >= 0))
               for code, name in enumerate(('train', 'validation', 'test'))}
    split_profiles = [set(profiles[splits == code].tolist()) for code in range(3)]
    split_families = [set(families[splits == code].tolist()) for code in range(3)]
    for i in range(3):
        if set(labels[indices[('train', 'validation', 'test')[i]]]) != {0, 1, 2}:
            raise ValueError('Each split needs all three eligible priority classes.')
        for j in range(i):
            if split_profiles[i] & split_profiles[j] or split_families[i] & split_families[j]:
                raise ValueError('Synthetic profiles or trajectory families leak between splits.')
    rng = np.random.default_rng(42)
    train_rows, validation, test = (indices[name] for name in ('train', 'validation', 'test'))
    learning_curve = []
    model = None
    with threadpool_limits(limits=threads):
        for size in sorted(set(min(n, len(train_rows)) for n in (10_000, 100_000, len(train_rows)))):
            selected = train_rows if size == len(train_rows) else np.sort(rng.choice(train_rows, size, replace=False))
            print(f'Training histogram gradient boosting on {size:,} eligible scenarios...', flush=True)
            model = HistGradientBoostingClassifier(max_iter=max_iter, max_leaf_nodes=31,
                learning_rate=.1, l2_regularization=1, class_weight='balanced',
                early_stopping=False, random_state=42)
            model.fit(features[selected], labels[selected])
            predicted = model.predict(features[validation])
            value = float(f1_score(labels[validation], predicted, average='macro'))
            learning_curve.append(dict(training_scenarios=size, validation_macro_f1=value))
            print(f'Validation macro-F1: {value:.5f}', flush=True)
        # No threshold/parameter search on the final, held-out trajectory families.
        predicted = model.predict(features[test])
        probability = model.predict_proba(features[test])
    version = 'priority-synthetic-hgb-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output.parent.mkdir(parents=True, exist_ok=True)
    artifact = dict(estimator=model, model_version=version, training_source='synthetic',
        human_reviewed=False, clinically_validated=False, policy_version=POLICY_VERSION,
        feature_version=FEATURE_VERSION, feature_names=list(FEATURE_NAMES),
        window_seconds=60, manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest())
    joblib.dump(artifact, output)
    majority = int(np.bincount(labels[train_rows], minlength=3).argmax())
    report = dict(model_version=version, training_source='synthetic', human_reviewed=False,
        clinically_validated=False, scenarios=manifest['scenarios'], timepoints=manifest['timepoints'],
        synthetic_profiles=manifest['profiles'], feature_names=list(FEATURE_NAMES),
        policy_version=POLICY_VERSION, manifest_sha256=artifact['manifest_sha256'],
        dataset_hashes=manifest['sha256'], model_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        sklearn_version=sklearn.__version__, numpy_version=np.__version__,
        generation_seed=manifest['seed'], model_seed=42, learning_curve=learning_curve,
        hyperparameters=model.get_params(),
        split_profile_ranges=manifest['split_profile_ranges'],
        split_families=manifest['split_families'], dataset_class_counts=manifest['label_counts'],
        eligible_split_sizes={name: len(rows) for name, rows in indices.items()},
        test=scores(labels[test], predicted),
        majority_baseline=scores(labels[test], np.full(len(test), majority)),
        generating_rule_baseline=dict(macro_f1=1.0,
            explanation='Perfect by construction: the rulebook defines these synthetic labels.'),
        per_test_family={}, per_test_pattern={}, duration_seconds=time.monotonic() - started,
        unknown_policy='Unknown windows are gated out, not learned as a patient-risk class.',
        limitations=manifest['limitations'] + [
            'Synthetic class scores are not probabilities of illness or safety.',
            'The generating rulebook is a simpler exact baseline for this experiment.',
            'No real-person evaluation, clinical review, or core-temperature input.'])
    for key, code_array, names in (('per_test_family', families, manifest['family_codes']),
                                  ('per_test_pattern', patterns, manifest['pattern_codes'])):
        for code in np.unique(code_array[test]):
            mask = code_array[test] == code
            report[key][names[int(code)]] = dict(samples=int(mask.sum()),
                accuracy=float(np.mean(labels[test][mask] == predicted[mask])))
    output.with_suffix('.report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    predictions = np.column_stack([test, profiles[test], labels[test], predicted, probability])
    np.savetxt(output.with_suffix('.test.csv'), predictions, delimiter=',',
               header='scenario_id,synthetic_profile,label,prediction,green_score,yellow_score,red_score',
               comments='', fmt=['%d'] * 4 + ['%.6f'] * 3)
    os.environ.setdefault('MPLCONFIGDIR', str(output.parent.resolve() / '.mplcache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    matrix = np.asarray(report['test']['confusion_matrix'])
    axes[0].imshow(matrix, cmap='Blues')
    for (row, column), value in np.ndenumerate(matrix):
        axes[0].text(column, row, f'{value:,}', ha='center', va='center',
                     color='white' if value > matrix.max() / 2 else 'black')
    axes[0].set(xticks=range(3), yticks=range(3), xticklabels=LABELS, yticklabels=LABELS,
                xlabel='Predicted', ylabel='Synthetic policy label', title='Held-out trajectory families')
    axes[1].plot([row['training_scenarios'] for row in learning_curve],
                 [row['validation_macro_f1'] for row in learning_curve], marker='o', color='#315b45')
    axes[1].set(xlabel='Training scenarios', ylabel='Validation macro-F1',
                xscale='log', title='Synthetic learning curve', ylim=(0, 1.01))
    fig.suptitle('Synthetic rule imitation — no clinical validation', fontsize=11)
    fig.savefig(output.with_suffix('.evaluation.png'), dpi=160)
    plt.close(fig)
    print(json.dumps({name: report[name] for name in ('model_version', 'scenarios', 'eligible_split_sizes', 'test', 'duration_seconds')}, indent=2), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=Path('data/synthetic-priority-v1'))
    parser.add_argument('--output', type=Path, default=Path('models/alert_priority.joblib'))
    parser.add_argument('--iterations', type=int, default=150)
    parser.add_argument('--threads', type=int, default=4)
    args = parser.parse_args()
    train(args.dataset, args.output, args.iterations, args.threads)


if __name__ == '__main__':
    main()
