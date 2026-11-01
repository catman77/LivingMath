"""Clean signed installation, actual external-source MCP story and recovery."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

from beta019_install import install, verify_package


def run(package: Path, work: Path):
    work = work.resolve(); work.mkdir(parents=True, mode=0o700, exist_ok=False)
    root = work / 'install'
    phases = []
    started = time.perf_counter_ns()
    first = install(package, root)
    phases.append({'phase': 'clean_install', 'exit_code': 0, 'wall_ns': time.perf_counter_ns() - started, 'result': first})
    second = install(package, root)
    if not second['idempotent']:
        raise ValueError('019_INSTALL_NOT_IDEMPOTENT')
    phases.append({'phase': 'repeat_install', 'exit_code': 0, 'idempotent': True})
    code, python = root / 'code', root / 'venv/bin/python'
    env = {**os.environ, 'PYTHONPATH': str(code), 'LM_ENGINE017_POLICY': str(package / 'frozen017/pre-registration.json')}
    for name in list(env):
        if name.startswith('LIVE_MATH_') or name == 'LM018_FAULT':
            env.pop(name)
    out = work / 'external-source-example'
    commands = [
        ('native_story', [str(python), str(code / 'beta019_qa.py'), '--base', str(work / 'private-work'), '--out', str(out), '--state', str(root / 'state')], 300),
        ('portable_tests', [str(python), '-m', 'pytest', '-q'] + [str(code / n) for n in ('test_engine017.py', 'test_deploy018.py', 'test_deploy018_bounds.py', 'test_deploy018_http.py', 'test_beta019.py', 'test_beta019_admin.py')], 120),
        ('network_controls', [str(python), str(code / 'beta019_security_qa.py'), '--root', str(work / 'network-install'), '--out', str(work / 'network-controls')], 120),
        ('archive_inspection', [str(python), str(code / 'beta019_admin.py'), '--root', str(root), 'inspect'], 120),
        ('export', [str(python), str(code / 'beta019_admin.py'), '--root', str(root), 'export'], 120)]
    for name, command, timeout in commands:
        before = time.perf_counter_ns()
        with (work / (name + '.log')).open('w') as log:
            p = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
        phases.append({'phase': name, 'command': command, 'exit_code': p.returncode, 'wall_ns': time.perf_counter_ns() - before})
        (work / 'phases.json').write_text(json.dumps(phases, indent=2) + '\n')
        if p.returncode:
            raise RuntimeError('019_REPRODUCE_STOP_WITH_RCA:' + name)
    exported = json.loads((work / 'export.log').read_text())['result']
    restored = subprocess.run([str(python), str(code / 'beta019_admin.py'), '--root', str(root), 'restore', '--snapshot', exported['snapshot']],
        env={**env, 'LM018_FAULT': '019_restore_after_rename'}, capture_output=True, text=True, timeout=120)
    if restored.returncode != -9:
        raise ValueError('019_RESTORE_SIGKILL_NOT_EXERCISED:' + restored.stdout + restored.stderr)
    recovered = install(package, root)
    if not recovered['schema']['result']['recovery']['recovered']:
        raise ValueError('019_NAMESPACE_RECOVERY_NOT_PERFORMED')
    phases.append({'phase': 'SIGKILL_namespace_restore_recovery', 'exit_code': -9, 'recovery': recovered, 'result': 'PASS'})
    checked = subprocess.run([str(python), str(code / 'beta019_admin.py'), '--root', str(root), 'inspect'], env=env, capture_output=True, text=True, timeout=120)
    if checked.returncode:
        raise ValueError('019_RESTORED_ARCHIVE_INSPECTION_FAILED:' + checked.stdout + checked.stderr)
    (work / 'restored-inspection.json').write_text(checked.stdout)
    machine = {'os': platform.platform(), 'python': sys.version, 'machine_id_sha256': hashlib.sha256(Path('/etc/machine-id').read_bytes()).hexdigest(),
        'boot_id_sha256': hashlib.sha256(Path('/proc/sys/kernel/random/boot_id').read_bytes()).hexdigest(),
        'root_filesystem_id': os.statvfs('/').f_fsid, 'machine_identity_class': 'actual caller machine; compare against originating host before assigning R6'}
    result = {'status': 'PASS_019_PORTABLE_REPLAY', 'production_deployment': 'NOT_PERFORMED', 'package_version': '1.0.0b1',
        'machine': machine, 'phases': phases, 'source_story': json.loads((out / 'result.json').read_text()),
        'manifest_sha256': hashlib.sha256((package / 'release-manifest.json').read_bytes()).hexdigest(),
        'R5b': 'DEFERRED_BY_OWNER', 'historical86': 'SKIP_NO_PRIVATE_SNAPSHOT; local original compatibility log is separate',
        'scientific_status': 'SOURCE_FORMULA_REPLAY; NO_STRUCTURAL_ADVANTAGE; unverified', 'host_reboot': 'NOT_PERFORMED_BY_REPRODUCER; independent acceptance records separately'}
    (work / 'phases.json').write_text(json.dumps(phases, indent=2) + '\n')
    (work / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'work': str(work), 'cycles': result['source_story']['complete_cycles']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--package', type=Path, required=True); parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args.package.resolve(strict=True), args.work)
    except Exception as error:
        if args.work.exists():
            (args.work / 'first-failure.json').write_text(json.dumps({'status': 'STOP_WITH_RCA', 'error': str(error),
                'traceback': __import__('traceback').format_exc()}, indent=2) + '\n')
        raise
