import hashlib
import json
from pathlib import Path
import subprocess
import sys

import httpx
import pytest

from roblox_pred.config import authorize, load_config, registry
from roblox_pred.sources import RobloxPublicSource

ROOT = Path(__file__).resolve().parents[1]


def approved(tmp_path):
    cfg,_ = load_config(ROOT/'configs/protocol.yaml')
    policy = registry(ROOT,cfg)['roblox_public_games']
    evidence = tmp_path/'evidence.txt'; evidence.write_text('UNIT TEST ONLY, NOT AN ACTUAL EXCEPTION')
    return policy.model_copy(update=dict(rights_status='EXPLICIT_EXCEPTION_OR_LICENSE',commercial_allowed=True,
        ml_allowed=True,collection_allowed=True,authorization_evidence='evidence.txt',
        authorization_sha256=hashlib.sha256(evidence.read_bytes()).hexdigest())), cfg


def test_license_hash_mismatch_cannot_authorize(tmp_path):
    policy,_ = approved(tmp_path); (tmp_path/'evidence.txt').write_text('changed')
    with pytest.raises(ValueError,match='EVIDENCE_DRIFT'): authorize(policy,tmp_path,collect=True)


def test_rate_limit_stops_after_one_request(tmp_path):
    policy,cfg = approved(tmp_path); calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(429, headers={'Retry-After':'120'},request=request)
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ValueError,match='RATE_LIMIT_STOP_RETRY_AFTER:120'):
            RobloxPublicSource(policy,tmp_path,cfg['audit'],client).fetch([1])
    assert len(calls) == 1


def test_authorized_mock_capture_persisted_hash_bound_and_missing_retained(tmp_path):
    policy,cfg = approved(tmp_path)
    def respond(request):
        return httpx.Response(200,json={'data':[{'id':1,'name':'unit','playing':0}]},request=request)
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        games, snaps, receipt = RobloxPublicSource(policy,tmp_path,cfg['audit'],client).fetch([1,2])
    assert snaps[0].current_players == 0 and snaps[1].current_players is None
    capture = tmp_path/receipt['raw_capture_path']
    assert hashlib.sha256(capture.read_bytes()).hexdigest() == receipt['response_sha256']


@pytest.mark.parametrize('script,extra,code,marker',[
    ('audit_sources',[],0,'RECORDED_AUDIT_REPLAY_NO_NETWORK'),
    ('audit_sources',['--live'],3,'SOURCE_RIGHTS_BLOCKED'),
    ('collect_snapshots',[],3,'SOURCE_RIGHTS_BLOCKED'),
    ('build_dataset',[],3,'NO_LICENSED_MANIFEST'),
    ('run_baseline',[],3,'NO_LICENSED_MANIFEST'),
    ('run_eval',[],3,'NO_LICENSED_MANIFEST'),
    ('run_semantic',['--dry-run'],0,'SYNTHETIC_CONTRACT_DRY_RUN'),
    ('run_semantic',[],3,'NATIVE_ROBLOX_BINDING_NOT_IDENTIFIED')])
def test_cli_honest_gates(script,extra,code,marker):
    result = subprocess.run([sys.executable,str(ROOT/'scripts'/f'{script}.py'),'--config',
        str(ROOT/'configs/protocol.yaml'),*extra],capture_output=True,text=True,timeout=30)
    assert result.returncode == code, result.stderr
    assert marker in result.stdout
    json.loads(result.stdout)
