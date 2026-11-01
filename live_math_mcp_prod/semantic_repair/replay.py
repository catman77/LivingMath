"""Clean source-study replay. No repeated production/full-suite/MCP infrastructure run."""
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from artifact_genesis.source import save  # noqa: E402
from artifact_genesis.journal import Journal  # noqa: E402
from artifact_translation.replay import scientific_hash  # noqa: E402
from semantic_repair.experiment import run as study, run005, run006, run007  # noqa: E402


def run(bundle: Path, out: Path) -> dict:
    start = time.monotonic(); out.mkdir(parents=True, exist_ok=False, mode=0o700)
    for n, h in json.loads((bundle/'manifest.json').read_text()).items():
        p = (bundle/n).resolve(strict=True)
        if not p.is_relative_to(bundle) or hashlib.sha256(p.read_bytes()).hexdigest() != h:
            raise ValueError('CAPSULE_DRIFT:'+n)
    if (bundle/'typed_realization008').exists():
        return replay008(bundle,out,start)
    if (bundle/'pipeline_repair007').exists():
        return replay007(bundle,out,start)
    if (bundle/'source_alignment006').exists():
        return replay006(bundle,out,start)
    if (bundle/'observer_closure005').exists():
        return replay005(bundle,out,start)
    root = bundle/'semantic_repair004'; code = bundle/'live_math_mcp_prod'
    baseline = out/'baseline003'; baseline.mkdir()
    with ZipFile(root/'frozen/baseline003.zip') as z:
        for n in z.namelist():
            if not (baseline/n).resolve().is_relative_to(baseline): raise ValueError('UNSAFE_OLD_MEMBER')
        z.extractall(baseline)
    old = baseline/'SEMANTIC_GROUNDING_003'
    # Real old negative artifacts are checked; their 22 targeted tests run against
    # their own immutable source/data, rather than rewriting any historical file.
    prior = json.loads((old/'semantic_grounding003/result.json').read_text())
    if prior['G3'] != 'FAIL': raise ValueError('HISTORICAL_G3_DRIFT')
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE':'1'}
    previous = subprocess.run([sys.executable,'-B','-m','pytest','-q','test_semantic_grounding003.py','test_semantic_grounding003_boundary.py'],
        cwd=old/'live_math_mcp_prod',env=env,text=True,capture_output=True)
    (out/'old003-tests.log').write_text(previous.stdout+previous.stderr)
    if previous.returncode: raise ValueError('OLD003_REGRESSION_FAILED')
    checks = subprocess.run([sys.executable,'-B','-m','pytest','-q','test_semantic_repair004.py','test_semantic_repair004_boundary.py',
        'test_artifact_translation001.py','test_artifact_translation001_boundary.py','test_artifact_genesis002.py',
        'test_artifact_genesis002_boundary.py','test_dav.py','--junitxml='+str(out/'tests.xml')],
        cwd=code,env=env,text=True,capture_output=True)
    (out/'tests.log').write_text(checks.stdout+checks.stderr)
    if checks.returncode: raise ValueError('TARGETED_REGRESSION_FAILED')
    result = asyncio.run(study(root,out/'experiment'))
    expected = json.loads((root/'replay-contract.json').read_text()); actual = {}
    for n,h in expected['scientific_sha256'].items():
        actual[n] = scientific_hash(out/'experiment'/n)
        if actual[n] != h: raise ValueError('STUDY_REPLAY_MISMATCH:'+n)
    # The one actual private MCP cohort was completed before packaging. Its
    # complete trace/schema/row hashes are integrity-bound, not called a replay.
    mcp = json.loads((root/'evidence/private-mcp/result.json').read_text())
    if mcp['status'] != 'PASS_REAL_PRIVATE_OAUTH_MCP': raise ValueError('PRIMARY_PRIVATE_MCP_DID_NOT_PASS')
    receipt = {'status':'PASS_EXACT_EXTRACTED_STUDY_REPLAY','bounded_source_composition':result['bounded_source_composition'],
        'old_G3_003':'FAIL','Q3':result['gates']['Q3'],'scientific_sha256':actual,
        'primary_MCP_recorded_status':mcp['status'],'MCP_repeated_in_replay':False,
        'inherited_full_suite_repeated':False,'journal':Journal.verify(out/'experiment/research-journal.jsonl'),
        'source_tree':str(code),'python':sys.version,'bundle_manifest_sha256':hashlib.sha256((bundle/'manifest.json').read_bytes()).hexdigest(),
        'production_accessed':False,'ALCH005_closed_accessed':False,'network_required':False,
        'wall_ms':(time.monotonic()-start)*1000,'proof_status':'unverified','execution_permission':{'allowed':False}}
    save(out/'replay-receipt.json',receipt); return receipt


def replay005(bundle: Path, out: Path, start: float) -> dict:
    root=bundle/'observer_closure005'; code=bundle/'live_math_mcp_prod'
    olddir=out/'immutable004'; olddir.mkdir()
    with ZipFile(root/'frozen/baseline004.zip') as z:
        for n in z.namelist():
            if not (olddir/n).resolve().is_relative_to(olddir): raise ValueError('UNSAFE_OLD_MEMBER')
        z.extractall(olddir)
    old=olddir/'SEMANTIC_REPAIR_004'
    historical=json.loads((old/'semantic_repair004/result.json').read_text())
    if historical['gates']['Q3']!='FAIL': raise ValueError('HISTORICAL_004_Q3_DRIFT')
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
    for label,cwd,targets in [
        ('immutable004',old/'live_math_mcp_prod',['test_semantic_repair004.py','test_semantic_repair004_boundary.py']),
        ('current',code,['test_observer_closure005.py','test_semantic_repair004.py','test_semantic_repair004_boundary.py',
            'test_artifact_translation001.py','test_artifact_translation001_boundary.py','test_artifact_genesis002.py',
            'test_artifact_genesis002_boundary.py','test_dav.py'])]:
        proc=subprocess.run([sys.executable,'-B','-m','pytest','-q',*targets,'--junitxml='+str(out/(label+'.xml'))],
            cwd=cwd,env=env,text=True,capture_output=True)
        (out/(label+'-tests.log')).write_text(proc.stdout+proc.stderr)
        if proc.returncode: raise ValueError('TARGETED_REGRESSION_FAILED:'+label)
    result=asyncio.run(run005(root,out/'experiment'))
    expected=json.loads((root/'replay-contract.json').read_text()); actual={}
    for name,h in expected['scientific_sha256'].items():
        actual[name]=scientific_hash(out/'experiment'/name)
        if actual[name]!=h: raise ValueError('STUDY_REPLAY_MISMATCH:'+name)
    mcp=json.loads((root/'evidence/private-mcp/result.json').read_text())
    if mcp['status']!='PASS_REAL_PRIVATE_OAUTH_MCP': raise ValueError('PRIMARY_MCP_FAILED')
    receipt={'status':'PASS_EXACT_EXTRACTED_STUDY_REPLAY','scientific_status':result['status'],
        'gates':result['gates'],'scientific_sha256':actual,'primary_MCP_recorded_status':mcp['status'],
        'MCP_repeated_in_replay':False,'inherited_full_suite_repeated':False,
        'journal':Journal.verify(out/'experiment/research-journal.jsonl'),
        'source_tree':str(code),'python':sys.version,'network_required':False,'production_accessed':False,
        'ALCH005_closed_accessed':False,'wall_ms':(time.monotonic()-start)*1000,
        'proof_status':'unverified','execution_permission':{'allowed':False}}
    save(out/'replay-receipt.json',receipt); return receipt


def replay006(bundle: Path, out: Path, start: float) -> dict:
    root=bundle/'source_alignment006';code=bundle/'live_math_mcp_prod';olddir=out/'immutable005';olddir.mkdir()
    with ZipFile(root/'frozen/baseline005.zip') as z:
        for n in z.namelist():
            if not (olddir/n).resolve().is_relative_to(olddir):raise ValueError('UNSAFE_OLD_MEMBER')
        z.extractall(olddir)
    old=olddir/'OBSERVER_CLOSURE_005'
    historical=json.loads((old/'observer_closure005/result.json').read_text())
    if [historical['gates'][k] for k in ['C3','C4']]!=['FAIL','FAIL']:raise ValueError('HISTORICAL_005_DRIFT')
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
    for label,cwd,targets in [('immutable005',old/'live_math_mcp_prod',[
        'test_observer_closure005.py','test_semantic_repair004.py','test_semantic_repair004_boundary.py']),
        ('current',code,['test_source_alignment006.py','test_observer_closure005.py','test_semantic_repair004.py',
            'test_semantic_repair004_boundary.py','test_artifact_translation001.py','test_artifact_translation001_boundary.py',
            'test_artifact_genesis002.py','test_artifact_genesis002_boundary.py','test_dav.py'])]:
        proc=subprocess.run([sys.executable,'-B','-m','pytest','-q',*targets,'--junitxml='+str(out/(label+'.xml'))],
            cwd=cwd,env=env,text=True,capture_output=True)
        (out/(label+'-tests.log')).write_text(proc.stdout+proc.stderr)
        if proc.returncode:raise ValueError('TARGETED_REGRESSION_FAILED:'+label)
    result=asyncio.run(run006(root,out/'experiment'))
    expected=json.loads((root/'replay-contract.json').read_text());actual={}
    for name,h in expected['scientific_sha256'].items():
        actual[name]=scientific_hash(out/'experiment'/name)
        if actual[name]!=h:raise ValueError('STUDY_REPLAY_MISMATCH:'+name)
    mcp=json.loads((root/'evidence/private-mcp/result.json').read_text())
    if mcp['status']!='PASS_REAL_PRIVATE_OAUTH_MCP':raise ValueError('PRIMARY_MCP_FAILED')
    receipt={'status':'PASS_EXACT_EXTRACTED_STUDY_REPLAY','scientific_status':result['scientific_status'],
        'scientific_sha256':actual,'primary_MCP_recorded_status':mcp['status'],'MCP_repeated_in_replay':False,
        'inherited_full_suite_repeated':False,'journal':Journal.verify(out/'experiment/research-journal.jsonl'),
        'source_tree':str(code),'python':sys.version,'production_accessed':False,'ALCH005_closed_accessed':False,
        'network_required':False,'wall_ms':(time.monotonic()-start)*1000,'proof_status':'unverified','execution_permission':{'allowed':False}}
    save(out/'replay-receipt.json',receipt);return receipt


def replay007(bundle: Path, out: Path, start: float) -> dict:
    root=bundle/'pipeline_repair007';code=bundle/'live_math_mcp_prod';old=out/'immutable006';old.mkdir()
    with ZipFile(root/'frozen/baseline006.zip') as z:
        for n in z.namelist():
            if not (old/n).resolve().is_relative_to(old):raise ValueError('UNSAFE_HISTORICAL_MEMBER')
        z.extractall(old)
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
    groups=[('immutable006',old/'SOURCE_ALIGNMENT_006/live_math_mcp_prod',[
        'test_source_alignment006.py','test_observer_closure005.py','test_semantic_repair004.py','test_semantic_repair004_boundary.py']),
        ('current',code,['test_pipeline_repair007.py','test_soundness007.py','test_source_alignment006.py','test_observer_closure005.py',
            'test_semantic_repair004.py','test_semantic_repair004_boundary.py','test_artifact_translation001.py',
            'test_artifact_translation001_boundary.py','test_artifact_genesis002.py','test_artifact_genesis002_boundary.py','test_dav.py'])]
    for label,cwd,tests in groups:
        test_env={**env,'LM_AUDIT_CODE':str(cwd)}
        proc=subprocess.run([sys.executable,'-B','-m','pytest','-q',*tests,'--junitxml='+str(out/(label+'.xml'))],
            cwd=cwd,env=test_env,text=True,capture_output=True)
        (out/(label+'-tests.log')).write_text(proc.stdout+proc.stderr)
        if proc.returncode:raise ValueError('TARGETED_REGRESSION_FAILED:'+label)
    result=asyncio.run(run007(root,out/'experiment'))
    expected=json.loads((root/'replay-contract.json').read_text());actual={}
    for name,h in expected['scientific_sha256'].items():
        actual[name]=scientific_hash(out/'experiment'/name)
        if actual[name]!=h:raise ValueError('SCIENTIFIC_REPLAY_MISMATCH:'+name)
    if result!=json.loads((root/'experiment/result.json').read_text()):raise ValueError('DYNAMIC_RESULT_REPLAY_MISMATCH')
    mcp=json.loads((root/'evidence/private-mcp/result.json').read_text())
    if mcp['status']!='PASS_REAL_PRIVATE_OAUTH_MCP':raise ValueError('PRIMARY_PRIVATE_MCP_NOT_AVAILABLE')
    receipt={'status':'PASS_EXACT_EXTRACTED_PIPELINE_REPLAY','result':result,'scientific_sha256':actual,
        'primary_MCP_recorded_status':mcp['status'],'MCP_repeated':False,'full_suite_repeated':False,
        'journal':Journal.verify(out/'experiment/research-journal.jsonl'),'production_accessed':False,
        'ALCH005_closed_accessed':False,'network_required':False,'source_tree':str(code),
        'wall_ms':(time.monotonic()-start)*1000,'proof_status':'unverified','execution_permission':{'allowed':False}}
    save(out/'replay-receipt.json',receipt);return receipt


def replay008(bundle: Path, out: Path, start: float) -> dict:
    from semantic_repair.study008 import run008
    root=bundle/'typed_realization008';code=bundle/'live_math_mcp_prod'
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','LM_AUDIT_CODE':str(code)}
    tests=['test_typed_realization008.py','test_pipeline_repair007.py','test_soundness007.py',
        'test_source_alignment006.py','test_observer_closure005.py','test_semantic_repair004.py',
        'test_semantic_repair004_boundary.py','test_artifact_translation001.py',
        'test_artifact_translation001_boundary.py','test_artifact_genesis002.py','test_artifact_genesis002_boundary.py','test_dav.py']
    proc=subprocess.run([sys.executable,'-B','-m','pytest','-q',*tests,'--junitxml='+str(out/'tests.xml')],
        cwd=code,env=env,text=True,capture_output=True)
    (out/'tests.log').write_text(proc.stdout+proc.stderr)
    if proc.returncode:raise ValueError('TYPED_EXTRACTED_TARGETED_TESTS_FAILED')
    result=asyncio.run(run008(root,out/'experiment'))
    expected=json.loads((root/'replay-contract.json').read_text());actual={}
    for name,h in expected['scientific_sha256'].items():
        actual[name]=scientific_hash(out/'experiment'/name)
        if actual[name]!=h:raise ValueError('TYPED_SCIENTIFIC_REPLAY_MISMATCH:'+name)
    if result!=json.loads((root/'experiment/result.json').read_text()):raise ValueError('TYPED_RESULT_REPLAY_MISMATCH')
    mcp=json.loads((root/'evidence/private-mcp/result.json').read_text())
    if mcp['status']!='PASS_REAL_PRIVATE_OAUTH_MCP':raise ValueError('TYPED_PRIMARY_MCP_FAILED')
    receipt={'status':'PASS_EXACT_EXTRACTED_TYPED_REPLAY','result':result,'scientific_sha256':actual,
        'primary_MCP_recorded_status':mcp['status'],'MCP_repeated':False,'full_suite_repeated':False,
        'targeted_tests_repeated':tests,'journal':Journal.verify(out/'experiment/research-journal.jsonl'),
        'source_tree':str(code),'production_accessed':False,'ALCH005_closed_accessed':False,'network_required':False,
        'wall_ms':(time.monotonic()-start)*1000,'proof_status':'unverified','execution_permission':{'allowed':False}}
    save(out/'replay-receipt.json',receipt);return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    try: print(json.dumps(run(a.bundle.resolve(),a.out.resolve()),ensure_ascii=False))
    except Exception as e:
        a.out.mkdir(parents=True,exist_ok=True);save(a.out/'replay-failure.json',{'status':'FAIL','type':type(e).__name__,'reason':str(e)});raise
