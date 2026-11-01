from datetime import timedelta
import json

import pytest

from roblox_pred.config import load_config
from roblox_pred.evaluation import metrics, temporal_split
from roblox_pred.evaluation.runner import evaluate, synthetic_samples
from roblox_pred.features.dataset import build_dataset
from roblox_pred.sources import RobloxPublicSource
from test_governance_cli import approved, ROOT
from test_outcomes_import import imported
from test_splits import rows


def test_non_binary_fractional_label_not_truncated_to_zero():
    with pytest.raises(ValueError, match='INVALID_PROBABILITY_OR_LABEL'):
        metrics([0, .5, 1], [.1,.4,.8], ['a','b','c'])


def test_outside_fold_sample_is_not_silently_removed():
    ss=rows(); ss[-1] = ss[-1].model_copy(update={'as_of':ss[-1].as_of+timedelta(days=1000)})
    # Independently valid timestamps/window are shifted with it.
    shift=timedelta(days=1000)
    original=rows()[-1]
    ss[-1] = original.model_copy(update={'as_of':original.as_of+shift,
        'outcome_window_start':original.outcome_window_start+shift,'horizon_end':original.horizon_end+shift})
    with pytest.raises(ValueError,match='OUTSIDE_PREREGISTERED_FOLDS'):
        temporal_split(ss,ss[0].as_of,[0,60],[151,211],[302,400],91)


def test_missing_outcome_never_enters_training(tmp_path):
    cfg,_=load_config(ROOT/'configs/protocol.yaml'); samples,manifest=synthetic_samples(cfg['seed'])
    samples[-1]=samples[-1].model_copy(update={'outcome':None,'censoring_flags':['UNKNOWN']})
    with pytest.raises(ValueError,match='NO_SILENT_EXCLUSION'):
        evaluate(samples,manifest,cfg,tmp_path,smoke=True)
    assert not (tmp_path/'frozen-evaluation.json').exists()


def test_backdated_cohort_enrolment_rejected(tmp_path):
    cfg=imported(tmp_path)
    path=tmp_path/'cohort.json'; cohort=json.loads(path.read_text())
    cohort[0]['enrolled_at']='2021-01-01T18:00:00Z';path.write_text(json.dumps(cohort))
    import hashlib
    mp=tmp_path/'manifest.json'; manifest=json.loads(mp.read_text())
    manifest['files']['cohort']['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    mp.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='COHORT_SELECTED_AFTER_AS_OF'): build_dataset(tmp_path,cfg)


def test_request_budget_precedes_second_network_call(tmp_path):
    import httpx
    policy,cfg=approved(tmp_path);limits={**cfg['audit'],'max_requests':1,'interval_seconds':0};calls=[]
    def respond(request):
        calls.append(request);return httpx.Response(200,json={'data':[]},request=request)
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        source=RobloxPublicSource(policy,tmp_path,limits,client)
        source.fetch([1])
        with pytest.raises(ValueError,match='REQUEST_BUDGET_EXHAUSTED'):source.fetch([1])
    assert len(calls)==1


def test_unsupported_outcome_change_cannot_silently_use_old_aggregator(tmp_path):
    import yaml
    path = ROOT/'configs/protocol.yaml'
    cfg = yaml.safe_load(path.read_text()); cfg['outcome_first_day']=60
    altered=tmp_path/'protocol.yaml'; altered.write_text(yaml.safe_dump(cfg))
    with pytest.raises(ValueError,match='OUTCOME_NOT_IMPLEMENTED'):load_config(altered)


def test_duplicate_capture_id_cannot_supply_conflicting_outcome(tmp_path):
    import hashlib
    cfg=imported(tmp_path);path=tmp_path/'snapshots.jsonl'
    rows=path.read_text().splitlines();row=json.loads(rows[-1]);row['current_players']=100000
    path.write_text('\n'.join([*rows,json.dumps(row)])+'\n')
    mp=tmp_path/'manifest.json';manifest=json.loads(mp.read_text())
    manifest['files']['snapshots']['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    mp.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='DUPLICATE_IMPORT_RECORD_ID'):build_dataset(tmp_path,cfg)
