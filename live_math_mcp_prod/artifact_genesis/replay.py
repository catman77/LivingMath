"""Independent clean extraction: frozen 001, raw genesis, source checks and real MCP."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from zipfile import ZipFile

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from artifact_genesis.experiment import run as experiment  # noqa: E402
from artifact_genesis.qa import run as qa  # noqa: E402
from artifact_genesis.source import save  # noqa: E402
from artifact_genesis.journal import Journal  # noqa: E402
from artifact_translation.replay import scientific_hash  # noqa: E402


def run(bundle: Path,out: Path) -> dict:
    started=time.monotonic();out.mkdir(parents=True,exist_ok=False,mode=0o700)
    for name,expected in json.loads((bundle/'manifest.json').read_text()).items():
        p=(bundle/name).resolve(strict=True)
        if not p.is_relative_to(bundle) or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:raise ValueError('BUNDLE_DRIFT:'+name)
    root=bundle/'artifact_genesis002';code=bundle/'live_math_mcp_prod'
    baseline=out/'baseline001';baseline.mkdir()
    with ZipFile(root/'frozen/baseline001.zip') as z:
        for name in z.namelist():
            if not(baseline/name).resolve().is_relative_to(baseline):raise ValueError('UNSAFE_BASELINE_MEMBER')
        z.extractall(baseline)
    baseline=baseline/'ARTIFACT_TRANSLATION_001'
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','LM_AT_REPLAY_PYTHON':sys.executable}
    old=subprocess.run(['bash','reproduce.sh',str(out/'old-replay')],cwd=baseline,env=env,text=True,capture_output=True)
    (out/'old-replay.log').write_text(old.stdout+old.stderr)
    if old.returncode!=0:raise ValueError('IMMUTABLE_001_REPLAY_FAILED')
    oldresult=json.loads((out/'old-replay/experiment/result.json').read_text())
    if oldresult['gates']['G3']!='FAIL_NO_NEW_STRUCTURAL_TRANSFER':raise ValueError('OLD_G3_RESULT_CHANGED')
    tests=subprocess.run([sys.executable,'-B','-m','pytest','-q','test_artifact_genesis002.py','test_artifact_genesis002_boundary.py',
        'test_artifact_translation001.py','test_artifact_translation001_boundary.py','test_dav.py','--junitxml='+str(out/'tests.xml')],
        cwd=code,env=env,text=True,capture_output=True)
    (out/'tests.log').write_text(tests.stdout+tests.stderr)
    if tests.returncode!=0:raise ValueError('GENESIS_REGRESSION_REPLAY_FAILED')
    result=asyncio.run(experiment(root,out/'experiment'))
    expected=json.loads((root/'replay-contract.json').read_text());actual={}
    for name,h in expected['scientific_sha256'].items():
        actual[name]=scientific_hash(out/'experiment'/name)
        if actual[name]!=h:raise ValueError('SCIENTIFIC_REPLAY_MISMATCH:'+name)
    mcp=qa(root,out/'experiment',baseline/'artifact_translation001',out/'private-mcp',out/'mcp')
    receipt={'status':'PASS_CLEAN_EXTRACTED_GENESIS_REPLAY','scientific_status':result['scientific_status'],
        'G3':result['G3'],'semantic_review':result['semantic_review'],'old001_G3':oldresult['gates']['G3'],
        'scientific_sha256':actual,'private_mcp_status':mcp['status'],'private_mcp_calls':mcp['calls'],
        'private_mcp_checks':len(mcp['checks']),'journal':Journal.verify(out/'experiment/research-journal.jsonl'),
        'source_tree':str(Path(__file__).resolve().parent.parent),'python':sys.version,
        'bundle_manifest_sha256':hashlib.sha256((bundle/'manifest.json').read_bytes()).hexdigest(),
        'production_accessed':False,'ALCH005_sealed_accessed':False,'network_required_except_loopback':False,
        'wall_ms':(time.monotonic()-started)*1000,'proof_status':'unverified','execution_permission':{'allowed':False}}
    save(out/'replay-receipt.json',receipt);return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    try:print(json.dumps(run(a.bundle.resolve(),a.out.resolve()),ensure_ascii=False))
    except Exception as e:
        a.out.mkdir(parents=True,exist_ok=True);save(a.out/'replay-failure.json',{'status':'FAIL','reason':str(e),'type':type(e).__name__});raise
