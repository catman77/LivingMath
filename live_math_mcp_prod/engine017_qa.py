"""Frozen017 acceptance using real MCP; driver supplies only owner/executor authority.

All next actions and posterior/applicability are obtained from the server. The
independent frozen oracle is loaded only after a native attempt is recorded.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import shutil
import sqlite3
import subprocess
import sys
import time
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from normalizer import canonical, digest
from qa_positive_acceptance import write_json, snapshot
from native_preview008_server import MeasuredProcess
from normalization_regression import Tap
from research_store import ResearchStore
from typed_cycle011_store import install as install011
from law_validation014_store import install as guards
from engine017_store import install
from engine017_fixtures import seed

SOURCE = Path(__file__).resolve().parent


def append(path, value):
    with path.open('a') as stream:
        stream.write(canonical(value) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def backup(source, target):
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(target) as dst:
        src.backup(dst)


class Acceptance017:
    def __init__(self, base, output):
        self.base, self.out = base, output
        output.mkdir(parents=True, exist_ok=False)
        self.private = base / ('run-' + output.name)
        self.workspace = self.private / 'workspace'
        self.seals = self.private / 'seals'
        self.workspace.mkdir(parents=True, mode=0o700)
        self.seals.mkdir(mode=0o700)
        self.db, self.legacy = self.workspace / 'engine.sqlite3', self.workspace / 'legacy.sqlite3'
        backup(base / 'canonical.sqlite3', self.db)
        backup(base / 'canonical.sqlite3', self.legacy)
        install011(self.db, self.legacy)
        guards(self.db)
        install(self.db)
        self.policy = json.loads((base / 'frozen/pre-registration.json').read_text())
        self.checks, self.calls, self.receipts, self.costs = [], [], [], []
        self.worlds = {}
        self.session_count = 0
        self.started, self.cpu = time.perf_counter_ns(), time.process_time_ns()
        self.child_start = resource.getrusage(resource.RUSAGE_CHILDREN)
        shutil.copy2(base / 'frozen/pre-registration.json', output / 'pre-registration.json')
        shutil.copy2(base / 'frozen/seal.json', output / 'pre-registration-seal.json')
        shutil.copy2(base / 'frozen/oracle.py', output / 'frozen-oracle.py')
        sources = output / 'sources'
        sources.mkdir()
        for p in SOURCE.glob('engine017*.py'):
            shutil.copy2(p, sources / p.name)
        shutil.copy2(SOURCE / 'test_engine017.py', sources / 'test_engine017.py')
        write_json(output / 'implementation-lock.json', {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources.iterdir()})

    def check(self, name, ok, evidence=None):
        self.checks.append({'invariant': name, 'result': 'PASS' if ok else 'FAIL', 'evidence': evidence})
        write_json(self.out / 'checks.json', self.checks)
        if not ok:
            write_json(self.out / 'first-failure.json', self.checks[-1])
            raise AssertionError(name)

    @asynccontextmanager
    async def session(self, enabled=True, database=None):
        self.session_count += 1
        label = 'session-' + str(self.session_count)
        denied = [self.base / 'frozen/oracle.py'] + list(self.seals.iterdir())
        args = [str(SOURCE / 'engine017_server.py'), '--canonical', str(self.legacy), '--db', str(database or self.db)]
        for p in denied:
            args += ['--forbidden', str(p)]
        env = {**os.environ, 'LIVE_MATH_ENGINE_017': '1' if enabled else '0',
               'LM014_NATIVE_LEDGER': str(self.workspace / 'native-I-T.jsonl')}
        parameters = StdioServerParameters(command=sys.executable, args=args, env=env)
        with (self.out / (label + '-stderr.txt')).open('w') as error:
            async with stdio_client(parameters, errlog=error) as (read, write):
                async with ClientSession(Tap(read, self.out / 'mcp-wire.jsonl', 'response'), Tap(write, self.out / 'mcp-wire.jsonl', 'request')) as client:
                    initialized = (await client.initialize()).model_dump(mode='json')
                    tools = (await client.list_tools()).model_dump(mode='json')
                    append(self.out / 'catalogues.jsonl', {'session': label, 'enabled': enabled, 'initialize': initialized, 'tools': tools})
                    self.check(label + ':capabilities', len(tools['tools']) == (27 if enabled else 24))
                    self.check(label + ':no_operator_tool', not {'activate', 'execute', 'commit', 'register_source'} & {t['name'] for t in tools['tools']})
                    yield client

    async def call(self, client, name, arguments, allow_error=False):
        wall = time.perf_counter_ns()
        reply = await client.call_tool(name, arguments)
        raw = reply.model_dump(mode='json')
        text = ''.join(c.text for c in reply.content if c.type == 'text')
        try:
            value = reply.structuredContent if reply.structuredContent is not None else json.loads(text)
        except ValueError:
            value = {'error': text}
        row = {'call': len(self.calls) + 1, 'tool': name, 'arguments': arguments, 'response': raw,
               'driver_wall_ns': time.perf_counter_ns() - wall}
        self.calls.append(row)
        append(self.out / 'mcp-transcript.jsonl', row)
        if reply.isError and not allow_error:
            self.check('unexpected_MCP_error:' + name, False, value)
        return value, bool(reply.isError)

    def command(self, module, payload, database=None, action=None):
        args = [sys.executable, str(SOURCE / module), '--db', str(database or self.db)]
        if action:
            args.append(action)
        start = time.perf_counter_ns()
        proc = MeasuredProcess(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            stdout, stderr = proc.communicate(canonical(payload), timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.wait(); raise ValueError('NATIVE_WORKER_WALL_LIMIT')
        u = proc.child_usage
        self.costs.append({'module': module, 'action': action, 'CPU_ns': round((u.ru_utime + u.ru_stime) * 1e9),
            'wall_ns': time.perf_counter_ns() - start, 'peak_RSS_KiB': u.ru_maxrss, 'exit_code': proc.returncode})
        try:
            parsed = json.loads(stdout)
        except ValueError:
            parsed = {'ok': False, 'stdout': stdout, 'stderr': stderr}
        return parsed, proc.returncode

    def owner(self, action, payload):
        result, code = self.command('engine017_operator.py', payload, action=action)
        append(self.out / 'cycle-ledger.jsonl', {'authority': 'owner', 'action': action, 'request': payload, 'response': result})
        return result, code

    def execute(self, world, move_id, database=None, unreadable=False):
        payload = {'project': world['project'], 'move_id': move_id,
            'environment_file': '/denied-before-environment-open' if unreadable else world['environment'],
            'private_key_file': '/denied-before-key-open' if unreadable else world['private_key_file']}
        value, code = self.command('engine017_executor.py', payload, database=database)
        append(self.out / 'cycle-ledger.jsonl', {'authority': 'pinned external executor', 'request': {'project': world['project'], 'move_id': move_id}, 'response': value})
        return value, code

    def active_controls(self, world, pc):
        folder = self.private / 'active-controls'
        folder.mkdir(exist_ok=True)
        controls = []
        def mutate(label, fn):
            copy_db = folder / (label + '.sqlite3')
            backup(self.db, copy_db)
            with sqlite3.connect(copy_db) as c:
                fn(c)
            value, code = self.execute(world, pc['move_id'], copy_db, unreadable=True)
            passed = code != 0 and value.get('error') and 'denied-before-' not in value['error']
            controls.append({'control': label, 'PASS': bool(passed), 'response': value, 'expected': 'binding denial before opening environment/key'})
            self.check('active:' + label, passed, value)
        def change_pc(field, change):
            def do(c):
                row = c.execute('SELECT p.id,p.payload_json FROM typed011_precommits p JOIN typed011_moves m ON m.precommit_id=p.id WHERE m.move_id=?', (pc['move_id'],)).fetchone()
                payload = json.loads(row[1])
                change(payload)
                c.execute('DROP TRIGGER typed011_precommits_no_update')
                c.execute('UPDATE typed011_precommits SET payload_json=?,digest=? WHERE id=?', (canonical(payload), digest(payload), row[0]))
            return do
        mutate('observer', change_pc('observer', lambda p: p.update(observer={'projection': 'primary', 'mod': 2})))
        mutate('source_hash', change_pc('source_bindings', lambda p: p['source_bindings'][0].update(sha256='0' * 64)))
        mutate('ordered_suffix', change_pc('suffix', lambda p: p['suffix'].append(p['suffix'][0])))
        mutate('test_id', change_pc('test_id', lambda p: p.update(test_id='forged-test')))
        mutate('native_definition', change_pc('native', lambda p: p.update(native_definition_sha256='0' * 64)))
        def activation(c):
            c.execute('DROP TRIGGER typed011_activations_no_update')
            c.execute('UPDATE typed011_activations SET operation_id=999999 WHERE move_id=?', (pc['move_id'],))
        mutate('activation', activation)
        copy_db = folder / 'version.sqlite3'
        backup(self.db, copy_db)
        ob = ResearchStore(copy_db).frontier.history(world['obligation_id'])[-1]
        ResearchStore(copy_db).frontier.update(world['obligation_id'], ob['version'], {'statement': ob['statement'] + ' New reviewed version.'})
        value, code = self.execute(world, pc['move_id'], copy_db, unreadable=True)
        self.check('active:version', code != 0 and value.get('error') == 'STALE_OBLIGATION_VERSION', value)
        controls.append({'control': 'version', 'PASS': code != 0, 'response': value})
        write_json(self.out / 'active-negative-controls.json', controls)

    def oracle(self, world, execution, pc_preview):
        # Import occurs only after the actual native event exists. The server's
        # Landlock cannot read this frozen independent implementation.
        path = self.base / 'frozen/oracle.py'
        self.check('oracle_frozen_hash', hashlib.sha256(path.read_bytes()).hexdigest() == self.policy['oracle_sha256'])
        spec = importlib.util.spec_from_file_location('independent017_post_measurement_oracle', path)
        oracle = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(oracle)
        environment = json.loads(Path(world['environment']).read_text())
        env = execution['envelope']
        actual, coordinate, steps = oracle.replay(world['declaration'], environment['target_word'] + env['suffix_ordinals'])
        actual['admissibility'] = actual['admissibility'][-len(env['suffix_ordinals']):]
        if environment['mode'] == 'exact':
            good = actual == env['observed'] and coordinate == env['observed_coordinate']
        elif environment['mode'] == 'withheld_sensor':
            good = env['outcome'] == 'INCONCLUSIVE' and env['observed']['defined'] is False and env['observed']['observation'] is None
        else:
            good = env['outcome'] == 'ERROR' and env['observed_coordinate'] == [] and env['observed']['defined'] is False
        append(self.out / 'independent-oracle.jsonl', {'source': world['key'], 'mode': environment['mode'],
            'actual_counterfactual_or_exact_readout': actual, 'coordinate': coordinate, 'steps': steps,
            'actual_envelope': env, 'after_measurement_only': True, 'PASS': good})
        self.check(world['key'] + ':independent_oracle', good)

    async def cycle(self, client, world, step, expected):
        prefix = world['key'] + ':' + str(step)
        query = {'project': world['project'], 'known_fingerprints': [], 'latest_feedback': None}
        preview, _ = await self.call(client, 'research_cycle_next', {'query': query})
        self.check(prefix + ':server_proposal', preview['status'] == 'PROPOSAL_READY', preview)
        self.check(prefix + ':purpose', preview['purpose'] == ('DISCRIMINATE' if step == 0 else 'VALIDATE_TRANSFER'))
        self.check(prefix + ':no_inference_E', all(r['operation'] != 'E' for r in preview['native_trace']))
        self.check(prefix + ':independent_branch', bool(preview['independent_branch']) and all(h['status'] == 'ACTIVE' for h in preview['independent_branch']))
        alias, _ = await self.call(client, 'research_cycle_preview', {'request': {**query, 'display_label': 'renamed source'}})
        self.check(prefix + ':alias_same_distinction', alias['claim_fingerprint'] == preview['claim_fingerprint'])
        args = {'request': query, 'request_key': prefix}
        replies = await asyncio.gather(self.call(client, 'research_cycle_precommit', args), self.call(client, 'research_cycle_precommit', args))
        pc, repeat = replies[0][0], replies[1][0]
        self.check(prefix + ':concurrent_precommit', pc == repeat and not pc['execution_permission']['allowed'], replies)
        append(self.out / 'sealed-proposals.jsonl', {'source': world['key'], 'step': step, 'preview': preview, 'precommit': pc, 'sealed_UTC': datetime.now(timezone.utc).isoformat()})
        denied, code = self.execute(world, pc['move_id'], unreadable=True)
        self.check(prefix + ':no_owner_grant', code != 0 and denied.get('error') == 'NO_TYPED_ACTIVATION', denied)
        # The model-facing generic path must never grant/complete this typed move.
        for action in ('activate_experiment', 'complete'):
            before = snapshot(self.db)
            bad, error = await self.call(client, 'transition_research_move', {'project': world['project'], 'move_id': pc['move_id'],
                'action': action, 'request_key': prefix + ':forbidden-' + action, 'reason': 'Adversarial model control',
                **({'result': {'outcome': 'SUCCESS', 'summary': 'Fabricated'}, 'evidence_refs': ['event:' + str(world['fixture_id'])]} if action == 'complete' else {})}, True)
            self.check(prefix + ':generic_' + action + '_denied', error and snapshot(self.db) == before, bad)
        activation, code = self.owner('activate', {'project': world['project'], 'move_id': pc['move_id'], 'request_key': prefix})
        self.check(prefix + ':owner_activation', code == 0 and activation.get('ok'), activation)
        if world['key'] == 'A0' and step == 0:
            self.active_controls(world, pc)
        before = snapshot(self.db)
        premise, _ = await self.call(client, 'research_cycle_validate', {'project': world['project'], 'move_id': pc['move_id'], 'event_id': world['fixture_id']})
        self.check(prefix + ':premise_not_measurement', premise['status'] == 'INSUFFICIENT_MEASUREMENT_BINDING' and snapshot(self.db) == before, premise)
        measured, code = self.execute(world, pc['move_id'])
        self.check(prefix + ':native_attempt', code == 0 and measured.get('ok'), measured)
        execution = measured['result']
        env = execution['envelope']
        self.check(prefix + ':frozen_outcome', env['outcome'] == expected, env)
        shutil.copy2(execution['artifact_path'], self.out / ('native-' + prefix.replace(':', '-') + '.json'))
        self.oracle(world, execution, preview)
        validated, _ = await self.call(client, 'research_cycle_validate', {'project': world['project'], 'move_id': pc['move_id'], 'event_id': execution['event_id']})
        self.check(prefix + ':semantic_validation', validated['status'] == 'VALID_BOUND_MEASUREMENT' and validated.get('semantic_measurement_bound') and validated.get('signature_verified'), validated)
        request = {'project': world['project'], 'move_id': pc['move_id'], 'event_id': execution['event_id'], 'request_key': prefix,
            **{k: env[k] for k in ('outcome', 'observed', 'summary', 'reason', 'proof_status')}}
        if world['key'] == 'A0' and step == 0:
            with sqlite3.connect(self.db) as c:
                c.execute("CREATE TRIGGER planned017_journal_failure BEFORE INSERT ON typed011_journal BEGIN SELECT RAISE(ABORT,'PLANNED_JOURNAL_FAILURE'); END")
            stable = snapshot(self.db)
            fault, code = self.owner('commit', request)
            self.check('planned_journal_failure_atomic_rollback', code != 0 and 'PLANNED_JOURNAL_FAILURE' in str(fault) and snapshot(self.db) == stable, fault)
            with sqlite3.connect(self.db) as c:
                c.execute('DROP TRIGGER planned017_journal_failure')
        committed = await asyncio.gather(asyncio.to_thread(self.owner, 'commit', request), asyncio.to_thread(self.owner, 'commit', request))
        one, two = committed[0][0], committed[1][0]
        self.check(prefix + ':concurrent_commit', all(code == 0 and value.get('ok') for value, code in committed) and one['result']['receipt_id'] == two['result']['receipt_id'] and one['result']['idempotent'] != two['result']['idempotent'], committed)
        receipt = one['result'] if not one['result']['idempotent'] else two['result']
        self.check(prefix + ':terminal_unverified', receipt['status'] == 'COMPLETED' and receipt['proof_status'] == 'unverified' and not receipt['execution_permission']['allowed'])
        stable = snapshot(self.db)
        conflict, code = self.owner('commit', {**request, 'outcome': 'ERROR' if env['outcome'] != 'ERROR' else 'SUCCESS'})
        self.check(prefix + ':result_digest_immutable', code != 0 and 'RECEIPT_REQUEST_KEY_CONFLICT' in str(conflict) and snapshot(self.db) == stable)
        self.receipts.append({'source': world['key'], 'step': step, 'family': world['family'], 'receipt': receipt})
        append(self.out / 'typed-receipts.jsonl', self.receipts[-1])
        following, _ = await self.call(client, 'research_cycle_next', {'query': query})
        snapshot_view, _ = await self.call(client, 'research_novelty_snapshot', {'request': query})
        self.check(prefix + ':authoritative_journal', snapshot_view['snapshot_complete'] and len(snapshot_view['journal']) == step + 1)
        self.check(prefix + ':feedback_version', snapshot_view['feedback']['version'] == step + 1)
        if expected in ('SUCCESS', 'FAILURE'):
            self.check(prefix + ':next_from_feedback', following['status'] == 'PROPOSAL_READY' and following['purpose'] == 'VALIDATE_TRANSFER', following)
            self.check(prefix + ':no_repeated_claim', following['claim_fingerprint'] != preview['claim_fingerprint'])
            if expected == 'FAILURE':
                self.check(prefix + ':narrowed_applicability', bool(snapshot_view['feedback']['applicability']['excluded']) and bool(snapshot_view['feedback']['applicability']['retained']))
        else:
            waiting = 'AWAITING_INCONCLUSIVE_EVIDENCE' if expected == 'INCONCLUSIVE' else 'ERROR_REQUIRES_OPERATOR_REVIEW'
            self.check(prefix + ':honest_wait', following['status'] == waiting and not following['execution_permission']['allowed'], following)
            self.check(prefix + ':posterior_retained', len(snapshot_view['feedback']['applicability']['retained']) == len(world['declaration']['discrimination_histories']))
            frontier = ResearchStore(self.db).frontier.history(world['obligation_id'])[-1]
            self.check(prefix + ':obligation_stays_open', frontier['status'] == 'OPEN')
            artifact = json.loads(Path(execution['artifact_path']).read_text())
            if expected == 'ERROR':
                self.check(prefix + ':no_fake_measurement', artifact['source_receipt']['attempt']['trace'] == [] and artifact['source_receipt']['attempt']['quality'] == 'NO_OBSERVATION_INSTRUMENT_ERROR')
        append(self.out / 'feedback-replay.jsonl', {'source': world['key'], 'step': step, 'caller_history': [], 'caller_feedback': None,
            'authoritative_snapshot': snapshot_view, 'following': following})
        return following

    async def legacy_cycle(self, client):
        from qa_positive_acceptance import Acceptance
        folder = self.out / 'legacy-compatibility'
        folder.mkdir()
        runner = Acceptance(folder, self.legacy, 'https://not-used.invalid')
        async def call(name, arguments, allow_error=False):
            result, error = await self.call(client, name, arguments, allow_error)
            return None if error and allow_error else result
        runner.call = call
        await runner.event('source_event', {'fixture_sha256': runner.fixture_hash, 'bytes_hex': runner.fixture.hex(),
            'artifact': 'artifact:fixture.bin', 'software_qa_only': True, 'purpose': 'Explicit legacy route, never typed.'}, kind='qa_source', status='observation', parent=False)
        runner.seed()
        await runner.positive()
        self.check('explicit_legacy_completion_compatible', all(c['result'] == 'PASS' for c in runner.checks), runner.checks)

    async def context_fault_controls(self):
        """Owner-controlled corrupted copies; no mutation of accepted source history."""
        folder = self.private / 'context-faults'
        folder.mkdir()
        world = self.worlds['A0']
        # Compute the legitimate next fingerprint before inserting a conflicting raw entry.
        row = next(r for r in reversed(self.calls) if r['tool'] == 'research_cycle_next' and
            r['arguments']['query']['project'] == world['project'] and not r['response'].get('isError'))
        current = row['response'].get('structuredContent') or json.loads(''.join(c['text'] for c in row['response']['content'] if c['type'] == 'text'))
        for label in ('journal_conflict', 'uninspected_source', 'incomplete_source'):
            db = folder / (label + '.sqlite3')
            backup(self.db, db)
            with sqlite3.connect(db) as c:
                if label == 'journal_conflict':
                    receipt_id = c.execute('SELECT max(id) FROM typed011_receipts WHERE project=?', (world['project'],)).fetchone()[0]
                    c.execute('INSERT INTO typed011_journal(project,scope,source_family_id,claim_fingerprint,raw_sha256,receipt_id,payload_json) VALUES (?,?,?,?,?,?,?)',
                        (world['project'], world['manifest']['scope'], current['source_family_id'], current['claim_fingerprint'], '0' * 64, receipt_id,
                         canonical({'fault': 'Deliberate conflicting raw distinction in an owner-controlled copy.'})))
                elif label == 'uninspected_source':
                    row = c.execute('SELECT payload_json FROM engine017_sources WHERE project=?', (world['project'],)).fetchone()
                    manifest = json.loads(row[0]); manifest['inspection_status'] = 'DECLARED_UNINSPECTED'
                    c.execute('DROP TRIGGER engine017_sources_no_update')
                    c.execute('UPDATE engine017_sources SET payload_json=? WHERE project=?', (canonical(manifest), world['project']))
                else:
                    row = c.execute('SELECT content FROM events WHERE id=?', (world['root_id'],)).fetchone()
                    payload = json.loads(row[0]); payload.pop('source_spec')
                    c.execute('DROP TRIGGER events_014_no_update')
                    c.execute('UPDATE events SET content=? WHERE id=?', (canonical(payload), world['root_id']))
            async with self.session(True, db) as client:
                value, _ = await self.call(client, 'research_cycle_next', {'query': {'project': world['project']}})
                expected = 'REQUIRES_REVIEW' if label == 'journal_conflict' else 'INSUFFICIENT_CONTEXT'
                self.check(label + ':fails_closed', value['status'] == expected and not value['execution_permission']['allowed'], value)

    async def run(self):
        for case in self.policy['cases']:
            family = next(f for f in self.policy['families'] if f['id'] == case['family'])
            b = seed(self.db, self.workspace, self.seals, family, case, self.out.name)
            self.worlds[b['key']] = b
        write_json(self.out / 'source-envelopes.json', {k: {'source': w['manifest'], 'registration': w['registration']} for k, w in self.worlds.items()})
        async with self.session(False) as client:
            health, _ = await self.call(client, 'service_health', {})
            self.check('flag_off_old_health', health['version'] == '0.4.2')
        async with self.session(True) as client:
            for world in self.worlds.values():
                source, _ = await self.call(client, 'research_source_contract', {'project': world['project']})
                self.check(world['key'] + ':source_bound', source['source'] == world['manifest'])
                await self.cycle(client, world, 0, world['expected'])
            # All following choices come from server state, not a driver-built next request.
            for world in self.worlds.values():
                if world['expected'] in ('SUCCESS', 'FAILURE'):
                    await self.cycle(client, world, 1, 'SUCCESS')
            await self.legacy_cycle(client)
            q = {'project': self.worlds['A0']['project']}
            for label, delta in [('observer', {'observer': {'projection': 'primary', 'mod': 2}}), ('version', {'version': 2}),
                ('C4', {'context_level': 'C4'}), ('source', {'source_id': 'wrong'})]:
                before = snapshot(self.db)
                value, _ = await self.call(client, 'research_cycle_next', {'query': {**q, **delta}})
                self.check('public_' + label + '_refusal', value['status'] == 'INSUFFICIENT_CONTEXT' and snapshot(self.db) == before, value)
            for name, args in [('research_cycle_precommit', {'request': q, 'request_key': 'illegal', 'grant': True}),
                ('record_result', {'project': q['project'], 'kind': 'experiment', 'focus': 'fake', 'result': '{"measurement_binding":{}}'})]:
                before = snapshot(self.db)
                _, error = await self.call(client, name, args, True)
                self.check('model_cannot_' + name, error and snapshot(self.db) == before)
            previous, _ = await self.call(client, 'research_cycle_history', q)
            self.check('history_exposes_persisted_selection', len(previous['precommits']) == 2 and
                all(p['payload']['suffix_ordinals'] and 'loss_ledger' in p['preview']['normalization'] for p in previous['precommits']))
            self.check('history_explicit_phase_route', all('TYPED_VALIDATED' in r['stages'] and 'FEEDBACK_PROJECTED' in r['stages'] for r in previous['state_routes']))
            for world in self.worlds.values():
                if world['expected'] in ('ERROR', 'INCONCLUSIVE'):
                    view, _ = await self.call(client, 'research_cycle_history', {'project': world['project']})
                    self.check(world['key'] + ':no_false_measured_phase', all('EXTERNALLY_MEASURED' not in r['stages'] for r in view['state_routes']))
        # New process + new client: persisted receipts/projections, not Python memory.
        async with self.session(True) as client:
            restarted, _ = await self.call(client, 'research_cycle_history', {'project': self.worlds['A0']['project']})
            self.check('restart_authoritative_history', previous == restarted)
            for key in ('A0', 'A1', 'B0', 'B1', 'C0', 'C1'):
                value, _ = await self.call(client, 'research_cycle_next', {'query': {'project': self.worlds[key]['project'], 'known_fingerprints': [], 'latest_feedback': None}})
                self.check('restart_' + key + '_next', value['status'] == 'PROPOSAL_READY' and value['purpose'] == 'VALIDATE_TRANSFER')
        await self.context_fault_controls()
        counts = dict(Counter(r['receipt']['outcome'] for r in self.receipts))
        self.check('all_frozen_cycles', counts == self.policy['expected_cycles'], counts)
        self.check('MCP_call_budget', len(self.calls) <= self.policy['budgets']['MCP_calls_max'])
        shutil.copy2(self.workspace / 'engine017-isolation.json', self.out / 'isolation.json')
        shutil.copy2(self.workspace / 'native-I-T.jsonl', self.out / 'native-I-T.jsonl')
        return counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    base = args.baseline or Path(Path('/tmp/lm017_path').read_text().strip())
    out = args.output or Path(json.loads((base / 'metadata.json').read_text())['out'])
    runner = Acceptance017(base, out)
    write_json(base / 'current.json', {'output': str(out), 'private': str(runner.private), 'database': str(runner.db), 'legacy': str(runner.legacy)})
    try:
        counts = asyncio.run(runner.run())
        status = 'STAGING_PASS_REGRESSION_PENDING'
    except Exception as error:
        status, counts = 'STOP_WITH_RCA', dict(Counter(r['receipt']['outcome'] for r in runner.receipts))
        write_json(out / 'exception.json', {'error': str(error), 'traceback': __import__('traceback').format_exc()})
        if not (out / 'first-failure.json').exists():
            write_json(out / 'first-failure.json', {'error': str(error)})
    u = resource.getrusage(resource.RUSAGE_CHILDREN)
    write_json(out / 'result.json', {'status': status, 'MCP_tool_calls': len(runner.calls), 'sessions': runner.session_count,
        'complete_cycles': counts, 'proof_status': 'unverified', 'production_writes': False})
    write_json(out / 'costs.json', {'workers': runner.costs, 'protocol_and_driver_wall_ns': time.perf_counter_ns() - runner.started,
        'driver_CPU_ns': time.process_time_ns() - runner.cpu,
        'children_CPU_ns_through_exit': round((u.ru_utime + u.ru_stime - runner.child_start.ru_utime - runner.child_start.ru_stime) * 1e9),
        'largest_child_peak_RSS_KiB': u.ru_maxrss, 'speedup_claim': False})
    print(canonical({'status': status, 'output': str(out), 'cycles': counts, 'MCP_calls': len(runner.calls)}))
    if status == 'STOP_WITH_RCA':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
