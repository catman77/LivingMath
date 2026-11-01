from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest

from roblox_pred.config import load_config
from roblox_pred.evaluation.runner import evaluate, synthetic_samples
from roblox_pred.models import fit_models, frame
from roblox_pred.schemas import ConceptArtifact
from roblox_pred.semantic import native_contract, unavailable
from roblox_pred.storage import Store, MODELS
from test_outcomes_import import imported
from roblox_pred.features.dataset import build_dataset

ROOT = Path(__file__).resolve().parents[1]


def config(): return load_config(ROOT/'configs/protocol.yaml')[0]


def test_smoke_evaluation_cached_and_cannot_substitute_data(tmp_path):
    cfg = config(); samples, manifest = synthetic_samples(cfg['seed'])
    result = evaluate(samples, manifest, cfg, tmp_path, smoke=True)
    assert result['scope'] == 'SYNTHETIC_ENGINEERING_ONLY'
    assert result['real_predictive_metrics'] is None and result['revenue_or_roi'] is None
    assert result == evaluate(samples, manifest, cfg, tmp_path, smoke=True)
    assert len(Store(tmp_path/'tables').rows('predictions')) == result['prediction_count']
    samples[-1] = samples[-1].model_copy(update={'outcome': 10000.})
    with pytest.raises(ValueError, match='FROZEN_EVALUATION_DRIFT'):
        evaluate(samples, manifest, cfg, tmp_path, smoke=True)


def test_real_smoke_mixing_forbidden(tmp_path):
    cfg = config(); samples, manifest = synthetic_samples(cfg['seed'])
    with pytest.raises(ValueError, match='MIXING_FORBIDDEN'):
        evaluate(samples, manifest, cfg, tmp_path, smoke=False)


def test_train_imputer_has_no_test_statistics():
    cfg = config(); samples, _ = synthetic_samples(cfg['seed'])
    train = samples[:240]
    models = fit_models(train, [int(s.outcome > 50) for s in train], cfg)
    imputer = models['M0_logistic'].named_steps['preprocess'].named_transformers_['numeric'].named_steps['impute']
    expected = np.nanmedian(frame(train, cfg)['favorites'])
    assert imputer.statistics_[2] == pytest.approx(expected)
    assert 'final_rank' not in imputer.feature_names_in_


def test_semantic_contract_contains_no_outcome_and_missing_native_is_null():
    sample = synthetic_samples(1)[0][0]
    contract = native_contract(sample, [])
    assert not {'outcome','success','horizon_end'} & contract.keys()
    result = unavailable(sample)
    assert result.status == 'UNSUPPORTED' and result.features is None and result.relations is None


def test_semantic_future_artifact_rejected():
    sample = synthetic_samples(1)[0][0]
    artifact = ConceptArtifact(record_id='x', universe_id=sample.universe_id,
        known_at=sample.as_of+timedelta(days=1), source_observed_at=sample.as_of,
        source_id='SYNTHETIC', source_license='UNIT', source_sha256='a'*64, text='unit', artifact_kind='concept')
    with pytest.raises(ValueError, match='FUTURE_ARTIFACT'): native_contract(sample, [artifact])


def test_all_seven_typed_tables_roundtrip(tmp_path):
    from roblox_pred.schemas import ConceptArtifact, Prediction, Run
    source = tmp_path/'import'; source.mkdir(); cfg = imported(source)
    samples, manifest, tables = build_dataset(source, cfg)
    sample = samples[0]
    tables['semantic_features'] = [unavailable(sample)]
    tables['concept_artifacts'] = [ConceptArtifact(record_id='c', universe_id=1, known_at=sample.as_of,
        source_observed_at=sample.as_of, source_id='test', source_license='UNIT', source_sha256='a'*64,
        text='unit fixture', artifact_kind='concept')]
    tables['predictions'] = [Prediction(record_id='p',experiment_id='unit',model_id='unit',fold='test',
        sample_id=sample.sample_id,score=.2,as_of=sample.as_of)]
    tables['runs'] = [Run(record_id='r',experiment_id='unit',git_commit=None,config_sha256='a'*64,
        dataset_manifest_sha256='b'*64,seed=1,model_versions={},timings={},status='UNIT_FIXTURE')]
    store = Store(tmp_path/'tables')
    assert set(tables) == set(MODELS)
    for name, records in tables.items():
        assert store.append(name, records)['inserted'] == len(records)
        assert Store(tmp_path/'tables').rows(name) == sorted(records, key=lambda r:r.record_id)
        assert store.append(name, records)['inserted'] == 0
