"""Replay015 against the bundled original Xi export, in disposable private storage.

This repeats the registered experiment; it is not independent new scientific
evidence. Production credentials, production SQLite files and LLMs are unused.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import shutil
import sqlite3
import subprocess
import sys
import time
import zipfile

from normalizer import canonical
from qa_positive_acceptance import snapshot, write_json
from research_store import ResearchStore
from real_xi015_run import measured, SOURCE
from real_xi015_source import audit_export


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finish_private(database):
    """Close only this experiment's QA branches, preserving append-only history."""
    from operational013_report import chain, append_only
    store = ResearchStore(database)
    before = snapshot(database)
    with store._connect() as c:
        moves = [dict(r) for r in c.execute(
            "SELECT * FROM research_moves WHERE project LIKE 'LM_QA_TYPED011_XI015_%'")]
        obligations = [dict(r) for r in c.execute(
            "SELECT * FROM research_obligations WHERE project LIKE 'LM_QA_TYPED011_XI015_%' OR project='LM_QA_XI015_TRAIN'")]
    for move in moves:
        view = store.moves.inspect(move['project'], move['id'])
        if view['status'] not in {'COMPLETED', 'ABANDONED', 'REJECTED'}:
            store.moves.transition(move['project'], move['id'], 'abandon',
                'xi015:close:' + str(move['id']), reason='QA attempt ended; retain its original observations and failures.')
    for obligation in obligations:
        current = store.frontier.history(obligation['id'])[-1]
        if current['status'] in {'OPEN', 'TESTING', 'BLOCKED'}:
            store.frontier.update(obligation['id'], current['version'], {
                'status': 'RESOLVED', 'closure_reason': 'Bounded015 run ended; no structural advantage established.',
                'evidence_refs': current['evidence_refs'] or ['event:' + str(i) for i in current['source_event_ids']],
                'reopen_conditions': ['New frozen source question and explicit operator review.']})
    after = snapshot(database)
    views = [store.moves.inspect(m['project'], m['id']) for m in moves]
    return {'active_QA_grants': [v['id'] for v in views if v['execution_permission']['allowed']],
        'moves': views, 'obligations': [store.frontier.history(o['id']) for o in obligations],
        'immutable_prefixes': {t: after['tables'][t][:len(rows)] == rows for t, rows in before['tables'].items()
                               if t != 'research_obligations'},
        'append_only': append_only(database), 'chain': chain(database)}


def typed_replay(base):
    from real_xi015_typed import prepare, activate, XiValidator
    from real_xi015_operator import commit
    from law_validation014_contract import ReceiptRequest014
    prepared = prepare(base)
    db = Path(prepared['database'])
    out = Path(prepared['out'])
    activation = activate(db, prepared['project'], prepared['move_id'], 'xi015-replay')
    command = [sys.executable, str(SOURCE / 'real_xi015_typed.py'), '--execute', '--db', str(db)]
    from native_preview008_server import MeasuredProcess
    start = time.perf_counter_ns()
    with (out / 'typed-executor.log').open('w') as log:
        process = MeasuredProcess(command, stdin=subprocess.PIPE, stdout=log, stderr=log, text=True)
        try:
            process.communicate(canonical({'project': prepared['project'], 'move_id': prepared['move_id'],
                'native_directory': prepared['native_directory']}), timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise ValueError('TYPED_EXECUTION_WALL_BUDGET')
    executor_wall = time.perf_counter_ns() - start
    usage = process.child_usage
    if process.returncode:
        raise ValueError('TYPED_EXECUTION_FAILED:' + (out / 'typed-executor.log').read_text())
    execution = json.loads((out / 'typed-executor.log').read_text())['result']
    validation = XiValidator(db).validate(prepared['project'], prepared['move_id'], execution['event_id'])
    env = execution['envelope']
    request = ReceiptRequest014(project=prepared['project'], move_id=prepared['move_id'],
        event_id=execution['event_id'], request_key='xi015-atomic-receipt',
        **{k: env[k] for k in ('outcome', 'observed', 'summary', 'reason', 'proof_status')}).model_dump()
    receipt = commit(db, request)
    stable = snapshot(db)
    repeated = commit(db, request)
    duplicate_unchanged = stable == snapshot(db)
    try:
        commit(db, {**request, 'reason': 'Attempt to substitute a different result reason.'})
        substitution_blocked = False
    except ValueError as error:
        substitution_blocked = str(error) == 'RECEIPT_REQUEST_KEY_CONFLICT'
    checks = {'idempotent': repeated['idempotent'], 'duplicate_unchanged': duplicate_unchanged,
              'substitution_blocked': substitution_blocked, 'substitution_unchanged': stable == snapshot(db)}
    write_json(out / 'typed-cycle.json', {'precommit': prepared, 'activation': activation,
        'native_executor': execution, 'validation': validation, 'receipt': receipt, 'idempotency': checks,
        'costs': {'wall_ns': executor_wall,
                  'CPU_ns': round((usage.ru_utime + usage.ru_stime) * 1e9), 'peak_RSS_KiB': usage.ru_maxrss},
        'new_native_theta_calls': 1, 'independent_new_blind_prediction': False})
    shutil.copy2(execution['artifact_path'], out / 'typed-native-artifact.json')
    if validation['status'] != 'VALID_BOUND_MEASUREMENT' or not all(checks.values()):
        raise ValueError('TYPED_GATE_FAILED')


def main():
    total_start = time.perf_counter_ns()
    total_cpu_start = resource.getrusage(resource.RUSAGE_SELF)
    children_start = resource.getrusage(resource.RUSAGE_CHILDREN)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True, help='New private directory, must not already exist')
    args = parser.parse_args()
    package = args.package.resolve()
    base = args.work.resolve()
    base.mkdir(parents=True, mode=0o700, exist_ok=False)
    policy = json.loads((package / 'frozen-split.json').read_text())
    archive = package / 'input/RH_XI_ROUTES_EXPORT_001.zip'
    if sha(archive) != policy['archive_sha256']:
        raise ValueError('SOURCE_ARCHIVE_MISMATCH')
    raw = base / 'raw/RH_XI_ROUTES_EXPORT_001'
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            target = (base / 'raw' / item.filename).resolve()
            if not target.is_relative_to(base / 'raw'):
                raise ValueError('UNSAFE_ARCHIVE_PATH')
        z.extractall(base / 'raw')
    manifest = json.loads((raw / 'MANIFEST_SHA256.json').read_text())
    if not all(sha(raw / name) == digest for name, digest in manifest.items()):
        raise ValueError('SOURCE_MEMBER_MISMATCH')
    source_manifest = json.loads((package / 'source-manifest.json').read_text())
    source_manifest.update(archive=str(archive), raw_source=str(raw))
    write_json(base / 'source-manifest.json', source_manifest)
    shutil.copy2(package / 'frozen-split.json', base / 'frozen-split.json')
    # A disposable empty QA ledger, never a replacement for an existing database.
    canonical_db = base / 'disposable-QA-origin.sqlite3'
    ResearchStore(canonical_db)
    with sqlite3.connect(canonical_db) as src, sqlite3.connect(base / 'canonical.sqlite3') as dst:
        src.backup(dst)
    write_json(base / 'metadata.json', {'base': str(base), 'canonical': str(canonical_db), 'raw': str(raw)})
    limits = policy['budget']
    launcher = ('import resource,runpy,sys;'
        f'resource.setrlimit(resource.RLIMIT_CPU,({limits["source_CPU_s"]},{limits["source_CPU_s"]}));'
        f'resource.setrlimit(resource.RLIMIT_AS,({limits["source_AS_bytes"]},{limits["source_AS_bytes"]}));'
        'p=sys.argv.pop(1);sys.path.insert(0,str(__import__("pathlib").Path(p).parent));runpy.run_path(p,run_name="__main__")')
    cost = measured([sys.executable, '-c', launcher, str(raw / 'reproduce.py'), '--out', str(base / 'reproduced')],
        base / 'native-reproduction.log', timeout=limits['source_wall_s'])
    cost['limits_declared_before_start'] = limits
    write_json(base / 'native-reproduction-costs.json', cost)
    started, cpu = time.perf_counter_ns(), time.process_time_ns()
    original, regenerated = audit_export(raw / 'cases.json'), audit_export(base / 'reproduced/cases.json')
    exact = {n: sha(raw / n) == sha(base / 'reproduced' / n) for n in ('cases.json', 'routes.json', 'loops.json')}
    if not all(exact.values()) or original != regenerated:
        raise ValueError('SOURCE_REPRODUCTION_MISMATCH')
    write_json(base / 'audited-input.json', original)
    write_json(base / 'source-validation.json', {'exact_bytes': exact, 'address_join': original['join'],
        'CPU_ns': time.process_time_ns() - cpu, 'wall_ns': time.perf_counter_ns() - started})
    p0 = measured([sys.executable, str(SOURCE / 'real_xi015_run.py'), '--baseline', str(base), '--output', str(base / 'P0')],
        base / 'P0.log')
    typed_replay(base)
    cleanup = finish_private(Path(json.loads((base / 'current.json').read_text())['database']))
    write_json(base / 'integrity.json', cleanup)
    checks = {'source_exact': all(exact.values()), 'no_active_grants': not cleanup['active_QA_grants'],
        'immutable_prefixes': all(cleanup['immutable_prefixes'].values()),
        'append_only': all(cleanup['append_only'].values()),
        'chain': cleanup['chain']['hash_chain_ok'] and cleanup['chain']['sqlite_integrity'] == 'ok'
                 and not cleanup['chain']['foreign_key_errors']}
    result = {'checks': checks, 'result': 'PASS_REPLAY' if all(checks.values()) else 'FAIL',
        'scientific_status': 'NO_DEMONSTRATED_STRUCTURAL_ADVANTAGE', 'proof_status': 'unverified',
        'production_used': False, 'P0_cost_including_subprocesses': p0}
    own, children = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    result['end_to_end_replay_costs'] = {
        'wall_ns': time.perf_counter_ns() - total_start,
        'CPU_ns': round((own.ru_utime + own.ru_stime + children.ru_utime + children.ru_stime
            - total_cpu_start.ru_utime - total_cpu_start.ru_stime
            - children_start.ru_utime - children_start.ru_stime) * 1e9),
        'largest_process_peak_RSS_KiB': max(own.ru_maxrss, children.ru_maxrss),
        'scope': 'Archive unpack, source regeneration/audit, disposable QA setup, all P0 baselines/predictions/native calls, typed replay/receipt, cleanup and integrity; excludes dependency installation and historical regression.'}
    write_json(base / 'replay-result.json', result)
    print(canonical(result))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
