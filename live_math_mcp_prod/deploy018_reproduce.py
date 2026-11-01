"""Verify a018 capsule and replay on empty private DBs; never reads live config."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    package = args.package.resolve(strict=True)
    manifest = json.loads((package / 'files-sha256.json').read_text())
    for name, expected in manifest.items():
        path = package / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('018_CAPSULE_HASH_MISMATCH:' + name)
    work = args.work.resolve()
    work.mkdir(mode=0o700, parents=True, exist_ok=False)
    source = Path(__file__).resolve().parent
    env = {**os.environ, 'PYTHONPATH': str(source)}
    for key in list(env):
        if key.startswith('LIVE_MATH_') or key == 'LM018_FAULT':
            env.pop(key)
    phases = [
        ('HTTPS', [sys.executable, str(source / 'deploy018_qa.py'), '--base', str(work), '--output', str(work / 'acceptance'), '--frozen', str(package / 'frozen')]),
        ('faults', [sys.executable, str(source / 'deploy018_fault_qa.py'), '--base', str(work), '--out', str(work / 'faults')]),
        ('portable_tests', [sys.executable, '-m', 'pytest', '-q', str(source / 'test_engine017.py'), str(source / 'test_deploy018.py'), str(source / 'test_deploy018_bounds.py'), str(source / 'test_deploy018_http.py')])]
    results = []
    for name, command in phases:
        if name == 'portable_tests':
            env['LM_ENGINE017_POLICY'] = str(work / 'frozen/pre-registration.json')
        with (work / (name + '.log')).open('w') as log:
            p = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=300)
        results.append({'phase': name, 'exit_code': p.returncode})
        (work / 'replay-phases.json').write_text(json.dumps(results, indent=2) + '\n')
        if p.returncode:
            raise RuntimeError('018_REPLAY_STOP_WITH_RCA:' + name)
    result = {'status': 'PASS_SAME_MACHINE_PRIVATE_REPLAY', 'deployment': 'NOT_PERFORMED', 'phases': results,
        'historical86': 'Provided original check log; fixture22 private DB is deliberately NOT bundled.',
        'independent_machine_R6': 'NOT_ESTABLISHED', 'external_source_R7': 'NOT_ESTABLISHED'}
    (work / 'replay-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
