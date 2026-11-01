"""Real019 TLS/OAuth external-source story, bounded and isolated from production."""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
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

from research_store import ResearchStore
from normalizer import canonical, digest
from qa_positive_acceptance import snapshot, write_json
from engine017_qa import Acceptance017, append
from deploy018_qa import Acceptance018
from deploy018_storage import migrate, backup, restore, inventory
from deploy018_storage_qa import probes
from deploy018_authority import install, reconcile
from typed_cycle011_store import install as install011
from engine017_store import install as install017
from beta019_seed import seed
from beta019_transport import serving, client
import beta019_source as source

SOURCE = Path(__file__).resolve().parent


class Acceptance019:
    def __init__(self, base: Path, out: Path, state: Path | None = None):
        self.base, self.out = base, out
        out.mkdir(parents=True, exist_ok=False)
        self.private = base / ('run-' + out.name)
        self.workspace = state.resolve() if state else self.private / 'workspace'
        self.seals = state.resolve().parent / 'seals' if state else self.private / 'seals'
        if state and not (self.workspace / '.beta019-state.json').exists():
            raise ValueError('019_INSTALLED_STATE_MARKER_REQUIRED')
        self.workspace.mkdir(parents=True, mode=0o700, exist_ok=bool(state)); self.seals.mkdir(mode=0o700, exist_ok=bool(state))
        self.legacy, self.db = self.workspace / 'research.sqlite3', self.workspace / 'beta.sqlite3'
        ResearchStore(self.legacy); ResearchStore(self.db)
        install011(self.db, self.legacy); install017(self.db)
        self.migrations = {'canonical': migrate(self.legacy), 'typed': migrate(self.db)}
        install(self.db)
        self.initial = snapshot(self.db)
        self.checks, self.calls, self.receipts, self.costs, self.security = [], [], [], [], []
        self.worlds = {}
        self.started, self.cpu = time.perf_counter_ns(), time.process_time_ns()
        self.child_start = resource.getrusage(resource.RUSAGE_CHILDREN)
        frozen = out / 'sources019'; frozen.mkdir()
        for p in SOURCE.glob('beta019*.py'):
            shutil.copy2(p, frozen / p.name)
        write_json(out / 'source-freeze.json', {'timestamp': datetime.now(timezone.utc).isoformat(),
            'native_definition_sha256': source.definition_sha(), 'registration': json.loads((SOURCE / 'external019/registration.json').read_text()),
            'code_hashes': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCE.glob('beta019*.py')},
            'unchanged_codebook': source.CODEBOOK, 'per_experiment_wall_limit_s': 120, 'worker_memory_bytes': 1073741824,
            'acceptance': 'Evidence/provenance and safe lifecycle; no advantage/discovery criterion; no outcome-dependent source changes.'})

    def check(self, name, ok, evidence=None):
        self.checks.append({'invariant': name, 'result': 'PASS' if ok else 'FAIL', 'evidence': evidence})
        write_json(self.out / 'checks.json', self.checks)
        if not ok:
            write_json(self.out / 'first-failure.json', self.checks[-1])
            raise AssertionError(name)

    async def call(self, connection, name, arguments, allow_error=False):
        return await Acceptance017.call(self, connection, name, arguments, allow_error)

    def command(self, module, payload, action=None, point=None):
        command = [sys.executable, str(SOURCE / module), '--db', str(self.db)]
        if action:
            command.append(action)
        env = {**os.environ}; env.pop('LM018_FAULT', None)
        if point:
            env['LM018_FAULT'] = point
        started = time.perf_counter_ns()
        from native_preview008_server import MeasuredProcess
        p = MeasuredProcess(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True)
        try:
            stdout, stderr = p.communicate(canonical(payload), timeout=120)
        except subprocess.TimeoutExpired:
            p.kill(); p.wait(); raise ValueError('019_EXPERIMENT_WALL_LIMIT')
        self.costs.append({'module': module, 'action': action, 'exit_code': p.returncode, 'wall_ns': time.perf_counter_ns() - started,
            'CPU_ns': round((p.child_usage.ru_utime + p.child_usage.ru_stime) * 1e9), 'peak_RSS_KiB': p.child_usage.ru_maxrss})
        try:
            value = json.loads(stdout)
        except ValueError:
            value = {'ok': False, 'error': stderr or stdout or 'Process interrupted before reply'}
        append(self.out / 'operator-executor.jsonl', {'module': module, 'action': action, 'move_id': payload.get('move_id'),
            'request_key': payload.get('request_key'), 'fault': point, 'exit_code': p.returncode, 'response': value})
        return value, p.returncode

    def owner(self, action, payload, point=None):
        return self.command('beta019_operator.py', payload, action, point)

    def execute(self, world, move_id, unreadable=False, key=None, point=None):
        return self.command('beta019_executor.py', {'project': world['project'], 'move_id': move_id,
            'environment_file': '/must-not-open' if unreadable else world['environment'],
            'private_key_file': '/must-not-open' if unreadable else key or world['private_key_file']}, point=point)

    async def prepared(self, connection, label):
        world = seed(self.db, self.workspace, self.seals, 0, self.out.name + ':' + label)
        pc, _ = await self.call(connection, 'research_cycle_precommit', {'request': {'project': world['project']}, 'request_key': label})
        result, code = self.owner('activate', {'project': world['project'], 'move_id': pc['move_id'], 'request_key': label})
        self.check(label + ':local_activation', code == 0 and result.get('ok'), result)
        return world, pc

    async def forge_controls(self, connection):
        """Append explicitly marked untrusted carriers, never alter real evidence."""
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from engine017_store import registered
        from typed_cycle011_store import connect, scope
        from deploy018_authority import lease_in
        from law_validation014_contract import Envelope014
        from engine017_measurement import outcome_of
        for control in ('invalid_signature', 'forged_native_result', 'artifact_hash', 'missing_artifact', 'foreign_source'):
            world, linked = await self.prepared(connection, control)
            with connect(self.db) as c:
                row = c.execute('SELECT * FROM typed011_precommits WHERE id=?', (linked['precommit_id'],)).fetchone()
                pc = json.loads(row['payload_json']); activation = c.execute('SELECT * FROM typed011_activations WHERE move_id=?', (linked['move_id'],)).fetchone()
                manifest, binding = registered(c, world['project']); accepted = scope(c, world['project']); lease = lease_in(c, world['project'], linked['move_id'])
            environment = json.loads(Path(world['environment']).read_text())
            attempt = source.calculate(environment['declaration'], environment['target_word'], pc['suffix_ordinals'], pc['observer'], 'exact')
            if control == 'forged_native_result':
                attempt['observed']['observation'] = 1 - attempt['observed']['observation']
            outcome = outcome_of(attempt, pc, 'exact')
            body = {'protocol': 'source-attempt019/v1', 'source_manifest_sha256': digest(manifest), 'precommit_sha256': row['digest'],
                'move_id': linked['move_id'], 'lease_sha256': digest(lease), 'environment': environment, 'attempt': attempt}
            if control == 'foreign_source':
                body['source_manifest_sha256'] = '0' * 64
            key_file = self.worlds[1]['private_key_file'] if control == 'invalid_signature' else world['private_key_file']
            key = Ed25519PrivateKey.from_private_bytes(Path(key_file).read_bytes())
            artifact = {'schema': 'signed-external019/v1', 'precommit_sha256': row['digest'], 'move_id': linked['move_id'],
                'observed': attempt['observed'], 'observed_coordinate': attempt['coordinate'], 'outcome': outcome,
                'source_receipt': body, 'signature': key.sign(canonical(body).encode()).hex(), 'proof_status': 'unverified'}
            path = Path(accepted['artifact_directory']) / 'deliberate-untrusted-carrier.json'
            if control != 'missing_artifact':
                path.write_text(canonical(artifact))
            artifact_sha = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else '0' * 64
            env = {k: pc[k] for k in ('project', 'proposal_fingerprint', 'obligation_id', 'obligation_version', 'scope', 'source_family_id',
                'source_bindings', 'native_definition_sha256', 'operation_definition_sha256', 'observer', 'test_id', 'suffix', 'suffix_ordinals',
                'purpose', 'law_fingerprint', 'context_word')}
            env.update(precommit_id=row['id'], precommit_sha256=row['digest'], move_id=linked['move_id'], audit_id=activation['audit_id'],
                activation_operation_id=activation['operation_id'], predictions=pc['alternatives'], observed=attempt['observed'],
                observed_coordinate=attempt['coordinate'], outcome=outcome, executor_id='qa.external.native011/v1',
                executor_code_sha256=accepted['executor_code_sha256'], artifact_sha256='0' * 64 if control == 'artifact_hash' else artifact_sha,
                summary='NEGATIVE CONTROL: intentionally untrusted carrier', reason='Owner QA forgery probe; never accepted as scientific evidence.')
            envelope = Envelope014.model_validate(env).model_dump()
            event = ResearchStore(self.db).record(world['project'], 'failed_check', 'NEGATIVE CONTROL:' + control,
                canonical({'claim_type': 'EXPERIMENT_RESULT', 'scope': pc['scope'], 'version': pc['obligation_version'], 'outcome': outcome,
                    'proof_status': 'unverified', 'measurement_binding': envelope, 'negative_control': control,
                    'observation': {'test_id': pc['test_id'], 'readout': attempt['observed'], 'scope': pc['scope'], 'version': pc['obligation_version'], 'observer': pc['observer']}}),
                'experiment', parent_id=world['root_id'], request_key='019:forged-carrier:' + control)
            with connect(self.db, True) as c:
                c.execute('INSERT INTO typed011_executions VALUES (?,?,?)', (linked['move_id'], event['id'], canonical({
                    'artifact_path': str(path), 'artifact_sha256': env['artifact_sha256'], 'envelope_sha256': digest(envelope)})))
                ResearchStore(self.db)._audit(c, 'beta019_deliberate_untrusted_carrier_control', {'move_id': linked['move_id'], 'event_id': event['id'], 'control': control})
            before = snapshot(self.db)
            rejected, _ = await self.call(connection, 'research_cycle_validate', {'project': world['project'], 'move_id': linked['move_id'], 'event_id': event['id']})
            expected = {'invalid_signature': '019_EXECUTOR_SIGNATURE_INVALID', 'forged_native_result': '019_NATIVE_MEASUREMENT_MISMATCH',
                'artifact_hash': 'ARTIFACT_DIGEST_MISMATCH', 'missing_artifact': 'No such file', 'foreign_source': '019_SOURCE_RECEIPT_REBIND'}[control]
            self.check('forgery:' + control, rejected['status'] == 'REJECTED' and expected in rejected['reason'] and snapshot(self.db) == before, rejected)
            reconcile(self.db, '019 owner retires deliberate forgery control; retain all untrusted carriers')

    async def authority_controls(self, connection):
        stale, pc = await self.prepared(connection, 'stale_version')
        current = ResearchStore(self.db).frontier.history(stale['obligation_id'])[-1]
        ResearchStore(self.db).frontier.update(stale['obligation_id'], current['version'], {'statement': current['statement'] + ' Next reviewed version.'})
        before = snapshot(self.db)
        denied, code = self.execute(stale, pc['move_id'], unreadable=True)
        self.check('stale_grant_denied_before_key_open', code != 0 and denied['error'] == 'STALE_OBLIGATION_VERSION' and snapshot(self.db) == before, denied)
        reconcile(self.db, '019 reviewed key rollover: retire all prior unfinished grants')
        rotated = seed(self.db, self.workspace, self.seals, 0, self.out.name + ':new_key')
        await self.cycle(connection, rotated, 0, old_key=stale['private_key_file'])

    async def crash_controls(self, connection):
        pending, completed = [], None
        for point in ('019_execution_prepared', '019_execution_after_event', '019_commit_transaction', '019_commit_after_commit'):
            world, pc = await self.prepared(connection, point)
            if point.startswith('019_execution'):
                result, code = self.execute(world, pc['move_id'], point=point)
            else:
                measured, code = self.execute(world, pc['move_id'])
                self.check(point + ':native_event_before_commit', code == 0 and measured.get('ok'))
                env = measured['result']['envelope']
                request = {'project': world['project'], 'move_id': pc['move_id'], 'event_id': measured['result']['event_id'], 'request_key': point,
                    **{k: env[k] for k in ('outcome', 'observed', 'summary', 'reason', 'proof_status')}}
                before = snapshot(self.db)
                result, code = self.owner('commit', request, point)
                if point == '019_commit_transaction':
                    self.check('SIGKILL_receipt_transaction_atomic', snapshot(self.db) == before)
                else:
                    completed = request
            self.check('SIGKILL:' + point, code == -9, result)
            pending.append({'project': world['project'], 'move_id': pc['move_id']})
        return pending, completed

    async def cycle(self, connection, world, step, old_key=None):
        started = time.perf_counter_ns()
        label = str(world['case']) + ':' + str(step)
        query = {'project': world['project']}
        preview, _ = await self.call(connection, 'research_cycle_next', {'query': query})
        self.check(label + ':source_proposal', preview['status'] == 'PROPOSAL_READY', preview)
        self.check(label + ':original_I_T_no_native_execution', not any(x['operation'] == 'E' for x in preview['native_trace']))
        self.check(label + ':purpose', preview['purpose'] == ('DISCRIMINATE' if step == 0 else 'VALIDATE_TRANSFER'))
        alias, _ = await self.call(connection, 'research_cycle_preview', {'request': {**query, 'display_label': 'Different display name'}})
        self.check(label + ':alias_not_novelty', preview['claim_fingerprint'] == alias['claim_fingerprint'])
        args = {'request': query, 'request_key': label}
        replies = await asyncio.gather(self.call(connection, 'research_cycle_precommit', args), self.call(connection, 'research_cycle_precommit', args))
        pc, repeated = replies[0][0], replies[1][0]
        self.check(label + ':concurrent_precommit_once', pc == repeated and not pc['execution_permission']['allowed'])
        denied, code = self.execute(world, pc['move_id'], unreadable=True)
        self.check(label + ':no_grant_no_key_read', code != 0 and denied['error'] == 'NO_TYPED_ACTIVATION', denied)
        for action in ('activate_experiment', 'complete'):
            before = snapshot(self.db)
            result, error = await self.call(connection, 'transition_research_move', {'project': world['project'], 'move_id': pc['move_id'],
                'action': action, 'reason': '019 unauthorized model authority test', 'request_key': 'denied:' + label + action}, True)
            self.check(label + ':model_denied:' + action, error and result.get('error', {}).get('code') == '018_OPERATOR_AUTHORITY_REQUIRED' and snapshot(self.db) == before, result)
        activation, code = self.owner('activate', {'project': world['project'], 'move_id': pc['move_id'], 'request_key': label})
        self.check(label + ':explicit_owner_activation', code == 0 and activation.get('ok'), activation)
        if old_key:
            before = snapshot(self.db)
            bad, code = self.execute(world, pc['move_id'], key=old_key)
            self.check('old_key_cannot_execute_new_scope', code != 0 and bad['error'] == 'EXECUTOR_SIGNING_KEY_MISMATCH' and snapshot(self.db) == before, bad)
        measured, code = self.execute(world, pc['move_id'])
        self.check(label + ':independent_native_execution', code == 0 and measured.get('ok'), measured)
        value = measured['result']; env = value['envelope']
        # Direct upstream public API is loaded only after the real signed event.
        wall, cpu = time.perf_counter_ns(), time.process_time_ns()
        environment = json.loads(Path(world['environment']).read_text())
        actual = source.native_trace(environment['target_word'] + env['suffix_ordinals'])[-1]
        observed = int(bool(set(actual) & set(source.OBJECT['final_states'])))
        direct = {'wall_ns': time.perf_counter_ns() - wall, 'CPU_ns': time.process_time_ns() - cpu,
            'source_configuration': actual, 'acceptance': observed, 'after_measurement_only': True,
            'counterfactual_only_for_withheld_or_error': world['mode'] != 'exact',
            'simple_baseline': 'For initial discrimination, blind lexicographic a also matches selected T; validation measured separately; no advantage claim',
            'LLM_only': 'NOT_RUN_NOT_USEFUL_FOR_DETERMINISTIC_FORMULA_REPLAY'}
        if world['mode'] == 'exact':
            self.check(label + ':direct_source_agreement', env['observed']['observation'] == observed and env['observed_coordinate'] == source.encode(actual))
        else:
            self.check(label + ':uncertainty_not_fabricated', not env['observed']['defined'] and env['observed']['observation'] is None and env['observed_coordinate'] == [])
        append(self.out / 'direct-source-baseline.jsonl', {'label': label, **direct})
        checked, _ = await self.call(connection, 'research_cycle_validate', {'project': world['project'], 'move_id': pc['move_id'], 'event_id': value['event_id']})
        self.check(label + ':typed_signed_validation', checked['status'] == 'VALID_BOUND_MEASUREMENT' and checked['signature_verified'] and checked['lease018_verified'], checked)
        request = {'project': world['project'], 'move_id': pc['move_id'], 'event_id': value['event_id'], 'request_key': label,
            **{k: env[k] for k in ('outcome', 'observed', 'summary', 'reason', 'proof_status')}}
        if step == 0 and world['case'] == 0:
            with sqlite3.connect(self.db) as c:
                c.execute("CREATE TRIGGER planned019_journal_fault BEFORE INSERT ON typed011_journal BEGIN SELECT RAISE(ABORT,'PLANNED019_JOURNAL_FAILURE'); END")
            before = snapshot(self.db)
            fail, code = self.owner('commit', request)
            self.check('journal_failure_atomic_rollback', code != 0 and 'PLANNED019_JOURNAL_FAILURE' in fail['error'] and snapshot(self.db) == before, fail)
            with sqlite3.connect(self.db) as c:
                c.execute('DROP TRIGGER planned019_journal_fault')
        result = await asyncio.gather(asyncio.to_thread(self.owner, 'commit', request), asyncio.to_thread(self.owner, 'commit', request))
        one, two = result[0][0], result[1][0]
        self.check(label + ':concurrent_commit_one_receipt', all(code == 0 and r.get('ok') for r, code in result)
            and one['result']['receipt_id'] == two['result']['receipt_id'] and one['result']['idempotent'] != two['result']['idempotent'], result)
        before = snapshot(self.db)
        conflict, code = self.owner('commit', {**request, 'outcome': 'ERROR' if env['outcome'] != 'ERROR' else 'SUCCESS'})
        self.check(label + ':request_key_cannot_replace_result', code != 0 and 'CONFLICT' in conflict['error'] and snapshot(self.db) == before)
        completed = one['result']
        self.check(label + ':completion_not_proof_or_grant', completed['status'] == 'COMPLETED' and completed['proof_status'] == 'unverified' and not completed['execution_permission']['allowed'])
        self.receipts.append({'project': world['project'], 'step': step, 'precommit': pc, 'receipt': completed, 'artifact': json.loads(Path(value['artifact_path']).read_text())})
        append(self.out / 'typed-receipts.jsonl', self.receipts[-1])
        next_state, _ = await self.call(connection, 'research_cycle_next', {'query': {**query, 'known_fingerprints': [], 'latest_feedback': None}})
        novelty, _ = await self.call(connection, 'research_novelty_snapshot', {'request': query})
        self.check(label + ':server_owned_feedback', novelty['feedback']['version'] == step + 1 and len(novelty['journal']) == step + 1)
        self.check(label + ':independent_branch_preserved', novelty['feedback']['applicability']['independent_branch_preserved'])
        if env['outcome'] in ('SUCCESS', 'FAILURE'):
            self.check(label + ':source_covered_next', next_state['status'] in ('PROPOSAL_READY', 'NO_INFORMATIVE_TEST', 'DOMAIN_EXHAUSTED_BOUNDED'), next_state)
        else:
            self.check(label + ':honest_wait', next_state['status'] == ('AWAITING_INCONCLUSIVE_EVIDENCE' if env['outcome'] == 'INCONCLUSIVE' else 'ERROR_REQUIRES_OPERATOR_REVIEW'))
        self.check(label + ':wall_bound', time.perf_counter_ns() - started < 120_000_000_000)
        return next_state

    async def run(self):
        for case in range(4):
            self.worlds[case] = seed(self.db, self.workspace, self.seals, case, self.out.name)
        write_json(self.out / 'source-registration.json', {'upstream': json.loads((SOURCE / 'external019/registration.json').read_text()),
            'sources': {k: {'manifest': w['manifest'], 'registration': w['registration'], 'obligation_id': w['obligation_id'], 'fixture_id': w['fixture_id']} for k, w in self.worlds.items()},
            'review_actor': 'task-authorized private QA operator', 'human_release_approval': 'NOT_GIVEN', 'remote_code_loading': False})
        forbidden = list(self.seals.iterdir())
        async with serving(self.workspace, self.db, self.out, 'default-off24', forbidden, enabled=False) as (origin, ctx, tokens, process):
            async with client(origin, ctx, tokens['access_token'], self.out / 'http-wire.jsonl') as connection:
                initialize = await connection.initialize(); tools = await connection.list_tools()
                self.check('default_off_24_tools', len(tools.tools) == 24 and not any(t.name == 'research_cycle_next' for t in tools.tools))
                write_json(self.out / 'legacy-tools.json', tools.model_dump(mode='json'))
        async with serving(self.workspace, self.db, self.out, 'beta019', forbidden) as (origin, ctx, tokens, process):
            async with client(origin, ctx, tokens['access_token'], self.out / 'http-wire.jsonl') as connection:
                initialized = await connection.initialize(); tools = await connection.list_tools()
                write_json(self.out / 'tools.json', {'initialize': initialized.model_dump(mode='json'), 'list': tools.model_dump(mode='json')})
                self.check('beta_27_tools_no_operator', len(tools.tools) == 27 and not {'activate', 'execute', 'commit', 'register_source'} & {t.name for t in tools.tools})
                await Acceptance018.auth_controls(self, origin, ctx, tokens['access_token'])
                contract, _ = await self.call(connection, 'research_contract', {})
                self.check('versioned_beta_contract', contract['http018']['version'] == '1.0.0b1' and contract['http018']['R5b'] == 'DEFERRED_BY_OWNER')
                for world in self.worlds.values():
                    await self.cycle(connection, world, 0)
                for case in (0, 1):
                    await self.cycle(connection, self.worlds[case], 1)
                await self.authority_controls(connection)
                await self.forge_controls(connection)
                for fields in ({'context_level': 'C4'}, {'version': 2}, {'source_id': 'foreign'}, {'observer': {'projection': 'primary', 'mod': 2}}):
                    before = snapshot(self.db)
                    value, _ = await self.call(connection, 'research_cycle_next', {'query': {'project': self.worlds[0]['project'], **fields}})
                    self.check('source_or_sufficiency_denial:' + str(fields), value['status'] == 'INSUFFICIENT_CONTEXT' and snapshot(self.db) == before, value)
                saved, _ = await self.call(connection, 'research_cycle_history', {'project': self.worlds[0]['project']})
                # Cross-project data cannot become grounds for an experiment.
                receipt = self.receipts[0]['receipt']
                before = snapshot(self.db)
                bad, _ = await self.call(connection, 'research_cycle_validate', {'project': self.worlds[1]['project'], 'move_id': receipt['move_id'], 'event_id': receipt['event_id']})
                self.check('foreign_project_event_rejected', bad['status'] == 'REJECTED' and bad['reason'] == 'MISSING_OR_FOREIGN_EVENT' and snapshot(self.db) == before, bad)
                interrupted, committed_before_crash = await self.crash_controls(connection)
        async with serving(self.workspace, self.db, self.out, 'restart-new-client', forbidden) as (origin, ctx, tokens, process):
            async with client(origin, ctx, tokens['access_token'], self.out / 'http-wire.jsonl') as connection:
                await connection.initialize(); await connection.list_tools()
                restored, _ = await self.call(connection, 'research_cycle_history', {'project': self.worlds[0]['project']})
                self.check('restart_durable_history', restored == saved)
                for move in interrupted:
                    state, _ = await self.call(connection, 'research_cycle_history', {'project': move['project']})
                    self.check('restart_no_orphan_grant:' + str(move['move_id']), all(not m['execution_permission']['allowed'] for m in state['moves']))
                repeated, code = self.owner('commit', committed_before_crash)
                self.check('committed_receipt_survives_SIGKILL_once', code == 0 and repeated['result']['idempotent'], repeated)
        after = snapshot(self.db)
        prefixes = {name: after['tables'][name][:len(rows)] == rows for name, rows in self.initial['tables'].items()}
        self.check('original_beta_rows_preserved', all(prefixes.values()), prefixes)
        state = inventory(self.db)
        self.check('sqlite_FK_hash_chain', state['chain']['hash_chain_ok'] and state['chain']['sqlite_integrity'] == 'ok' and not state['chain']['foreign_key_errors'], state['chain'])
        with ResearchStore(self.db)._connect() as c:
            moves = [dict(r) for r in c.execute('SELECT id,project FROM research_moves')]
        self.check('all_move_permissions_false', all(not ResearchStore(self.db).moves.inspect(m['project'], m['id'])['execution_permission']['allowed'] for m in moves))
        prepared = self.private / 'prepared-guard-probe.sqlite3'
        backup(self.db, prepared)
        with sqlite3.connect(prepared) as c:
            if not c.execute('SELECT 1 FROM transformation_contracts LIMIT 1').fetchone():
                c.execute('INSERT INTO transformation_contracts(project,payload_json,created_at) VALUES (?,?,?)',
                    ('LM_QA_019_SQL_PROBE', canonical({'purpose': 'Disposable guard coverage only; no mathematical contract or grant'}), 0))
        guarded = probes(prepared, self.private / 'guard-probe.sqlite3')
        self.check('all_guarded_tables_update_delete_rejected', guarded['all_exercised_pass'], len(guarded['records']))
        write_json(self.out / 'integrity.json', {'chain': state['chain'], 'prefixes': prefixes, 'guard_probes': guarded, 'new_verified': [e['id'] for e in after['tables']['events'] if e['status'] == 'verified']})
        counts = dict(Counter(r['receipt']['outcome'] for r in self.receipts))
        self.check('all_four_protocol_outcomes', set(counts) == {'SUCCESS', 'FAILURE', 'INCONCLUSIVE', 'ERROR'}, counts)
        return counts


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--base', type=Path, required=True); parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--state', type=Path)
    args = parser.parse_args(); args.base.mkdir(parents=True, mode=0o700, exist_ok=True)
    runner = Acceptance019(args.base, args.out, args.state)
    write_json(args.base / 'current019.json', {'output': str(args.out.resolve()), 'database': str(runner.db), 'legacy': str(runner.legacy), 'private': str(runner.private)})
    try:
        counts = asyncio.run(runner.run()); status = 'PASS_019_EXTERNAL_SOURCE_STAGING'
    except Exception as error:
        status, counts = 'STOP_WITH_RCA', dict(Counter(r['receipt']['outcome'] for r in runner.receipts))
        write_json(args.out / 'exception.json', {'error': str(error), 'traceback': traceback.format_exc()})
        if not (args.out / 'first-failure.json').exists():
            write_json(args.out / 'first-failure.json', {'error': str(error)})
    write_json(args.out / 'result.json', {'status': status, 'deployment': 'NOT_PERFORMED', 'complete_cycles': counts,
        'MCP_tool_calls': len(runner.calls), 'checks': len(runner.checks), 'proof_status': 'unverified', 'R5b': 'DEFERRED_BY_OWNER',
        'scientific_result': 'SOURCE_FORMULA_REPLAY; NO_STRUCTURAL_ADVANTAGE; NOT_AUTONOMOUS_DISCOVERY'})
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    write_json(args.out / 'costs.json', {'workers': runner.costs, 'driver_wall_ns': time.perf_counter_ns() - runner.started,
        'driver_CPU_ns': time.process_time_ns() - runner.cpu, 'children_CPU_ns': round((children.ru_utime + children.ru_stime - runner.child_start.ru_utime - runner.child_start.ru_stime) * 1e9),
        'largest_child_peak_RSS_KiB': children.ru_maxrss, 'external_inference': 'NOT_USED'})
    print(canonical({'status': status, 'output': str(args.out), 'cycles': counts, 'calls': len(runner.calls)}))
    if status == 'STOP_WITH_RCA':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
