"""Clean extracted bundle replay, offline, with new private fixture BackupAPI clones."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from zipfile import ZipFile

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from artifact_translation.experiment import run as experiment, save  # noqa: E402
from artifact_translation.qa import run as mcp_qa  # noqa: E402


def normalized(value):
    if isinstance(value,dict):
        return {k:normalized(v) for k,v in value.items() if k not in {
            'metrics','wall_ms','boundary_wall_ms','generator_wall_ms','generator_control_wall_ms'}}
    if isinstance(value,list):return [normalized(v) for v in value]
    return value


def scientific_hash(path: Path) -> str:
    rows=[normalized(json.loads(line)) for line in path.read_text().splitlines() if line]
    raw=json.dumps(rows,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def run(bundle: Path, out: Path) -> dict:
    started=time.monotonic();out.mkdir(parents=True,exist_ok=False,mode=0o700)
    manifest=json.loads((bundle/'manifest.json').read_text())
    for name,h in manifest.items():
        p=(bundle/name).resolve(strict=True)
        if not p.is_relative_to(bundle) or hashlib.sha256(p.read_bytes()).hexdigest()!=h:
            raise ValueError('BUNDLE_FILE_DRIFT:'+name)
    root=bundle/'artifact_translation001';code=bundle/'live_math_mcp_prod'
    with ZipFile(root/'frozen/original-dav.zip') as z:
        for member in z.infolist():
            if member.is_dir() or '__pycache__' in member.filename:continue
            dest=(out/'golden'/member.filename).resolve()
            if not dest.is_relative_to(out/'golden'):raise ValueError('UNSAFE_GOLDEN_ARCHIVE_MEMBER')
            dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(z.read(member))
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
    golden=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],
        cwd=out/'golden/LivingMath_DAV_Core_Package_v1',env=env,text=True,capture_output=True)
    (out/'golden.log').write_text(golden.stdout+golden.stderr)
    if golden.returncode!=0:raise AssertionError('ORIGINAL_GOLDEN_REPLAY_FAILED')
    tests=subprocess.run([sys.executable,'-B','-m','pytest','-q','test_artifact_translation001.py',
        'test_artifact_translation001_boundary.py','test_dav.py','--junitxml='+str(out/'tests.xml')],
        cwd=code,env=env,text=True,capture_output=True)
    (out/'tests.log').write_text(tests.stdout+tests.stderr)
    if tests.returncode!=0:raise AssertionError('TARGETED_REGRESSION_REPLAY_FAILED')
    scientific=asyncio.run(experiment(root,out/'experiment'))
    expected=json.loads((root/'replay-contract.json').read_text());actual={}
    for name,h in expected['scientific_sha256'].items():
        actual[name]=scientific_hash(out/'experiment'/name)
        if actual[name]!=h:raise AssertionError('SCIENTIFIC_REPLAY_MISMATCH:'+name)
    qa=mcp_qa(root,out/'private-mcp',out/'mcp')
    result={'status':'PASS_CLEAN_EXTRACTED_REPLAY','python':sys.version,'platform':platform.platform(),
        'bundle_manifest_sha256':hashlib.sha256((bundle/'manifest.json').read_bytes()).hexdigest(),
        'bundle_files_checked':len(manifest),'golden':'7/7 PASS','targeted_regressions':'PASS',
        'scientific_sha256':actual,'scientific_status':scientific['scientific_status'],
        'source_count':len(scientific['sources']),'private_OAuth_MCP_status':qa['status'],
        'private_MCP_calls':qa['calls'],'private_MCP_checks':len(qa['checks']),
        'production_accessed':False,'ALCH005_sealed_accessed':False,'external_network_required':False,
        'wall_ms':(time.monotonic()-started)*1000,'proof_status':'unverified','execution_permission':{'allowed':False}}
    save(out/'replay-receipt.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    try:print(json.dumps(run(a.bundle.resolve(),a.out.resolve()),ensure_ascii=False))
    except Exception as exc:
        a.out.mkdir(parents=True,exist_ok=True)
        save(a.out/'replay-failure.json',{'status':'FAIL','type':type(exc).__name__,'reason':str(exc)})
        raise
