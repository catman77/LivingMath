"""Finite release-only replay/reboot acceptance, never production or owner signoff.

Run replay in a fresh work directory, reboot ONLY the owned QA guest, then
finish. The019 scenario/thresholds and all scientific outcomes stay unchanged.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

from release020 import verify, sha


def write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def command(work: Path, label: str, argv: list[str], timeout: int = 120, extra: dict | None = None) -> str:
    environment = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', **(extra or {})}
    before = time.perf_counter_ns()
    process = subprocess.run(argv, capture_output=True, text=True, env=environment, timeout=timeout)
    (work / (label + '.log')).write_text(process.stdout + process.stderr)
    with (work / 'rc020-commands.jsonl').open('a') as stream:
        stream.write(json.dumps({'phase': label, 'argv': argv, 'exit_code': process.returncode,
            'wall_ns': time.perf_counter_ns() - before}) + '\n')
    if process.returncode:
        raise ValueError('020_ACCEPTANCE_PHASE_FAILED:' + label)
    return process.stdout


def inspect(work: Path, label: str) -> dict:
    root = work / 'install'
    return json.loads(command(work, label, [str(root / 'venv/bin/python'),
        str(root / 'code/beta019_admin.py'), '--root', str(root), 'inspect']))['result']


def machine() -> dict:
    return {'os': platform.platform(), 'python': sys.version,
        'machine_id_sha256': sha(Path('/etc/machine-id')),
        'boot_id_sha256': sha(Path('/proc/sys/kernel/random/boot_id')),
        'filesystem_id': os.statvfs('/').f_fsid,
        'attestation_class': 'software/VM identity; no independent human approval'}


def unchanged(previous: dict, current: dict) -> None:
    for name in ('canonical', 'typed'):
        for field in ('logical_sha256', 'schema_sha256', 'sequence', 'chain'):
            if previous[name][field] != current[name][field]:
                raise ValueError('020_STATE_CHANGED:' + name + ':' + field)
    if previous['committed_artifacts'] != current['committed_artifacts']:
        raise ValueError('020_RECEIPT_IDS_OR_SIGNATURES_CHANGED')


def replay(package: Path, work: Path) -> dict:
    if work.exists():
        raise ValueError('020_FRESH_COHORT_REQUIRED')
    process = subprocess.run([sys.executable, str(package / 'release020.py'), '--package', str(package),
        'reproduce', '--work', str(work)], env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}, timeout=600)
    if process.returncode:
        raise ValueError('020_REPLAY_FAILED')
    checkpoint = {'machine': machine(), 'state': inspect(work, 'before-reboot-inspection'),
        'release': verify(package), 'source_result': json.loads((work / 'result.json').read_text()),
        'reboot': 'PENDING_REAL_GUEST_REBOOT'}
    write(work / 'rc020-before-reboot.json', checkpoint)
    return {'status': 'PASS_REPLAY_AWAITING_REBOOT', 'committed_artifacts': len(checkpoint['state']['committed_artifacts'])}


def readonly_mcp(package: Path, work: Path) -> None:
    # Script executes in the installed SDK environment, not this stdlib helper.
    script = '''import asyncio,json,os,sqlite3
from pathlib import Path
from beta019_transport import serving,client
work=Path(os.environ['LM020_WORK']); root=work/'install'; state=root/'state'
with sqlite3.connect(state/'beta.sqlite3') as c:
 projects=[r[0] for r in c.execute('SELECT DISTINCT project FROM research_moves ORDER BY project')]
async def main():
 records=[]
 for enabled,count in [(False,24),(True,27)]:
  async with serving(state,state/'beta.sqlite3',work,'rc020-catalogue-'+str(count),enabled=enabled) as (origin,context,token,process):
   async with client(origin,context,token['access_token'],work/('rc020-wire-'+str(count)+'.jsonl')) as s:
    init=await s.initialize(); inventory=await s.list_tools(); assert len(inventory.tools)==count
    health=await s.call_tool('service_health',{}); assert not health.isError
    histories=[]
    if enabled:
     contract=await s.call_tool('research_contract',{}); assert not contract.isError
     data=contract.structuredContent or json.loads(contract.content[0].text)
     assert data['http018']['version']=='1.0.0b1' and data['http018']['protocol']=='livingmath-research019/v1'
     for project in projects:
      response=await s.call_tool('research_cycle_history',{'project':project}); assert not response.isError
      history=response.structuredContent or json.loads(response.content[0].text)
      assert all(not m['execution_permission']['allowed'] for m in history['moves'])
      histories.append({'project':project,'history':history})
    records.append({'enabled':enabled,'tool_count':count,'initialize':init.model_dump(mode='json'),'tools':inventory.model_dump(mode='json'),'health':health.model_dump(mode='json'),'histories':histories})
 (work/'rc020-catalogue.json').write_text(json.dumps(records,indent=2)+'\\n')
 print(json.dumps({'status':'PASS','actual_MCP_tools':[24,27],'no_active_grants':True,'projects_checked':len(projects)}))
asyncio.run(main())
'''
    root = work / 'install'
    command(work, 'actual-MCP-after-reboot', [str(root / 'venv/bin/python'), '-c', script],
        extra={'PYTHONPATH': str(root / 'code'), 'LM020_WORK': str(work)})


def finish(package: Path, work: Path, require_reboot: bool = True) -> dict:
    before = json.loads((work / 'rc020-before-reboot.json').read_text())
    now = machine()
    if before['machine']['machine_id_sha256'] != now['machine_id_sha256']:
        raise ValueError('020_DIFFERENT_QA_MACHINE_AFTER_REBOOT')
    changed_boot = before['machine']['boot_id_sha256'] != now['boot_id_sha256']
    if require_reboot and not changed_boot:
        raise ValueError('020_ACTUAL_GUEST_REBOOT_REQUIRED')
    current = inspect(work, 'after-reboot-inspection')
    unchanged(before['state'], current)
    readonly_mcp(package, work)
    unchanged(current, inspect(work, 'after-MCP-inspection'))
    root = work / 'install'
    command(work, 'uninstall', [sys.executable, str(package / 'release020.py'), '--package', str(package), 'uninstall', '--root', str(root)])
    if (root / 'code').exists() or (root / 'venv').exists() or not (root / 'state/beta.sqlite3').exists() or not (root / 'seals').exists():
        raise ValueError('020_UNINSTALL_DATA_RETENTION_FAILED')
    command(work, 'reinstall', [sys.executable, str(package / 'release020.py'), '--package', str(package), 'install', '--root', str(root)], timeout=600)
    second = json.loads(command(work, 'repeat-install', [sys.executable, str(package / 'release020.py'), '--package', str(package), 'install', '--root', str(root)]))
    if not second['result']['idempotent']:
        raise ValueError('020_REINSTALL_NOT_IDEMPOTENT')
    unchanged(current, inspect(work, 'after-reinstall-inspection'))
    command(work, 'bootstrap-tests', [str(root / 'venv/bin/python'), '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
        str(package / 'qa020/test_release020.py')], extra={'PYTHONPATH': str(package),
        'LM020_ORIGINAL_ZIP': str(package / 'provenance/capsule-019.zip')})
    result = {'status': 'PASS', 'scope': '020 release-only fresh cohort; original019 tests unchanged',
        'release': verify(package), 'machine_before': before['machine'], 'machine_after': now,
        'actual_guest_reboot': changed_boot, 'require_reboot': require_reboot,
        'receipt_ids_hash_chain_state_preserved': True, 'signed_committed_artifacts': len(current['committed_artifacts']),
        'no_active_grants_after_reboot': True, 'uninstall_reinstall': 'PASS',
        'legacy_private_tools': [24, 27], 'owner_approval': 'AWAITING_OWNER_SIGNOFF',
        'historical86': 'SKIP_NO_PRIVATE_SNAPSHOT', 'proof_status': 'unverified'}
    write(work / 'rc020-acceptance.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--same-host-no-reboot', action='store_true', help='Local supplementary rehearsal only; never independent reboot proof')
    parser.add_argument('action', choices=['replay', 'finish'])
    args = parser.parse_args()
    try:
        verify(args.package)
        result = replay(args.package, args.work) if args.action == 'replay' else finish(args.package, args.work, not args.same_host_no_reboot)
        print(json.dumps(result))
    except Exception as error:
        if args.work.exists():
            write(args.work / 'rc020-first-failure.json', {'status': 'STOP_WITH_RCA', 'error': str(error),
                'traceback': __import__('traceback').format_exc()})
        raise
