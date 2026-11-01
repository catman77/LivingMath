"""Deterministic009 acceptance. Production read-only; lifecycle only on private BackupAPI copies."""
import argparse
import asyncio
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import subprocess
import sys
import traceback

from normalizer import digest
from normalization_regression import run_regression
from qa_positive_acceptance import write_json, snapshot
from research_cycle009_worlds import declarations, environments
from research_cycle009_oracle import sequence
from research_cycle009_runtime import Cycle

SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def initialize():
    from attention_qa import configure
    from qa_positive_acceptance import oauth
    from transfer_qa import Session
    from native_preview008_qa import readonly_state
    cfg = configure(); stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    b = Path.home() / '.local/state/livingmath/cycle009' / stamp
    b.mkdir(parents=True, mode=0o700)
    db = (Path(cfg['LIVE_MATH_DATA_DIR']) / 'research.sqlite3').resolve(strict=True)
    with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)) as src, closing(sqlite3.connect(b / 'research-before.sqlite3')) as dest:
        src.backup(dest)
    (b / 'research-before.sqlite3').chmod(0o600)
    write_json(b / 'before.json', snapshot(db)); write_json(b / 'readonly-before.json', readonly_state(db))
    paths = [ROOT / 'AGENTS.md', *SOURCE.glob('*.py'), *SOURCE.glob('*.json'), *[p for p in (ROOT / 'docs/qa').rglob('*') if p.is_file()]]
    write_json(b / 'protected-files.json', {str(p.resolve()): sha(p) for p in paths})
    write_json(b / 'metadata.json', {'db': str(db), 'private': str(b), 'backup_sha256': sha(b / 'research-before.sqlite3')})
    folder = b / 'live-readonly'; folder.mkdir(); client = Session(folder, db, cfg['LIVE_MATH_PUBLIC_URL'])
    async def read(c):
        before = readonly_state(db)
        tools = (await c.session.list_tools()).model_dump(mode='json')
        health = await c.call('service_health', {})
        expected = json.loads((ROOT / 'docs/qa/LM-NATIVE-PREVIEW-008-DEPLOY/20261027T051454059241Z/tools-list-after.json').read_text())
        names = ('research_native_preview', 'research_normalize_preview')
        current = {t['name']: t for t in tools['tools']}; known = {t['name']: t for t in expected['tools']}
        installed = len(current) == 20 and all(current.get(n) == known[n] for n in names)
        write_json(b / 'public-preflight.json', {'initialize': c.initialized, 'tools': tools, 'health': health,
            'expected_preview_schemas_match': installed, 'public_installation': 'PASS' if installed else 'DEPLOYMENT_PENDING',
            'public_preview_smoke': 'SKIP_NO_REGISTERED_COMPATIBLE_QA_SOURCE', 'readonly_before': before, 'readonly_after': readonly_state(db)})
        assert before == readonly_state(db)
    client.work = read
    try:
        oauth(cfg, client)
    except BaseException:
        (b / 'public-transport-failure.txt').write_text(traceback.format_exc())
        write_json(b / 'public-preflight.json', {'public_installation': 'DEPLOYMENT_PENDING', 'reason': 'TRANSPORT_FAILURE',
                                               'public_preview_smoke': 'SKIP', 'no_deployment_attempted': True})
    return b


def freeze(baseline, base):
    registered = baseline / 'frozen-scenarios'
    if not registered.exists():
        registered.mkdir()
        worlds = declarations(baseline.name)
        envs = environments(worlds, [secrets.token_hex(32) for _ in worlds])
        (registered / 'world-inputs').mkdir(); (registered / 'sealed-environments').mkdir()
        for world, env in zip(worlds, envs):
            write_json(registered / 'world-inputs' / (world['id'] + '.json'), world)
            write_json(registered / 'sealed-environments' / (world['id'] + '.json'), env)
        write_json(registered / 'worlds.json', worlds)
        write_json(registered / 'oracle.json', [sequence(w, e) for w, e in zip(worlds, envs)])
        write_json(registered / 'preregistration.json', {'protocol': '009.P0.1', 'worlds': 3, 'cycles_per_world': 2,
            'hypotheses': 3, 'independent_branch': True, 'loss': 'test_cost + (7/3)*expected surviving hypothesis count',
            'outcomes': ['first FAILURE', 'second bounded candidate consistency', 'separate operator INCONCLUSIVE control'],
            'gate': '3/3 worlds complete two linked scoped steps, genuine T change, independent rational agreement, no false witness/grant/verified, append-only preservation',
            'stale_grant': 'Unexecuted permission canary must be invalidated by v1->v2 evidence-bearing update',
            'version_projection': 'Append linked histories/root/law/old-negative receipt; remove only measured-excluded current hypotheses, preserve original rows and independent source',
            'operator_inputs': ['source laws and finite declarations', 'salted sealed environment', 'narrow QA allowance', 'scoped diagnostic dispositions'],
            'negative_controls': ['adverse diagnostic label without disposition', 'wrong scope/project/source/hash/observer/version',
                'C4', 'quota', 'point/germ/lexical alias', 'primitive rename', 'mutated returned witness',
                'premise-only completion evidence', 'permission-only witness', 'terminal reactivation', 'result-key tamper'],
            'costs': 'Cold per-preview wait4 worker CPU/RSS through exit, wall/source decode/normalizer/I/T/serialization and MCP roundtrip/client CPU; whole MCP server wait4 includes descendant subset and is not added twice',
            'baseline': 'Unchanged006.2 paired on the identical evolving snapshots, with independent T; lifecycle is shared orchestration, no full-cycle speedup inference',
            'warm': 'No public cross-request cache; cache reuse is not a claimed benefit', 'P1': 'SKIP0; no post-P0 scientific proposer decision requested',
            'production': 'Read-only initialize/tools/list/health. No QA-native production sources => preview smoke SKIP, use staging; never deploy or create live QA sources.'})
        paths = [p for p in registered.rglob('*') if p.is_file()]
        write_json(registered / 'manifest.json', {str(p.relative_to(registered)): sha(p) for p in paths})
        for p in paths: p.chmod(0o444)
    hashes = json.loads((registered / 'manifest.json').read_text())
    assert all(sha(registered / p) == h for p, h in hashes.items())
    for path in ('world-inputs', 'sealed-environments'):
        shutil.copytree(registered / path, base / path)
    for name in ('worlds.json', 'oracle.json', 'preregistration.json', 'manifest.json'):
        shutil.copyfile(registered / name, base / name)
    (base / 'frozen-sources').mkdir()
    files = [*SOURCE.glob('research_cycle009*.py'), SOURCE / 'test_research_cycle009.py',
             *SOURCE.glob('live_constructive007*.py'), *SOURCE.glob('live_transfer006*.py'),
             *SOURCE.glob('native_preview008*.py'), SOURCE / 'native_preview008-adapters.json', SOURCE / 'normalizer.py',
             SOURCE / 'mcp_server.py', SOURCE / 'move_lifecycle.py', SOURCE / 'frontier.py', SOURCE / 'evidence_review.py']
    files = [p for p in files if p.is_file()]
    for p in files: shutil.copyfile(p, base / 'frozen-sources' / p.name)
    write_json(base / 'source-hashes.json', {str(p.resolve()): sha(p) for p in files})
    return json.loads((base / 'worlds.json').read_text()), json.loads((base / 'oracle.json').read_text())


async def permission_control(cycle):
    """Genuine source admissibility divergence; no activation/external execution."""
    from mcp import ClientSession
    from research_cycle009_transport import measured_stdio
    from research_cycle009_worlds import checksum
    from research_cycle009 import requests, validate_executable_readout
    w = {'id': 'boundary', 'project': 'LM_QA_CYCLE009_' + cycle.base.name + '_boundary',
        'parameters': {'family': 'boundary', 'initial': [0], 'actions': ['a0', 'a1', 'a2']},
        'histories': {'H0': ['a0'], 'H1': ['a1'], 'H2': ['a0', 'a0']},
        'tests': [{'id': 't' + str(i), 'ordinal': i, 'suffix': ['a' + str(i)], 'cost': 0} for i in range(3)],
        'observer': {'projection': 'primary', 'mod': None}, 'law_kind': 'unsupported', 'width': 1,
        'current_observation': 0, 'unknowns': ['No equivalence beyond D'], 'independent_branch': {'id': 'IND', 'word': []}}
    w['fixture_sha256'] = checksum(w); w['scope'] = 'QA009/boundary/' + w['fixture_sha256']
    async with measured_stdio(cycle.db, cycle.base / 'sessions/permission-only') as (read, write):
        async with ClientSession(read, write) as client:
            cycle.client = client; await client.initialize()
            binding = await cycle.seed(w, '0' * 64)
            _, req = requests(cycle.db, w, binding)
            out = await cycle.call('research_native_preview', req)
            cycle.check('permission_only:real_native_witness', out['status'] == 'NEW_DISTINCTION' and
                        out['witness']['readouts'][0]['defined'] != out['witness']['readouts'][1]['defined'])
            test = next(t for t in w['tests'] if t['id'] == out['witness']['test_id'])
            candidate = {'test_id': test['id'], **{k: test[k] for k in ('suffix', 'cost', 'ordinal')},
                         'counterfactuals': [{'readout': r} for r in out['witness']['readouts']]}
            try:
                validate_executable_readout(w, candidate, {'test_id': test['id']})
            except ValueError as error:
                refused = str(error) == 'PERMISSION_ONLY_WITNESS_IS_NOT_EXECUTABLE'
            else:
                refused = False
            cycle.check('permission_only:no_execution', refused and not out['execution_permission']['allowed'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-dir', type=Path, help='Existing private baseline; every attempt still creates a fresh cohort')
    args = parser.parse_args()
    baseline = args.baseline_dir.resolve(strict=True) if args.baseline_dir else initialize()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    base = baseline / 'cohorts' / stamp; base.mkdir(parents=True, mode=0o700, exist_ok=False)
    Path('/tmp/lm009_cohort').write_text(str(base))
    write_json(base / 'metadata.json', {'baseline': str(baseline), 'report': str(ROOT / 'docs/qa/LM-RESEARCH-CYCLE-009' / stamp)})
    failure = None
    try:
        worlds, oracle = freeze(baseline, base)
        with (base / 'pytest.txt').open('w') as out:
            subprocess.run([sys.executable, '-m', 'pytest', '-q', str(SOURCE)], stdout=out, stderr=subprocess.STDOUT,
                           env={k: v for k, v in os.environ.items() if k != 'LIVE_MATH_NATIVE_PREVIEW'}, check=True)
        print('Full pytest PASS', flush=True)
        prior = os.environ.pop('LIVE_MATH_NATIVE_PREVIEW', None)
        try: legacy = run_regression(base / 'historical86', baseline / 'research-before.sqlite3')
        finally:
            if prior is not None: os.environ['LIVE_MATH_NATIVE_PREVIEW'] = prior
        if legacy['result'] != 'PASS': raise RuntimeError('Historical86 did not pass')
        db = base / 'isolated.sqlite3'
        with closing(sqlite3.connect((baseline / 'research-before.sqlite3').as_uri() + '?mode=ro', uri=True)) as src, closing(sqlite3.connect(db)) as dest:
            src.backup(dest)
        cycle = Cycle(base, db, Path(json.loads((baseline / 'metadata.json').read_text())['db']))
        async def run():
            for w, expected in zip(worlds, oracle): await cycle.run_world(w, expected)
            await permission_control(cycle)
        asyncio.run(run())
        # Sealed values, raw truth tables and environment traces must never enter MCP arguments.
        arguments = json.dumps([c['arguments'] for c in cycle.calls])
        cycle.check('no_hidden_fixture_or_oracle_in_MCP_arguments', all(key not in arguments for key in
            ('target_word', 'raw_signatures', 'sealed-environments', 'private_native_trace', '"salt"')))
        write_json(base / 'run-state.json', {'result': 'PASS', 'linked_completed_steps': len(cycle.ledger)})
    except BaseException as error:
        failure = {'classification': 'SOFTWARE_OR_SOURCE_OR_ORACLE_MISMATCH', 'error': str(error), 'traceback': traceback.format_exc()}
        write_json(base / 'run-failure.json', failure)
        if not (base / 'first-failure.json').exists(): write_json(base / 'first-failure.json', failure)
        print(json.dumps({'result': 'STOP_WITH_RCA', 'error': str(error), 'cohort': str(base)}), flush=True)
    finally:
        from research_cycle009_report import export
        print(json.dumps(export(base, failure)), flush=True)


if __name__ == '__main__':
    main()
