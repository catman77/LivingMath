"""Independent replay of immutable 001/002 plus the new source-grounding study."""
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
from semantic_grounding.experiment import run as experiment  # noqa: E402
from semantic_grounding.qa import run as qa  # noqa: E402


def run(bundle: Path, out: Path) -> dict:
    started = time.monotonic()
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    for name, expected in json.loads((bundle / 'manifest.json').read_text()).items():
        p = (bundle / name).resolve(strict=True)
        if not p.is_relative_to(bundle) or hashlib.sha256(p.read_bytes()).hexdigest() != expected:
            raise ValueError('BUNDLE_DRIFT:' + name)
    root = bundle / 'semantic_grounding003'; code = bundle / 'live_math_mcp_prod'
    old = out / 'baseline002'; old.mkdir()
    with ZipFile(root / 'frozen/baseline002.zip') as z:
        for name in z.namelist():
            if not (old / name).resolve().is_relative_to(old):
                raise ValueError('UNSAFE_BASELINE_MEMBER')
        z.extractall(old)
    old = old / 'ARTIFACT_GENESIS_002'
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'LM_AG_REPLAY_PYTHON': sys.executable}
    previous = subprocess.run(['bash', 'reproduce.sh', str(out / 'old002-replay')],
                              cwd=old, env=env, text=True, capture_output=True)
    (out / 'old002-replay.log').write_text(previous.stdout + previous.stderr)
    if previous.returncode != 0:
        raise ValueError('IMMUTABLE_002_REPLAY_FAILED')
    prior = json.loads((out / 'old002-replay/replay-receipt.json').read_text())
    if prior['G3'] != 'FAIL' or prior['old001_G3'] != 'FAIL_NO_NEW_STRUCTURAL_TRANSFER':
        raise ValueError('HISTORICAL_NEGATIVE_RESULT_DRIFT')
    tests = subprocess.run([sys.executable, '-B', '-m', 'pytest', '-q',
        'test_semantic_grounding003.py', 'test_semantic_grounding003_boundary.py',
        'test_artifact_genesis002.py', 'test_artifact_genesis002_boundary.py',
        'test_artifact_translation001.py', 'test_artifact_translation001_boundary.py', 'test_dav.py',
        '--junitxml=' + str(out / 'tests.xml')], cwd=code, env=env, text=True, capture_output=True)
    (out / 'tests.log').write_text(tests.stdout + tests.stderr)
    if tests.returncode != 0:
        raise ValueError('GROUNDING_REGRESSION_REPLAY_FAILED')
    result = asyncio.run(experiment(root, out / 'experiment'))
    expected = json.loads((root / 'replay-contract.json').read_text())
    actual = {}
    for name, h in expected['scientific_sha256'].items():
        actual[name] = scientific_hash(out / 'experiment' / name)
        if actual[name] != h:
            raise ValueError('SCIENTIFIC_REPLAY_MISMATCH:' + name)
    if result['software_status'] != 'PASS' or result['G3'] != 'FAIL':
        raise ValueError('SOFTWARE_OR_SCIENTIFIC_GATING_MISMATCH')
    source001 = out / 'old002-replay/baseline001/ARTIFACT_TRANSLATION_001/artifact_translation001'
    mcp = qa(source001, out / 'experiment', out / 'private-mcp', out / 'mcp')
    receipt = {'status': 'PASS_CLEAN_EXTRACTED_GROUNDING_REPLAY',
        'scientific_status': result['scientific_status'], 'G3': result['G3'],
        'semantic_review': result['semantic_review'], 'old002_G3': prior['G3'], 'old001_G3': prior['old001_G3'],
        'scientific_sha256': actual, 'private_MCP': {'status': mcp['status'], 'calls': mcp['calls'], 'checks': len(mcp['checks'])},
        'journal': Journal.verify(out / 'experiment/research-journal.jsonl'),
        'bundle_manifest_sha256': hashlib.sha256((bundle / 'manifest.json').read_bytes()).hexdigest(),
        'source_tree': str(code), 'python': sys.version,
        'production_accessed': False, 'ALCH005_sealed_or_key_accessed': False,
        'network_required_except_loopback': False, 'wall_ms': (time.monotonic() - started) * 1000,
        'proof_status': 'unverified', 'execution_permission': {'allowed': False}}
    save(out / 'replay-receipt.json', receipt)
    return receipt


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--bundle', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    try:
        print(json.dumps(run(a.bundle.resolve(), a.out.resolve()), ensure_ascii=False))
    except Exception as e:
        a.out.mkdir(parents=True, exist_ok=True)
        save(a.out / 'replay-failure.json', {'status': 'FAIL', 'reason': str(e), 'type': type(e).__name__})
        raise
