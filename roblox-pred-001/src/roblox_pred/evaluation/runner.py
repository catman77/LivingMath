"""One frozen evaluation per output directory; synthetic smoke is never a real benchmark."""
from datetime import UTC, datetime, timedelta
from importlib.metadata import version
import json
import os
from pathlib import Path
import subprocess
import time

import numpy as np

from roblox_pred.config import digest
from roblox_pred.evaluation import metrics, temporal_split, train_threshold
from roblox_pred.features import validate_as_of
from roblox_pred.features.dataset import METRIC
from roblox_pred.models import fit_models, predict
from roblox_pred.schemas import FeatureValue, Sample, target_window


def synthetic_samples(seed: int) -> tuple[list[Sample], dict]:
    rng = np.random.default_rng(seed); origin = datetime(2020, 1, 1, 18, tzinfo=UTC); samples = []
    for offset, width, count in [(0, 60, 240), (151, 30, 120), (272, 30, 120)]:
        for j in range(count):
            i = len(samples); stamp = origin+timedelta(days=offset+j % width)
            start, end = target_window(stamp); signal = float(rng.lognormal(3, 1.2))
            values = {'current_players': signal, 'visits_total': signal*100,
                'favorites': None if i % 5 == 0 else signal*2, 'likes': None, 'dislikes': 0.,
                'age_days': float(i % 180), 'genre': ['Action', 'Social', None][i % 3]}
            samples.append(Sample(sample_id='synthetic-'+str(i), universe_id=i+1,
                creator_key='SYNTHETIC:'+str(i), creator_known_at=stamp, as_of=stamp, scenario='Pfirst',
                release_date=None, release_precision='UNKNOWN', cohort_frame='SYNTHETIC_ENGINEERING_ONLY',
                source_id='SYNTHETIC', source_license='GENERATED_FIXTURE_NOT_ROBLOX_DATA',
                features={k: FeatureValue(value=v, known_at=stamp, source_observed_at=stamp,
                    source_id='SYNTHETIC', source_version_sha256=digest([i, k, v]), capture_kind='SYNTHETIC')
                    for k, v in values.items()}, outcome_metric=METRIC, outcome_window_start=start,
                horizon_end=end, outcome=signal*float(rng.uniform(.7, 1.3)), outcome_days=30,
                outcome_available_at=end, synthetic=True))
    return samples, {'origin': origin.isoformat(), 'synthetic': True,
                     'manifest_sha256': digest([s.model_dump(mode='json') for s in samples])}


def freeze(path: Path, declaration: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(declaration, ensure_ascii=False, indent=2, sort_keys=True) + '\n'
    try:
        with path.open('x') as stream:
            stream.write(encoded)
    except FileExistsError:
        if path.read_text() != encoded:
            raise ValueError('FROZEN_EVALUATION_DRIFT_NEW_REGISTERED_STUDY_REQUIRED')
    return digest(declaration)


def code_hash() -> str:
    folder = Path(__file__).resolve().parents[1]
    return digest({str(p.relative_to(folder)): p.read_text() for p in sorted(folder.rglob('*.py'))})


def git_commit() -> str | None:
    value = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, check=False)
    return value.stdout.strip() if value.returncode == 0 else None


def evaluate(samples: list[Sample], manifest: dict, config: dict, output: Path, *, smoke=False) -> dict:
    started = time.monotonic()
    if not samples or any(s.synthetic != smoke for s in samples) or manifest.get('synthetic') != smoke:
        raise ValueError('REAL_SYNTHETIC_MIXING_FORBIDDEN')
    for s in samples:
        validate_as_of(s)
        if (s.outcome is None or s.outcome_days != 30 or s.censoring_flags or s.eligibility_flags
                or s.outcome_metric != config['primary_outcome'] or s.outcome_available_at is None
                or s.outcome_available_at < s.horizon_end):
            raise ValueError('DATA_GATE_INCOMPLETE_COHORT_NO_SILENT_EXCLUSION:' + s.sample_id)
        if not smoke and s.outcome_available_at > datetime.now(UTC):
            raise ValueError('FUTURE_OUTCOME_NOT_YET_AVAILABLE')
    c = config['cohort']
    folds = temporal_split(samples, datetime.fromisoformat(manifest['origin']), c['train_offsets_days'],
        c['validation_offsets_days'], c['test_offsets_days'], config['embargo_days'])
    threshold = train_threshold([s.outcome for s in folds['train']], config['top_fraction'])
    labels = {name: [int(s.outcome >= threshold) for s in group] for name, group in folds.items()}
    if not smoke:
        for name in folds:
            if len(folds[name]) < c['min_'+name]:
                raise ValueError('DATA_GATE_SMALL_FOLD:' + name)
        for name in ['train', 'test']:
            if sum(labels[name]) < c['min_'+name+'_positive']:
                raise ValueError('DATA_GATE_TOO_FEW_POSITIVES:' + name)
        if any(len(set(v)) < 2 for v in labels.values()):
            raise ValueError('DATA_GATE_NO_CLASS_CONTRAST')
    versions = {name: version(name) for name in ['numpy', 'pandas', 'scikit-learn', 'duckdb', 'pyarrow']}
    declaration = {'config': config, 'dataset_manifest': manifest,
        'samples_sha256': digest([s.model_dump(mode='json') for s in sorted(samples, key=lambda s: s.sample_id)]),
        'code_sha256': code_hash(), 'versions': versions,
        'scope': 'SYNTHETIC_ENGINEERING_ONLY' if smoke else 'REAL_BASELINE',
        'frozen_before_model_fit': True, 'train_threshold': threshold}
    experiment_id = freeze(output/'frozen-evaluation.json', declaration)
    result_path = output/'evaluation.json'
    if result_path.exists():
        result = json.loads(result_path.read_text())
        if result['experiment_id'] != experiment_id:
            raise ValueError('RESULT_FREEZE_BINDING_DRIFT')
        return result
    models = fit_models(folds['train'], labels['train'], config)
    base = float(np.mean(labels['train'])); result_metrics = {}; records = []
    from roblox_pred.schemas import Prediction
    for fold in ['validation', 'test']:
        scores = predict(models, folds[fold], config, base)
        result_metrics[fold] = {}
        for model_id, values in scores.items():
            result_metrics[fold][model_id] = metrics(labels[fold], values,
                [s.sample_id for s in folds[fold]], config['top_fraction'])
            records.extend(Prediction(record_id=digest([experiment_id, fold, model_id, s.sample_id]),
                experiment_id=experiment_id, model_id=model_id, fold=fold, sample_id=s.sample_id,
                score=float(p), calibrated_probability=None, as_of=s.as_of) for s, p in zip(folds[fold], values))
    result = {'experiment_id': experiment_id, 'scope': declaration['scope'], 'status': 'ENGINEERING_PASS' if smoke else 'BASELINE_EVALUATED',
        'research_conclusion': 'INCONCLUSIVE', 'real_predictive_metrics': None if smoke else result_metrics,
        'synthetic_metrics': result_metrics if smoke else None, 'train_threshold': threshold,
        'fold_sizes': {k: len(v) for k, v in folds.items()}, 'seed': config['seed'],
        'versions': versions, 'native_comparison': 'NOT_EXECUTED_DATA_GATE', 'revenue_or_roi': None,
        'seconds': time.monotonic()-started, 'prediction_count': len(records), 'llm_calls': 0}
    from roblox_pred.storage import Store
    from roblox_pred.schemas import Run
    store = Store(output/'tables')
    store.append('predictions', records)
    store.append('runs', [Run(record_id=experiment_id, experiment_id=experiment_id, git_commit=git_commit(),
        config_sha256=digest(config), dataset_manifest_sha256=manifest['manifest_sha256'], seed=config['seed'],
        model_versions=versions, timings={'total_seconds': result['seconds']}, status=result['status'])])
    temporary = result_path.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    os.replace(temporary, result_path)
    return result
