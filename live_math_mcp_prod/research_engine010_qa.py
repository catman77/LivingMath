"""010 source-contract acceptance: reproduce exact legacy boundaries, then enforce the stop gate."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version as package_version
import json
import os
from pathlib import Path
import resource
import shutil
import sqlite3
import subprocess
import sys
import time
import traceback

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from normalizer import digest
from normalization_oracle import materialize
from normalization_regression import Tap, run_regression
from native_preview008_qa import readonly_state
from research_cycle009 import operation, proposal, law_payload
from qa_positive_acceptance import write_json, snapshot

SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parent
PRIOR009 = ROOT / 'docs/qa/LM-RESEARCH-CYCLE-009/20261027T061232007705Z'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspection():
    ledger = [json.loads(s) for s in (PRIOR009 / 'cycle-ledger.jsonl').read_text().splitlines()]
    findings = []
    for step in ledger:
        source = json.loads((PRIOR009 / 'source-snapshots' / (step['world'] + '-step' + str(step['cycle_index']) + '-after.json')).read_text())
        event = next(e for e in source['tables']['events'] if e['id'] == step['measurement_event_id'])
        data = json.loads(event['content'])
        findings.append({'world': step['world'], 'cycle_index': step['cycle_index'], 'move_id': step['move_id'],
            'measurement_event_id': event['id'], 'event_sha256': digest(event), 'actual_event': event,
            'present_metadata': sorted(data), 'binding_envelope_present': 'measurement_binding' in data,
            'missing': [k for k in ('move_id', 'audit_id', 'activation_operation_id', 'obligation_id',
                'proposal_fingerprint', 'source_bindings', 'suffix', 'executor_id') if k not in data],
            'status': 'INSUFFICIENT_MEASUREMENT_BINDING'})
    return findings


class Acceptance:
    def __init__(self, base):
        self.base, self.calls, self.checks = base, [], []

    def check(self, name, valid, evidence=None):
        row = {'invariant': name, 'result': 'PASS' if valid else 'FAIL', 'evidence': evidence}
        self.checks.append(row); write_json(self.base / 'checks.json', self.checks)
        if not valid:
            write_json(self.base / 'unexpected-failure.json', row)
            raise AssertionError(name)

    async def session(self, db, label, work, phase_a=False):
        directory = self.base / label; directory.mkdir(exist_ok=False)
        script = SOURCE / ('research_engine010_server.py' if phase_a else 'mcp_server.py')
        args = [str(script), '--db', str(db)] if phase_a else [str(script), 'stdio']
        params = StdioServerParameters(command=sys.executable, args=args,
            env={**os.environ, 'LIVE_MATH_DB': str(db), 'LIVE_MATH_NATIVE_PREVIEW': '1'})
        with (directory / 'stderr.txt').open('w') as error:
            async with stdio_client(params, errlog=error) as (read, write):
                async with ClientSession(Tap(read, directory / 'wire.jsonl', 'response'),
                                         Tap(write, directory / 'wire.jsonl', 'request')) as client:
                    initialized = (await client.initialize()).model_dump(mode='json')
                    tools = (await client.list_tools()).model_dump(mode='json')
                    write_json(directory / 'schemas.json', {'initialize': initialized, 'tools': tools})
                    await work(client, tools)

    async def call(self, client, db, tool, args, label, readonly=False):
        before = readonly_state(db); started = time.perf_counter_ns()
        response = await client.call_tool(tool, args)
        wall = time.perf_counter_ns() - started
        after = readonly_state(db)
        raw = response.model_dump(mode='json')
        decoded = None if response.isError else (response.structuredContent or json.loads(response.content[0].text))
        row = {'index': len(self.calls) + 1, 'label': label, 'tool': tool, 'arguments': args, 'response': raw,
               'decoded_response': decoded,
               'before': before, 'after': after, 'readonly_unchanged': before == after, 'MCP_roundtrip_wall_ns': wall}
        self.calls.append(row)
        with (self.base / 'calls.jsonl').open('a') as out: out.write(json.dumps(row, ensure_ascii=False) + '\n')
        if readonly or response.isError:
            self.check(label + ':no_DB_delta', before == after)
        if response.isError:
            return None
        return decoded

    async def repro_legacy(self, db, source, world, native):
        self.check('legacy_copy_is_isolated', db.is_relative_to(self.base))
        events = {e['id']: e for e in source['tables']['events']}
        root_id = native['question']['root_event_id']; root = json.loads(events[root_id]['content'])['source_spec']
        histories = {h['id']: int(h['ref'].split(':')[1]) for h in root['hypotheses'] if h['predictive']}
        fixture_id = next(e['id'] for e in events.values() if e['kind'] == 'qa_source')
        binding = {'obligation_id': native['active_frontier_id'], 'root_id': root_id, 'fixture_id': fixture_id,
                   'version': 1, 'histories': histories}
        async def work(client, tools):
            self.check('legacy_staging_20', len(tools['tools']) == 20)
            move = proposal(world, binding, operation(world, 't1', {'not_a_measurement': True}, '010 legacy boundary reproduction only'))
            record = await self.call(client, db, 'record_research_move', {'project': world['project'], 'move': move,
                'request_key': world['project'] + ':010-repro-propose'}, 'legacy-propose')
            self.check('legacy_record_not_activation', not record['execution_permission']['allowed'])
            audited = await self.call(client, db, 'audit_research_move', {'project': world['project'], 'move_id': record['id'],
                'request_key': world['project'] + ':010-repro-audit'}, 'legacy-audit')
            grant = await self.call(client, db, 'transition_research_move', {'project': world['project'], 'move_id': record['id'],
                'action': 'activate_experiment', 'request_key': world['project'] + ':010-repro-activate'}, 'legacy-activate')
            self.check('legacy_scoped_grant_only_after_explicit_activation', grant['execution_permission']['allowed'])
            result = await self.call(client, db, 'transition_research_move', {'project': world['project'], 'move_id': record['id'],
                'action': 'complete', 'request_key': world['project'] + ':010-repro-complete',
                'evidence_refs': ['event:' + str(fixture_id)], 'reason': 'Boundary reproduction: this is an existing premise, not a measured event.',
                'result': {'outcome': 'INCONCLUSIVE', 'summary': 'No measurement performed; generic legacy existence-check reproduction.', 'data': {}}}, 'red1-premise-completion')
            self.check('red1_legacy_existence_contract_reproduced', result['status'] == 'COMPLETED' and result['proof_status'] == 'unverified')
            self.boundary_move_id = record['id']; self.fixture_id = fixture_id
            req = json.loads(json.dumps(native)); req['question'].pop('known_fingerprints', None)
            first = await self.call(client, db, 'research_native_preview', req, 'red2-repeat-first', readonly=True)
            req['question']['known_fingerprints'] = []
            repeat = await self.call(client, db, 'research_native_preview', req, 'red2-explicit-empty', readonly=True)
            self.check('red2_caller_local_history_boundary', first['status'] == repeat['status'] == 'NEW_DISTINCTION'
                and first['interpretation']['fingerprint'] == repeat['interpretation']['fingerprint'])
            # Append a genuine display-label variant; do not edit existing source rows.
            names = {a: 'display_' + str(i) for i, a in enumerate(root['parameters']['actions'])}
            renamed_refs = {}
            for old_id in [int(ref.split(':')[1]) for ref in root['histories']]:
                data = json.loads(events[old_id]['content']); data['word'] = [names[a] for a in data['word']]
                row = await self.call(client, db, 'record_result', {'project': world['project'], 'kind': 'hypothesis',
                    'focus': '010 display-label variant', 'result': json.dumps(data), 'parent_id': old_id,
                    'request_key': world['project'] + ':010-alias:' + str(old_id)}, 'alias-history')
                renamed_refs['event:' + str(old_id)] = 'event:' + str(row['id'])
            clone = json.loads(json.dumps(root)); clone['parameters']['actions'] = [names[a] for a in root['parameters']['actions']]
            clone['histories'] = [renamed_refs[r] for r in root['histories']]
            for h in clone['hypotheses']: h['ref'] = renamed_refs.get(h['ref'], h['ref'])
            for test in clone['tests']: test['suffix'] = [names[a] for a in test['suffix']]
            row = await self.call(client, db, 'record_result', {'project': world['project'], 'kind': 'hypothesis',
                'focus': '010 renamed source', 'result': json.dumps({'source_spec': clone, 'scope': world['scope'], 'version': 1}),
                'parent_id': root_id, 'request_key': world['project'] + ':010-alias-root'}, 'alias-root')
            from research_cycle009 import event_rows
            current = event_rows(db, world['project']); alias_root = current[row['id']]
            law = await self.call(client, db, 'record_result', {'project': world['project'], 'kind': 'hypothesis',
                'focus': '010 renamed law', 'result': json.dumps(law_payload(world, alias_root, 1)),
                'parent_id': row['id'], 'request_key': world['project'] + ':010-alias-law'}, 'alias-law')
            current = event_rows(db, world['project'])
            req['question'].update(root_event_id=row['id'], certificate_event_id=law['id'],
                left_history_id=int(renamed_refs['event:' + str(native['question']['left_history_id'])].split(':')[1]),
                right_history_id=int(renamed_refs['event:' + str(native['question']['right_history_id'])].split(':')[1]))
            req['source_event_ids'] = sorted(current); req['source_bindings'] = [{'event_id': i, 'sha256': digest(current[i])} for i in sorted(current)]
            renamed = await self.call(client, db, 'research_native_preview', req, 'red3-rename-empty-history', readonly=True)
            self.check('red3_rename_is_not_new_fingerprint', renamed['status'] == 'NEW_DISTINCTION' and
                renamed['interpretation']['fingerprint'] == first['interpretation']['fingerprint'])
            write_json(self.base / 'legacy-red-summary.json', {'completion_with_premise': 'LEGACY_COMPLETED_UNVERIFIED',
                'repeat_with_empty_history': 'LEGACY_NEW_RELATIVE_TO_EMPTY_CALLER_CONTEXT',
                'rename': 'SAME_FINGERPRINT_NOT_NEW_MATH', 'layer': 'new010 contract gap; no assertion that legacy generic API promised stronger semantics',
                'move_id': record['id'], 'premise_event_id': fixture_id})
        await self.session(db, 'legacy-repro', work)

    async def typed_guards(self, db, native):
        async def work(client, tools):
            self.check('phaseA_3_readonly_tools', len(tools['tools']) == 3 and all(t['annotations']['readOnlyHint'] for t in tools['tools']))
            request = {'project': native['project'], 'move_id': self.boundary_move_id, 'measurement_event_id': self.fixture_id}
            first = await self.call(client, db, 'research_cycle_validate_receipt', {'request': request}, 'typed-premise-rejection', True)
            self.check('typed_premise_is_not_measurement', first['status'] == 'INSUFFICIENT_MEASUREMENT_BINDING'
                       and first['commit_enabled'] is False and first['execution_permission'] == {'allowed': False})
            for i in range(2):
                req = json.loads(json.dumps(native))
                if i == 0: req['question'].pop('known_fingerprints', None)
                else: req['question']['known_fingerprints'] = []
                out = await self.call(client, db, 'research_cycle_preview', {'request': req}, 'typed-novelty-' + str(i), True)
                self.check('typed_novelty_incomplete_' + str(i), out['status'] == 'NOVELTY_CONTEXT_INCOMPLETE'
                    and out['known_fingerprints'] is None and out['I_T_executed'] is False and out['next_step'] is None)
            out = await self.call(client, db, 'research_novelty_snapshot', {'request': native}, 'typed-authority-snapshot', True)
            self.check('missing_journal_not_complete_empty_history', out['status'] == 'NOVELTY_CONTEXT_INCOMPLETE'
                and out['snapshot_complete'] is False and out['caller_known_fingerprints_authoritative'] is False)
            for case in ('foreign', 'stale', 'hash', 'C4', 'quota'):
                req = json.loads(json.dumps(native))
                if case == 'foreign': req['project'] = 'OTHER'
                elif case == 'stale': req['active_frontier_version'] += 99
                elif case == 'hash': req['source_bindings'][0]['sha256'] = 'f' * 64
                elif case == 'C4': req['question']['context_level'] = 'C4'
                else: req['budget'] = {**req.get('budget', {}), 'max_events': 1}
                out = await self.call(client, db, 'research_cycle_preview', {'request': req}, 'typed-context-' + case, True)
                self.check('typed-context-' + case + ':denied', out['status'] == 'INSUFFICIENT_CONTEXT'
                    and not out['execution_permission']['allowed'] and out['I_T_executed'] is False)
            repeated = await self.call(client, db, 'research_cycle_validate_receipt', {'request': request}, 'typed-validation-repeat', True)
            self.check('typed_readonly_validation_idempotent', repeated == first)
            bad = {**request, 'project': 'OTHER'}
            out = await self.call(client, db, 'research_cycle_validate_receipt', {'request': bad}, 'typed-foreign', True)
            self.check('typed_foreign_denied', out['status'] == 'REJECTED')
            out = await self.call(client, db, 'research_cycle_validate_receipt', {'request': {**request, 'verified': True}}, 'typed-verified-field', True)
            self.check('typed_model_cannot_add_verified', out is None)
        await self.session(db, 'phase-a', work, phase_a=True)

    async def historical_bindings(self):
        for finding in inspection():
            label = finding['world'] + '-step' + str(finding['cycle_index'])
            history = json.loads((PRIOR009 / 'source-snapshots' / (label + '-after.json')).read_text())
            db = self.base / (label + '.sqlite3')
            materialize(history, db)
            async def work(client, tools):
                request = {'project': history['project'], 'move_id': finding['move_id'],
                           'measurement_event_id': finding['measurement_event_id']}
                response = await self.call(client, db, 'research_cycle_validate_receipt', {'request': request}, label, True)
                self.check(label + ':no_invented_receipt', response['status'] == 'INSUFFICIENT_MEASUREMENT_BINDING'
                    and response['no_reconstruction_from_caller_or_harness_trace']
                    and not response['execution_permission']['allowed'])
            await self.session(db, label, work, phase_a=True)


def initialize():
    """New private BackupAPI baseline; public MCP preflight is strictly read-only."""
    from contextlib import closing
    from attention_qa import configure
    from qa_positive_acceptance import oauth
    from transfer_qa import Session
    cfg = configure()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    baseline = Path.home() / '.local/state/livingmath/engine010' / stamp
    baseline.mkdir(parents=True, mode=0o700, exist_ok=False)
    db = (Path(cfg['LIVE_MATH_DATA_DIR']) / 'research.sqlite3').resolve(strict=True)
    with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)) as source, closing(sqlite3.connect(baseline / 'research-before.sqlite3')) as target:
        source.backup(target)
    (baseline / 'research-before.sqlite3').chmod(0o600)
    write_json(baseline / 'before.json', snapshot(db))
    write_json(baseline / 'readonly-before.json', readonly_state(db))
    paths = [ROOT / 'AGENTS.md', *SOURCE.glob('*.py'), *SOURCE.glob('*.json'),
             *[p for p in (ROOT / 'docs/qa').rglob('*') if p.is_file()]]
    write_json(baseline / 'protected-files.json', {str(p.resolve()): sha(p) for p in paths})
    write_json(baseline / 'metadata.json', {'db': str(db), 'private': str(baseline),
        'backup_sha256': sha(baseline / 'research-before.sqlite3'), 'production_readonly': True})
    folder = baseline / 'live-readonly'; folder.mkdir()
    client = Session(folder, db, cfg['LIVE_MATH_PUBLIC_URL'])
    async def read(c):
        before = readonly_state(db)
        tools = (await c.session.list_tools()).model_dump(mode='json')
        health = await c.call('service_health', {})
        contract = await c.call('research_contract', {})
        write_json(baseline / 'public-preflight.json', {'initialize': c.initialized, 'tools': tools,
            'health': health, 'research_contract': contract, 'readonly_before': before, 'readonly_after': readonly_state(db)})
        assert len(tools['tools']) == 20 and before == readonly_state(db)
    client.work = read
    oauth(cfg, client)
    return baseline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-dir', type=Path, help='Existing private010 baseline; otherwise create a fresh read-only BackupAPI baseline.')
    args = parser.parse_args(); baseline = args.baseline_dir.resolve(strict=True) if args.baseline_dir else initialize()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'); base = baseline / 'cohorts' / stamp
    base.mkdir(parents=True, mode=0o700, exist_ok=False); Path('/tmp/lm010_cohort').write_text(str(base))
    write_json(base / 'metadata.json', {'baseline': str(baseline), 'report': str(ROOT / 'docs/qa/LM-RESEARCH-ENGINE-010' / stamp)})
    findings = inspection(); write_json(base / 'source-binding.json', findings)
    write_json(base / 'first-failure.json', {'classification': 'MISSING_SOURCE_CONTRACT_METADATA',
        'status': 'STOP_WITH_RCA', 'measurement_events': [r['measurement_event_id'] for r in findings],
        'reason': 'Existing009 events have no bound measurement envelope. Do not backfill from caller/harness traces.'})
    files = [*SOURCE.glob('research_engine010*.py'), *SOURCE.glob('test_research_engine010*.py'),
             PRIOR009 / 'oracle.json', PRIOR009 / 'manifest-sha256.json']
    (base / 'frozen-sources').mkdir()
    for p in files: shutil.copyfile(p, base / 'frozen-sources' / p.name)
    write_json(base / 'source-hashes.json', {str(p): sha(p) for p in files})
    write_json(base / 'environment.json', {'python_executable': sys.executable, 'python_version': sys.version,
        'mcp_sdk_version': package_version('mcp'),
        'requirements_sha256': {p.name: sha(p) for p in SOURCE.glob('requirements*.txt')}})
    acceptance = Acceptance(base); failure = None
    started, cpu = time.perf_counter_ns(), time.process_time_ns()
    children_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    try:
        with (base / 'pytest.txt').open('w') as out:
            subprocess.run([sys.executable, '-m', 'pytest', '-q', str(SOURCE)], stdout=out, stderr=subprocess.STDOUT,
                env={k: v for k, v in os.environ.items() if k != 'LIVE_MATH_NATIVE_PREVIEW'}, check=True)
        print('Full pytest PASS', flush=True)
        prior = os.environ.pop('LIVE_MATH_NATIVE_PREVIEW', None)
        try: legacy = run_regression(base / 'historical86', baseline / 'research-before.sqlite3')
        finally:
            if prior is not None: os.environ['LIVE_MATH_NATIVE_PREVIEW'] = prior
        acceptance.check('historical86', legacy['result'] == 'PASS')
        source = json.loads((PRIOR009 / 'source-snapshots/affine-step1-before.json').read_text())
        world = json.loads((PRIOR009 / 'world-inputs/affine.json').read_text())
        previous_calls = json.loads((PRIOR009 / 'mcp-transcript.json').read_text())['calls']
        native = next(c['arguments'] for c in previous_calls if c['tool'] == 'research_native_preview')
        write_json(base / 'reproducer-inputs.json', {'source': source, 'world': world, 'native': native})
        db = base / 'isolated.sqlite3'; materialize(source, db)
        async def run():
            await acceptance.repro_legacy(db, source, world, native)
            await acceptance.typed_guards(db, native)
            await acceptance.historical_bindings()
        asyncio.run(run())
    except BaseException as error:
        failure = {'classification': 'UNEXPECTED_PHASE_A_FAILURE', 'error': str(error), 'traceback': traceback.format_exc()}
        write_json(base / 'run-failure.json', failure); print(json.dumps(failure), flush=True)
    finally:
        children = resource.getrusage(resource.RUSAGE_CHILDREN)
        write_json(base / 'process-costs.json', {'wall_ns': time.perf_counter_ns() - started,
            'driver_CPU_ns': time.process_time_ns() - cpu,
            'children_CPU_seconds': children.ru_utime + children.ru_stime - children_before.ru_utime - children_before.ru_stime,
            'children_max_RSS_KiB': children.ru_maxrss, 'driver_max_RSS_KiB': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'scope': 'timed QA section: pytest, historical86, legacy reproducers and Phase-A MCP refusal guards; excludes interpreter startup/imports/source freeze/report export; not a completed010 cycle'})
        from research_engine010_report import export
        print(json.dumps(export(base, failure)), flush=True)


if __name__ == '__main__':
    main()
