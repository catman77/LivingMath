"""Check payload hashes and execute offline regressions in separate processes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--integrity-only', action='store_true')
    p.add_argument('--report', type=Path)
    args = p.parse_args()
    manifest = json.loads((ROOT/'MANIFEST.json').read_text())
    failures = []
    for name, expected in manifest['files'].items():
        path = ROOT/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            failures.append(name)
    baseline = json.loads((ROOT/'code/PACKAGE_MANIFEST.json').read_text())
    for name, expected in baseline['files'].items():
        path = ROOT/'code'/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            failures.append('frozen:'+name)
    checks = []
    if not failures and not args.integrity_only:
        for path in ['code/experiments/llm_white_star',
                     'code/experiments/llm_white_star_formal',
                     'code/experiments/llm_white_star_transfer', 'integration']:
            cmd = [sys.executable, '-m', 'unittest', 'discover', '-s', path, '-p', 'test_*.py', '-v']
            run = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=60)
            checks.append(dict(path=path, command=cmd, exit_code=run.returncode,
                               stdout=run.stdout, stderr=run.stderr))
            print(path+': '+('PASS' if run.returncode == 0 else 'FAIL'))
    report = dict(integrity_failures=failures, checks=checks,
                  passed=not failures and all(c['exit_code'] == 0 for c in checks),
                  scope='offline numeric/reference/adapter checks; not live MCP integration')
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    if failures: print(json.dumps(report, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
