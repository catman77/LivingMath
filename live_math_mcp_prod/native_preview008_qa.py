"""Fresh, retained MCP preview acceptance; no production writes, LLM or automatic deployment."""
import argparse
import asyncio
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import traceback

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from normalizer import canonical, digest, ContextNormalizer
from normalization_regression import Tap, run_regression
from normalization_oracle import materialize, run_audit, audit_projection
from live_constructive007_oracle import pairs, attention
from native_preview008_fixtures import ORIGINAL007, changed, materialize_copy, native_request, normalize_request
from qa_positive_acceptance import snapshot, write_json

SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def append(path, value):
    with path.open('a') as out:
        out.write(json.dumps(value, ensure_ascii=False) + '\n')


def readonly_state(db: Path) -> dict:
    state = snapshot(db)
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as c:
        schema = c.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY name').fetchall()
        sequence = c.execute('SELECT * FROM sqlite_sequence ORDER BY name').fetchall()
        version = c.execute('PRAGMA user_version').fetchone()[0]
    return {'all_tables_sha256': digest(state['tables']), 'schema_sha256': digest(schema),
            'sequence_sha256': digest(sequence), 'schema_version': version,
            'inode': state['inode'], 'database_sha256': sha(db),
            'operations': len(state['tables']['operations']),
            'chain_head': state['tables']['operations'][-1]['entry_hash'] if state['tables']['operations'] else 'GENESIS'}


class Acceptance:
    def __init__(self, base):
        self.base = base
        self.calls, self.checks, self.readonly, self.costs = [], [], [], []

    def check(self, name, ok, evidence=None):
        row = {'invariant': name, 'result': 'PASS' if ok else 'FAIL', 'evidence': evidence}
        self.checks.append(row)
        write_json(self.base / 'checks.json', self.checks)
        if not ok:
            write_json(self.base / 'first-failure.json', {'classification': 'ENGINEERING_OR_ORACLE_MISMATCH', **row})
            raise AssertionError(name)

    async def session(self, db, work, label, script=None, env=None):
        params = StdioServerParameters(command=sys.executable,
            args=[str(script or SOURCE / 'native_preview008_server.py'), *([] if script else ['--db', str(db)])],
            env={**os.environ, **(env or {})})
        with (self.base / (label + '-stderr.txt')).open('w') as error:
            async with stdio_client(params, errlog=error) as (read, write):
                async with ClientSession(Tap(read, self.base / 'mcp-wire.jsonl', 'response'),
                                         Tap(write, self.base / 'mcp-wire.jsonl', 'request')) as client:
                    initialized = (await client.initialize()).model_dump(mode='json')
                    tools = (await client.list_tools()).model_dump(mode='json')
                    append(self.base / 'tools-list.jsonl', {'label': label, 'initialize': initialized, 'tools': tools})
                    await work(client, tools)

    async def call(self, client, db, name, arguments, label):
        before = readonly_state(db)
        started = time.perf_counter_ns()
        response = await client.call_tool(name, arguments)
        elapsed = time.perf_counter_ns() - started
        raw = response.model_dump(mode='json')
        row = {'index': len(self.calls) + 1, 'label': label, 'tool': name, 'arguments': arguments,
               'response': raw, 'client_roundtrip_wall_ns': elapsed}
        self.calls.append(row)
        append(self.base / 'calls.jsonl', row)
        after = readonly_state(db)
        equal = before == after
        delta = {'call': row['index'], 'label': label, 'before': before, 'after': after,
                 'all_tables_schema_sequence_chain_and_bytes_unchanged': equal}
        self.readonly.append(delta)
        append(self.base / 'read-only-before-after.jsonl', delta)
        self.check(label + ':readonly', equal, delta)
        if response.isError:
            return None, row
        out = response.structuredContent or json.loads(response.content[0].text)
        if name in {'research_normalize_preview', 'research_native_preview'}:
            self.check(label + ':no_grant', out.get('execution_permission') == {'allowed': False}
                       and out.get('proof_status') == 'unverified', out.get('status'))
        return out, row

    async def world(self, world, oracle):
        db = Path(world['database'])
        async def exercise(client, tools):
            self.check(world['id'] + ':two_tools', {t['name'] for t in tools['tools']} ==
                       {'research_normalize_preview', 'research_native_preview'})
            self.check(world['id'] + ':readonly_schema', all(t['annotations']['readOnlyHint'] and
                       t['inputSchema'].get('additionalProperties') is False for t in tools['tools']))
            for n, pair in enumerate(oracle['pairs']):
                results = {}
                for mode in ('bounded', 'constructive'):
                    req = native_request(world, pair['left'], pair['right'], mode)
                    out, call = await self.call(client, db, 'research_native_preview', req,
                                                f'{world["id"]}:{n}:{mode}')
                    self.check(f'{world["id"]}:{n}:{mode}:response', out is not None, call)
                    found = out['status'] == 'NEW_DISTINCTION'
                    self.check(f'{world["id"]}:{n}:{mode}:distinction', found == pair['hidden'], out['status'])
                    if found:
                        test = out['witness']['test_id']
                        self.check(f'{world["id"]}:{n}:{mode}:native_witness',
                                   out['witness']['readouts'] == [pair['Sig_left'][test], pair['Sig_right'][test]], out['witness'])
                    else:
                        self.check(f'{world["id"]}:{n}:{mode}:not_equivalence',
                                   out['asserts_equivalence'] is False and out['witness'] is None)
                    self.check(f'{world["id"]}:{n}:{mode}:independent_T',
                               out['attention']['status'] == oracle['attention']['status'] and
                               out['attention'].get('test_id') == oracle['attention']['selected_test_id'])
                    if oracle['attention']['ranking']:
                        keys = list(oracle['attention']['ranking'][0])
                        self.check(f'{world["id"]}:{n}:{mode}:exact_T_rationals',
                                   [{k: v[k] for k in keys} for v in out['attention']['ranking']] == oracle['attention']['ranking'])
                    self.check(f'{world["id"]}:{n}:{mode}:metered',
                               out['cost_ledger']['total']['total_native_calls'] == sum(out['primitive_calls'].values()) <= 2048)
                    self.check(f'{world["id"]}:{n}:{mode}:OS_child_cost_through_exit',
                               out['child_usage_status'] == 'OS_WAIT4_THROUGH_EXIT' and
                               out['child_cpu_ns'] >= out['worker_total_cpu_ns'] > 0 and
                               out['child_peak_rss_KiB'] >= out['worker_max_rss_KiB'] > 0)
                    results[mode] = out
                    self.costs.append({'world': world['id'], 'family': world['family'], 'fresh_heldout': world.get('fresh_heldout', False),
                                       'pair': [pair['left'], pair['right']], 'hidden': pair['hidden'], 'mode': mode,
                                       'client_roundtrip_wall_ns': call['client_roundtrip_wall_ns'],
                                       **{k: out[k] for k in ('cold_wall_ns', 'cold_cpu_ns', 'parent_cpu_ns', 'worker_total_wall_ns',
                                                             'worker_total_cpu_ns', 'worker_max_rss_KiB', 'child_cpu_ns', 'child_peak_rss_KiB', 'source_serialization',
                                                             'source_snapshot_wall_ns', 'primitive_calls', 'cost_ledger')},
                                       'status': out['status'], 'strategy': out['interpretation'].get('strategy', 'B1'),
                                       'witness': out.get('witness'), 'T_test_id': out['attention'].get('test_id')})
                    append(self.base / 'cost-ledger.jsonl', self.costs[-1])
                self.check(f'{world["id"]}:{n}:T_not_I_witness',
                           results['bounded']['attention'].get('ranking') == results['constructive']['attention'].get('ranking'))
                if n == 0:
                    req = native_request(world)
                    again, _ = await self.call(client, db, 'research_native_preview', req, world['id'] + ':ID_replay')
                    self.check(world['id'] + ':ID_replay_exact', again['witness'] == results['constructive']['witness'])
            for level in ('C0', 'C1', 'C2', 'C3', 'C4'):
                out, _ = await self.call(client, db, 'research_normalize_preview', normalize_request(world, level), world['id'] + ':normalize:' + level)
                self.check(world['id'] + ':normalize_status:' + level,
                           out is not None and out['status'] == ('EXPLANATION_ONLY' if level == 'C4' else 'COMPLETE') and
                           out['audit_sufficient'] == (level != 'C4'))
            print(json.dumps({'phase': 'MCP_cold_pairs', 'world': world['id'], 'pairs': len(oracle['pairs']), 'status': 'PASS'}), flush=True)
        await self.session(db, exercise, world['id'])

    async def controls(self, worlds):
        world = worlds[0]
        db = Path(world['database'])
        request_cases = {}
        for fault in ('foreign', 'missing', 'hash', 'stale', 'adapter', 'observer', 'C4', 'budget',
                      'malicious', 'authority', 'long_request_suffix', 'timeout', 'missing_binding', 'duplicate_id', 'missing_law'):
            req = native_request(world)
            if fault == 'foreign': req['project'] = 'FOREIGN'
            if fault == 'missing': req['source_event_ids'][0] = 999999
            if fault == 'hash': req['source_bindings'][0]['sha256'] = '0' * 64
            if fault == 'stale': req['active_frontier_version'] += 1
            if fault == 'adapter': req['source_adapter_id'] = 'not_installed'
            if fault == 'observer': req['observer']['mod'] = 2
            if fault == 'C4': req['question']['context_level'] = 'C4'
            if fault == 'budget': req['budget'] = {'source_bytes': 4096}
            if fault == 'malicious': req['code'] = 'raise SystemExit("never execute")'
            if fault == 'authority': req['question']['verified'] = True
            if fault == 'long_request_suffix': req['question']['max_suffix_length'] = 3
            if fault == 'timeout': req['budget'] = {'deadline_ms': 50}
            if fault == 'missing_binding': req['source_bindings'].pop()
            if fault == 'duplicate_id': req['source_event_ids'].append(req['source_event_ids'][0])
            if fault == 'missing_law': req['question'].pop('certificate_event_id')
            request_cases[fault] = req
        async def exercise(client, tools):
            for fault, req in request_cases.items():
                out, _ = await self.call(client, db, 'research_native_preview', req, 'negative:' + fault)
                if fault in {'malicious', 'authority', 'long_request_suffix'}:
                    self.check('negative:' + fault, out is None)
                elif fault == 'timeout':
                    self.check('negative:hard_timeout', out is not None and out['status'] == 'RESOURCE_LIMIT' and out['reason'] == 'HARD_WORKER_TIMEOUT')
                elif fault == 'missing_law':
                    self.check('negative:missing_law_fallback', out is not None and out['status'] == 'NEW_DISTINCTION' and out['interpretation']['strategy'] == 'FALLBACK_BOUNDED')
                else:
                    self.check('negative:' + fault, out is not None and out['status'] == 'INSUFFICIENT_CONTEXT')
            req = normalize_request(world); req['query_scope']['expected_hashes'] = [{'event_id': 1, 'sha256': '0' * 64}]
            out, _ = await self.call(client, db, 'research_normalize_preview', req, 'negative:normalize_hash')
            self.check('negative:normalize_hash', out['status'] == 'INSUFFICIENT_CONTEXT')
            req = normalize_request(world); req['budget'] = {'source_bytes': 4096}
            out, _ = await self.call(client, db, 'research_normalize_preview', req, 'negative:normalize_budget')
            self.check('negative:normalize_budget', out['status'] == 'INSUFFICIENT_CONTEXT')
        await self.session(db, exercise, 'request-controls')
        for fault in ('wrong_law', 'guard_false', 'partial_law', 'stale_law', 'closed', 'long_suffix', 'invalid_suffix', 'source_code', 'point_germ', 'labels'):
            w = changed(world, fault)
            copy_db = materialize_copy(w, self.base / 'controls' / fault)
            async def exercise(client, tools):
                req = native_request(w)
                if fault == 'labels':
                    from live_constructive007_worlds import frame
                    from live_constructive007 import interpret_constructive
                    old = interpret_constructive(frame(world), world['refs']['h0'], world['refs']['h1'], world['certificate_ref'])
                    req['question']['known_fingerprints'] = [old['fingerprint']]
                out, _ = await self.call(client, copy_db, 'research_native_preview', req, 'source-control:' + fault)
                if fault in {'wrong_law', 'guard_false', 'partial_law', 'stale_law'}:
                    self.check('source-control:' + fault, out['status'] == 'NEW_DISTINCTION' and out['interpretation']['strategy'] == 'FALLBACK_BOUNDED')
                elif fault == 'labels':
                    self.check('source-control:labels_no_novelty', out['status'] == 'NO_NEW_DISTINCTION_BOUNDED')
                else:
                    self.check('source-control:' + fault, out['status'] == 'INSUFFICIENT_CONTEXT')
            await self.session(copy_db, exercise, 'source-' + fault)
        # An existing event in another project is not merely a missing-ID control.
        foreign_db = materialize_copy(world, self.base / 'controls' / 'existing-foreign')
        from research_store import ResearchStore
        store = ResearchStore(foreign_db)
        row = store.record('FOREIGN008', 'hypothesis', 'foreign', 'Foreign private source', 'hypothesis')
        with sqlite3.connect(foreign_db) as conn:
            conn.row_factory = sqlite3.Row
            foreign_row = dict(conn.execute('SELECT * FROM events WHERE id=?', (row['id'],)).fetchone())
        async def foreign(client, tools):
            req = native_request(world); req['source_event_ids'].append(row['id'])
            req['source_bindings'].append({'event_id': row['id'], 'sha256': digest(foreign_row)})
            out, _ = await self.call(client, foreign_db, 'research_native_preview', req, 'negative:existing_foreign_event')
            self.check('negative:existing_foreign_event', out['status'] == 'INSUFFICIENT_CONTEXT')
        await self.session(foreign_db, foreign, 'existing-foreign')
        # Exact noncommuting native histories, compared with independent sequential replay.
        permutation = copy.deepcopy(worlds[1])
        events = permutation['history']['tables']['events']
        spec = json.loads(next(e['content'] for e in events if 'event:' + str(e['id']) == permutation['refs']['root']))['source_spec']
        a, b = [spec['parameters']['actions'][i] for i in (1, 3)]
        for e, word in zip(events[:2], ([a, b], [b, a])):
            data = json.loads(e['content']); data['word'] = word; e['content'] = json.dumps(data)
        noncomm_db = materialize_copy(permutation, self.base / 'controls' / 'noncommuting')
        expected = pairs(permutation['history'], permutation['query'])[0]
        async def noncommuting(client, tools):
            out, _ = await self.call(client, noncomm_db, 'research_native_preview', native_request(permutation), 'negative:noncommutative_order')
            tid = out['witness']['test_id']
            self.check('negative:noncommutative_order', expected['hidden'] and
                       out['witness']['readouts'] == [expected['Sig_left'][tid], expected['Sig_right'][tid]])
        await self.session(noncomm_db, noncommuting, 'noncommuting')

    async def normalize004(self, world):
        db = materialize_copy(world, self.base / 'controls' / 'normalization004')
        full = materialize(world['history'], self.base / 'normalization004-full-audit.sqlite3')
        baseline = {a['id']: run_audit(full, a) for a in world['candidates']}
        async def exercise(client, tools):
            for level in ('C0', 'C1', 'C2', 'C3', 'C4'):
                req = {'project': world['project'], 'focus': 'zero microtheory audit',
                       'source_event_ids': [e['id'] for e in world['history']['tables']['events']],
                       'query_scope': {'level': level, 'candidates': world['candidates']}, 'budget': {}}
                out, _ = await self.call(client, db, 'research_normalize_preview', req, '004_MCP:' + level)
                view = out['view']
                projected = materialize(view['audit_context'], self.base / ('normalization004-MCP-' + level + '.sqlite3')) if level != 'C4' else None
                for a in world['candidates']:
                    answer = audit_projection(projected, view, a, world['history'])
                    self.check('004_MCP:' + level + ':' + a['id'], answer == baseline[a['id']] if level != 'C4'
                               else answer['status'] == 'INSUFFICIENT_CONTEXT')
                if level != 'C4':
                    reps = {c['representation'] for c in out['claims']}
                    self.check('004_MCP:' + level + ':point_germ_separate', level == 'C0' or {'point_value', 'analytic_germ'} <= reps)
                    self.check('004_MCP:' + level + ':loss_recovery', all('recovery' in x for x in out['loss_ledger']))
        await self.session(db, exercise, 'normalization004-MCP')


def initialize_baseline():
    from attention_qa import configure
    from qa_positive_acceptance import oauth
    from transfer_qa import Session
    cfg = configure()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    b = Path.home() / '.local/state/livingmath/preview008' / stamp
    b.mkdir(parents=True, mode=0o700)
    db = (Path(cfg['LIVE_MATH_DATA_DIR']) / 'research.sqlite3').resolve(strict=True)
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(b / 'research-before.sqlite3') as dst:
        src.backup(dst)
    (b / 'research-before.sqlite3').chmod(0o600)
    write_json(b / 'before.json', snapshot(db))
    paths = [ROOT / 'AGENTS.md', *SOURCE.glob('*.py'), *SOURCE.glob('*.json'), *[p for p in (ROOT / 'docs/qa').rglob('*') if p.is_file()]]
    write_json(b / 'protected-hashes.json', {str(p.resolve()): sha(p) for p in paths})
    write_json(b / 'metadata.json', {'private': str(b), 'db': str(db), 'backup_sha256': sha(b / 'research-before.sqlite3')})
    folder = b / 'live-readonly'; folder.mkdir()
    client = Session(folder, db, cfg['LIVE_MATH_PUBLIC_URL'])
    async def read(c):
        write_json(b / 'preflight.json', {'health': await c.call('service_health', {}),
                   'tools': (await c.session.list_tools()).model_dump(mode='json'),
                   'RH_frontier': await c.call('research_frontier', {'project': 'RH', 'include_closed': True})})
    client.work = read; oauth(cfg, client)
    return b


def freeze(base):
    original = json.loads((ORIGINAL007 / 'worlds.json').read_text())
    worlds = copy.deepcopy(original)
    for w in original[3:6]:
        fresh = changed(w, 'fresh'); fresh['fresh_heldout'] = True; worlds.append(fresh)
    for w in worlds:
        w['database'] = str(materialize_copy(w, base / 'fixtures' / w['id']))
    oracle = [{'world': w['id'], 'pairs': pairs(w['history'], w['query']),
               'attention': attention(w['history'], w['query'])} for w in worlds]
    write_json(base / 'worlds.json', worlds); write_json(base / 'oracle.json', oracle)
    files = [*SOURCE.glob('native_preview008*'), SOURCE / 'test_native_preview008.py',
             *SOURCE.glob('live_constructive007*.py'), *SOURCE.glob('live_transfer006*.py'),
             SOURCE / 'normalizer.py', SOURCE / 'normalization-schema.json', ORIGINAL007 / 'oracle.json']
    files = [p for p in files if p.is_file()]
    write_json(base / 'frozen-manifest.json', {str(p.resolve()): sha(p) for p in files + [base / 'worlds.json', base / 'oracle.json']})
    write_json(base / 'preregistration.json', {'protocol': '008.P0.P1.2', 'original007_pairs': 120, 'fresh_pairs': 45,
        'primary': 'Cold actual MCP bounded vs constructive, same source/D/caps and unchanged T. Compare native I and total I+T calls, roundtrip/worker CPU/wall/RSS/serialization separately.',
        'order': ['bounded', 'constructive'], 'LLM_calls': 0, 'cache': 'No cross-request native or normalization cache. Existing bounded8 normalization cache measured separately, not a public MCP speedup.',
        'production_deployment': False, 'correctness_gate': 'zero false witnesses/grants/missed bounded distinction/source leakage/DB deltas; full legacy regressions',
        'speedup_gate': 'No speedup requirement; measured cold wall ratio determines NO/INCONCLUSIVE rather than blocking functional P0.',
        'CPU_meter': 'Per-child OS wait4 through exit including final JSON serialization and teardown; boundary thread CPU separate. Self-reported pre-output CPU is diagnostic only.',
        'resource_limits': {'input_bytes': 65536, 'source_bytes': 4_000_000, 'events': 2000, 'native_calls': 2048, 'suffix': 2, 'worker_memory_MiB': 1024, 'deadline_ms': 5000}})
    return worlds, oracle


def cache_secondary(base, worlds):
    rows = []
    for w in worlds[:8]:
        cache = ContextNormalizer(); times = []
        values = []
        for _ in range(3):
            started = time.perf_counter_ns()
            values.append(cache.normalize(w['history'], 'source-certified interpretation', [w['query']], 'C2'))
            times.append(time.perf_counter_ns() - started)
        assert values[0] == values[1] == values[2] and len(cache.cache) <= 8
        rows.append({'world': w['id'], 'cold_then_repeats_ns': times, 'cache_entries': len(cache.cache),
                     'public_MCP_cache_hit': False, 'native_cache': False})
    write_json(base / 'cache-secondary.json', {'scope': 'Existing bounded normalization cache only, within one process; not a claim about fresh MCP workers.', 'rows': rows})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-dir', type=Path, help='Private pre-edit baseline; each invocation creates a new cohort')
    parser.add_argument('--prior-cohort', type=Path, help='Require unchanged worlds/oracle before a cost-only corrected cohort')
    args = parser.parse_args()
    baseline = args.baseline_dir.resolve(strict=True) if args.baseline_dir else initialize_baseline()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    base = baseline / 'cohorts' / stamp; base.mkdir(parents=True, mode=0o700, exist_ok=False)
    write_json(base / 'metadata.json', {'baseline': str(baseline), 'report': str(ROOT / 'docs/qa/LM-NATIVE-PREVIEW-008' / stamp)})
    Path('/tmp/lm008_cohort').write_text(str(base))
    acceptance = Acceptance(base)
    failure = None
    try:
        worlds, oracle = freeze(base)
        if args.prior_cohort:
            prior = json.loads((args.prior_cohort / 'worlds.json').read_text())
            same_worlds = [{k: v for k, v in w.items() if k != 'database'} for w in worlds] == [
                {k: v for k, v in w.items() if k != 'database'} for w in prior]
            same_oracle = (base / 'oracle.json').read_bytes() == (args.prior_cohort / 'oracle.json').read_bytes()
            write_json(base / 'corpus-replay-check.json', {'prior_cohort': str(args.prior_cohort),
                'same_worlds_except_private_database_paths': same_worlds, 'same_oracle_bytes': same_oracle,
                'math_I_T_source_laws_domains_and_gates_changed': False, 'change': 'Per-child wait4 CPU/RSS measurement only'})
            acceptance.check('cost_fix_same_corpus', same_worlds and same_oracle)
        with (base / 'pytest.txt').open('w') as out:
            subprocess.run([sys.executable, '-m', 'pytest', '-q', str(SOURCE)], stdout=out, stderr=subprocess.STDOUT, check=True)
        print(json.dumps({'phase': 'full_pytest', 'status': 'PASS'}), flush=True)
        reg = run_regression(base / 'historical86', baseline / 'research-before.sqlite3')
        acceptance.check('historical86', reg['result'] == 'PASS')
        from normalization_qa import prepare_p0, run_p0
        n004 = base / 'normalization004'; n004.mkdir()
        w004 = prepare_p0(n004); result004 = run_p0(n004, w004)
        acceptance.check('normalizer004_2304', result004['result'] == 'PASS' and result004['exact_complete_matches'] == 2304)
        # Re-run the original007 suite with unchanged inputs/oracle; its feedback writes only its own private fixtures.
        from live_constructive007_qa import run_p0 as original007_run
        p007 = base / 'baseline007'; p007.mkdir(); (p007 / 'databases').mkdir()
        prior = copy.deepcopy(worlds[:8])
        for w in prior:
            w['database'] = str(materialize_copy(w, p007 / 'databases' / w['id']))
        write_json(p007 / 'worlds.json', prior); shutil.copyfile(ORIGINAL007 / 'oracle.json', p007 / 'oracle.json')
        original007_run(p007)
        acceptance.check('original007', json.loads((p007 / 'P0-result.json').read_text())['correctness'] == 'PASS')
        async def run():
            await acceptance.normalize004(w004[0])
            await acceptance.controls(worlds)
            for w, oracle_world in zip(worlds, oracle):
                await acceptance.world(w, oracle_world)
        asyncio.run(run())
        cache_secondary(base, worlds)
        acceptance.check('nonoptimal_I_witness_not_T', any(x['witness'] and x['witness']['test_id'] != x['T_test_id']
                         for x in acceptance.costs if x['mode'] == 'constructive' and x['T_test_id']))
        from native_preview008_report import stage_patch
        stage_patch(base, acceptance, baseline)
    except BaseException as error:
        failure = {'classification': 'SOFTWARE_OR_HARNESS_OR_TRANSPORT', 'exception': str(error), 'traceback': traceback.format_exc()}
        write_json(base / 'run-failure.json', failure)
        print(json.dumps({'status': 'FAIL', 'reason': str(error), 'cohort': str(base)}), flush=True)
    finally:
        from native_preview008_report import export
        print(json.dumps(export(base, failure)), flush=True)


if __name__ == '__main__':
    main()
