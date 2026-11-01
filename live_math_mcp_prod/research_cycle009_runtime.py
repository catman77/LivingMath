"""Synthetic-only lifecycle orchestration. No changes to deployed code or original source rows."""
import asyncio
import copy
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import sys
import time

from mcp import ClientSession
from normalizer import digest, read_history
from native_preview008_qa import readonly_state
from native_preview008_server import PreviewBoundary, MeasuredProcess
from live_constructive007_native import native_fingerprint
from qa_positive_acceptance import snapshot, write_json
from research_store import ResearchStore
from research_cycle009 import (MECHANISM, event_rows, requests, source_spec, law_payload, material,
    selected_claim, survivors, validate_witness, validate_executable_readout, validate_completion, operation, proposal, qa_closure_changes)
from research_cycle009_transport import measured_stdio


def append(path, value):
    with path.open('a') as out:
        out.write(json.dumps(value, ensure_ascii=False) + '\n')


class Cycle:
    def __init__(self, base: Path, database: Path, canonical: Path):
        if database.resolve() == canonical.resolve() or not database.is_relative_to(base):
            raise ValueError('Lifecycle requires an explicit private QA database')
        self.base, self.db = base, database
        self.checks, self.calls, self.costs, self.ledger, self.equivalence = [], [], [], [], []
        self.moves = []
        self.invariants = {}
        self.seen_fingerprints = {}
        self.seen_request_shapes = set()

    def check(self, name, ok, actual=None):
        row = {'invariant': name, 'result': 'PASS' if ok else 'FAIL', 'actual': actual}
        self.checks.append(row); write_json(self.base / 'checks.json', self.checks)
        if not ok:
            write_json(self.base / 'first-failure.json', {'classification': 'CYCLE_INVARIANT', **row})
            raise AssertionError(name)

    async def call(self, name, arguments, allow_error=False):
        before = readonly_state(self.db)
        started, cpu = time.perf_counter_ns(), time.process_time_ns()
        response = await self.client.call_tool(name, arguments)
        wall, cpu_ns = time.perf_counter_ns() - started, time.process_time_ns() - cpu
        raw = response.model_dump(mode='json')
        row = {'index': len(self.calls) + 1, 'tool': name, 'arguments': arguments, 'response': raw,
               'MCP_roundtrip_wall_ns': wall, 'client_CPU_ns': cpu_ns}
        self.calls.append(row); append(self.base / 'calls.jsonl', row)
        readonly = name.endswith('_preview') or name in {'research_move_history', 'research_frontier', 'service_health'} or response.isError
        if readonly:
            after = readonly_state(self.db)
            append(self.base / 'readonly.jsonl', {'call': row['index'], 'before': before, 'after': after, 'equal': before == after})
            self.check('call:' + str(row['index']) + ':readonly', before == after)
        if response.isError:
            if not allow_error:
                raise RuntimeError(name + ': ' + ''.join(c.text for c in response.content if c.type == 'text'))
            return None
        value = response.structuredContent or json.loads(response.content[0].text)
        if name.endswith('_preview'):
            self.check('call:' + str(row['index']) + ':no_preview_grant', value.get('execution_permission') == {'allowed': False}
                       and value.get('proof_status') == 'unverified')
        return value

    async def event(self, world, label, data, kind='hypothesis', status='hypothesis', parent=None):
        args = {'project': world['project'], 'kind': kind, 'focus': label, 'result': json.dumps(data, sort_keys=True),
                'status': status, 'request_key': world['project'] + ':' + label}
        if parent is not None:
            args['parent_id'] = parent
        result = await self.call('record_result', args)
        return event_rows(self.db, world['project'])[result['id']]

    async def seed_projection(self, world, binding, active, version, previous=None, failures=None, label_prefix=''):
        histories = {}
        for name, word in world['histories'].items():
            data = {'claim_type': 'SOURCE_CLAIM', 'statement': 'Operator declared finite history, not actual hidden environment.',
                    'word': word, 'scope': world['scope'], 'version': version, 'representation': 'native_007/v1'}
            if previous:
                data['relations'] = [{'type': 'derived_from', 'target_ref': 'event:' + str(previous['histories'][name])}]
            row = await self.event(world, f'{label_prefix}v{version}-{name}', data,
                                   parent=previous['histories'][name] if previous else binding['fixture_id'])
            histories[name] = row['id']
        independent = await self.event(world, f'{label_prefix}v{version}-IND', {'claim_type': 'HYPOTHESIS',
            'statement': 'Independent branch, unchanged finite observation; version projection is not a new measurement.',
            'word': [], 'scope': 'independent', 'version': version, 'representation': 'native_007/v1',
            'relations': [{'type': 'derived_from', 'target_ref': 'event:' + str(previous['independent_id'])}] if previous else []},
            parent=previous['independent_id'] if previous else binding['fixture_id'])
        spec = source_spec(world, histories, independent['id'], active, version, failures or [])
        root = await self.event(world, f'{label_prefix}v{version}-source', {'claim_type': 'SOURCE_CLAIM',
            'statement': 'Registered native operations/D. Applicability projection retains original sources and negative evidence.',
            'source_spec': spec, 'scope': world['scope'], 'version': version, 'representation': 'native_007/v1',
            'relations': [{'type': 'derived_from', 'target_ref': 'event:' + str(previous['root_id'])}] if previous else []},
            parent=previous['root_id'] if previous else binding['fixture_id'])
        law = await self.event(world, f'{label_prefix}v{version}-law', law_payload(world, root, version), parent=root['id'])
        return {**binding, 'histories': histories, 'independent_id': independent['id'], 'root_id': root['id'],
                'law_id': law['id'], 'version': version, 'active': active}

    async def seed(self, world, environment_hash):
        self.check(world['id'] + ':unique_namespace', not event_rows(self.db, world['project']))
        fixture = await self.event(world, 'fixture', {'claim_type': 'SOURCE_CLAIM', 'statement': 'Operator-supplied sealed finite QA fixture.',
            'fixture_sha256': world['fixture_sha256'], 'environment_commitment': environment_hash,
            'scope': world['scope'], 'representation': 'fixture009:' + world['fixture_sha256'],
            'public_source_parameters': world['parameters'], 'version': 1}, kind='qa_source', status='observation')
        binding = await self.seed_projection(world, {'fixture_id': fixture['id']}, list(world['histories']), 1)
        representation = 'fixture009:' + world['fixture_sha256']
        blueprint = {'project': world['project'], 'import_key': world['project'] + ':scoped-operator-constraint',
            'sources': [{'id': fixture['id'], 'sha256': digest(fixture)}],
            'obligations': [{'key': 'cycle', 'statement': 'Two bounded readouts of only fixture ' + world['fixture_sha256'],
                'scope': world['scope'], 'source_event_ids': [fixture['id']], 'evidence_refs': ['event:' + str(fixture['id'])]}],
            'constraints': [{'kind': 'allowed_experiment', 'obligation_key': 'cycle', 'mechanisms': [MECHANISM],
                'source_event_ids': [fixture['id']], 'source_representations': [representation], 'scope': world['scope'],
                'reason': 'User-authorized isolated QA fixture only; no global experimental permission.',
                'reopen_conditions': ['New fixture, scope, mechanism or observer requires independent review.']}]}
        result = ResearchStore(self.db).frontier.import_history(blueprint, 'User-authorized frozen009 QA operator')
        append(self.base / 'operator-ledger.jsonl', {'operation': 'scoped_constraint', 'world': world['id'], 'blueprint': blueprint, 'result': result})
        binding['obligation_id'] = result['obligation_ids']['cycle']
        return binding

    async def preview(self, world, binding, stage, feedback_id=None, oracle=None, active=None):
        from research_cycle009_oracle import rank
        from live_constructive007_oracle import run as raw_run
        history = read_history(self.db, world['project'])
        folder = self.base / 'source-snapshots'; folder.mkdir(exist_ok=True)
        write_json(folder / (stage + '.json'), history)
        append(self.base / 'source-receipts.jsonl', {'stage': stage, 'project': world['project'],
            'version': binding['version'], 'root_event_id': binding['root_id'],
            'snapshot_sha256': digest(history), 'event_hashes': {str(e['id']): digest(e) for e in history['tables']['events']}})
        normal, native = requests(self.db, world, binding, feedback_id)
        known = sorted(self.seen_fingerprints.get(world['project'], set()))
        if len(known) > 16:
            raise ValueError('BOUNDED_NOVELTY_REGISTRY_FULL')
        native['question']['known_fingerprints'] = known
        normalized = await self.call('research_normalize_preview', normal)
        off_normal = PreviewBoundary(self.db).run('normalize', normal)
        self.check(stage + ':normalization_complete', normalized['status'] == 'COMPLETE' and normalized['audit_sufficient'])
        self.check(stage + ':offline_normalization_exact', material(normalized) == material(off_normal))
        results = {}
        for mode in ('bounded', 'constructive'):
            request = copy.deepcopy(native); request['question']['mode'] = mode
            out = await self.call('research_native_preview', request)
            results[mode] = out
            self.check(stage + ':' + mode + ':native_response', out['status'] not in {'INSUFFICIENT_CONTEXT', 'RESOURCE_LIMIT', 'FAIL_CLOSED'})
            validate_witness(world, binding, out, raw_run)
            self.check(stage + ':' + mode + ':OS_exit_cost', out['child_usage_status'] == 'OS_WAIT4_THROUGH_EXIT'
                       and out['child_cpu_ns'] >= out['worker_total_cpu_ns'] > 0)
            self.costs.append({'world': world['id'], 'stage': stage, 'version': binding['version'], 'mode': mode,
                'MCP_roundtrip_wall_ns': self.calls[-1]['MCP_roundtrip_wall_ns'], 'client_CPU_ns': self.calls[-1]['client_CPU_ns'],
                **{k: out[k] for k in ('cold_wall_ns', 'child_cpu_ns', 'child_peak_rss_KiB', 'parent_cpu_ns',
                    'source_serialization', 'source_snapshot_wall_ns', 'primitive_calls', 'cost_ledger')},
                'attention_test': out['attention'].get('test_id'), 'I_witness': out.get('witness')})
            append(self.base / 'costs.jsonl', self.costs[-1])
        offline = PreviewBoundary(self.db).run('native', native)
        self.check(stage + ':offline_native_exact', material(results['constructive']) == material(offline))
        self.check(stage + ':same_pre_snapshot_novelty_for_B1_C',
                   results['bounded']['status'] == results['constructive']['status'])
        discovered = results['constructive']['interpretation'].get('fingerprint')
        if results['constructive']['status'] == 'NEW_DISTINCTION':
            self.check(stage + ':no_repeated_NEW_for_seen_fingerprint', discovered not in known)
            self.seen_fingerprints.setdefault(world['project'], set()).add(discovered)
        # Byte-identical declared operations/ordinal histories across versions are
        # a repeated request shape, not a new mathematical discovery/equivalence.
        parameters = copy.deepcopy(world['parameters']); actions = parameters['actions']
        ordinal = lambda word: [actions.index(a) for a in word]
        parameters['actions'] = list(range(len(actions)))
        shape = digest({'project': world['project'], 'scope': world['scope'], 'parameters': parameters,
            'native_definition_sha256': native_fingerprint(),
            'histories': sorted(ordinal(world['histories'][n]) for n in binding['active'][:2]),
            'observer': world['observer'], 'D': [ordinal(t['suffix']) for t in world['tests']]})
        append(self.base / 'novelty-ledger.jsonl', {'stage': stage, 'project': world['project'], 'version': binding['version'],
            'known_before': known, 'returned_fingerprint': discovered, 'status': results['constructive']['status'],
            'same_declared_request_shape_seen': shape in self.seen_request_shapes, 'request_shape_sha256': shape,
            'new_mathematical_discovery_claimed': False, 'known_registry_update_after_paired_comparison': True})
        self.seen_request_shapes.add(shape)
        self.equivalence.append({'world': world['id'], 'stage': stage, 'normalization': 'EXACT',
            'witness_readouts_provenance_guard_T': 'EXACT', 'timing_fields_excluded_only': True})
        append(self.base / 'offline-vs-MCP.jsonl', self.equivalence[-1])
        attention = results['constructive']['attention']
        self.check(stage + ':T_independent_of_I', material(attention['ranking']) == material(results['bounded']['attention']['ranking'])
                   if 'ranking' in attention else attention['status'] == results['bounded']['attention']['status'])
        expected = rank(world, active if active is not None else binding['active'])
        self.check(stage + ':independent_raw_T', attention['status'] == expected['status'] and attention.get('test_id') == expected['test_id'])
        if expected['ranking']:
            keys = list(expected['ranking'][0])
            self.check(stage + ':exact_rational_ranking', [{k: r[k] for k in keys} for r in attention['ranking']] == expected['ranking'])
        self.check(stage + ':independent_retained', next(h for h in attention['hypotheses'] if h['id'] == 'IND')['status'] == 'ACTIVE')
        write_json(self.base / (stage + '-preview.json'), {'normalization': normalized, 'native': results['constructive']})
        return results['constructive']

    async def propose(self, world, binding, name, op, adverse=()):
        move = proposal(world, binding, op, adverse)
        request = {'project': world['project'], 'move': move, 'request_key': world['project'] + ':propose:' + name}
        record = await self.call('record_research_move', request)
        self.moves.append((world['project'], record['id']))
        self.check(name + ':record_not_grant', record['execution_permission']['allowed'] is False)
        return record, move

    async def audit_activate(self, world, binding, name, record):
        audit = await self.call('audit_research_move', {'project': world['project'], 'move_id': record['id'],
                                                      'request_key': world['project'] + ':audit:' + name})
        self.check(name + ':audit_not_grant', not audit['execution_permission']['allowed'] and audit['status'] == 'AUDITED', audit['audit'])
        activated = await self.call('transition_research_move', {'project': world['project'], 'move_id': record['id'],
            'action': 'activate_experiment', 'request_key': world['project'] + ':activate:' + name})
        self.check(name + ':explicit_scoped_grant', activated['execution_permission']['allowed'] and
                   activated['execution_permission']['scope'] == world['scope'] and
                   activated['execution_permission']['frontier_versions'] == {str(binding['obligation_id']): binding['version']})
        return activated

    def operator_review(self, world, binding, move, adverse, name):
        for event_id in adverse:
            result = ResearchStore(self.db).evidence_reviews.record(world['project'], event_id, binding['obligation_id'],
                binding['version'], move['proposed_operation'], 'diagnostic_subject',
                'Frozen QA operator policy: the actual failed guard is the diagnostic subject; the next experiment uses surviving candidates only, not the false premise.',
                ['event:' + str(event_id), 'event:' + str(binding['fixture_id'])],
                world['project'] + ':review:' + name + ':' + str(event_id), 'Explicit user-authorized isolated QA operator')
            append(self.base / 'operator-ledger.jsonl', {'operation': 'scoped_adverse_disposition', 'world': world['id'], 'result': result})

    async def measure(self, world, binding, grant, test, name):
        current = await self.call('research_move_history', {'project': world['project'], 'move_id': grant['id']})
        self.check(name + ':current_grant_before_external_execution', current['execution_permission']['allowed'])
        environment = self.base / 'sealed-environments' / (world['id'] + '.json')
        request = {'world_file': str(self.base / 'world-inputs' / (world['id'] + '.json')),
            'environment_file': str(environment), 'environment_sha256': hashlib.sha256(environment.read_bytes()).hexdigest(),
            'database': str(self.db), 'move_id': grant['id'], 'test_id': test['test_id'], 'version': binding['version']}
        started = time.perf_counter_ns()
        process = MeasuredProcess([sys.executable, str(Path(__file__).with_name('research_cycle009_measure.py'))],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            stdout, stderr = process.communicate(json.dumps(request).encode(), timeout=5)
        except subprocess.TimeoutExpired:
            process.kill(); process.communicate(); raise
        if process.returncode != 0:
            (self.base / (name + '-measurement-stderr.txt')).write_bytes(stderr)
            raise RuntimeError('External measurement failed: ' + name)
        value = json.loads(stdout)
        usage = process.child_usage
        receipt = {'world': world['id'], 'name': name, 'result': value, 'wall_ns': time.perf_counter_ns() - started,
            'child_CPU_ns_through_exit': round((usage.ru_utime + usage.ru_stime) * 1e9), 'peak_rss_KiB': usage.ru_maxrss,
            'request': request, 'cost_trace_not_sent_to_I_T': True}
        append(self.base / 'external-measurements.jsonl', receipt)
        return value

    async def finish(self, world, binding, grant, measurement, claim, name, force_outcome=None):
        outcome = force_outcome or ('SUCCESS' if measurement['readout'] == claim['readout'] else 'FAILURE')
        observation = {k: measurement[k] for k in ('test_id', 'readout', 'scope', 'version', 'observer')}
        data = {'claim_type': 'EXPERIMENT_RESULT', 'statement': 'Finite measured readout; no mathematical truth is established.',
            'fixture_sha256': world['fixture_sha256'], 'measurement_origin': 'external_bounded_native_executor',
            'scope': world['scope'], 'version': binding['version'], 'test_id': measurement['test_id'],
            'observation': observation, 'outcome': outcome, 'proof_status': 'unverified'}
        event = await self.event(world, name + '-measurement', data,
            kind='experiment' if outcome == 'INCONCLUSIVE' else 'counterexample', status='experiment', parent=binding['root_id'])
        result = {'outcome': outcome, 'summary': 'Actual finite readout of ' + measurement['test_id'] + '; candidate consistency only.',
                  'data': {'readout': measurement['readout'], 'fixture_sha256': world['fixture_sha256'], 'measurement_event_id': event['id']}}
        validate_completion(event, world, binding, measurement['test_id'], result)
        request = {'project': world['project'], 'move_id': grant['id'], 'action': 'complete',
            'request_key': world['project'] + ':complete:' + name, 'reason': 'External bounded result event exists and matches this scoped experiment.',
            'evidence_refs': ['event:' + str(event['id'])], 'result': result}
        complete = await self.call('transition_research_move', request)
        self.check(name + ':completed_no_grant_no_verified', complete['status'] == 'COMPLETED' and
                   not complete['execution_permission']['allowed'] and complete['proof_status'] == 'unverified')
        old_state = readonly_state(self.db)
        repeated = await self.call('transition_research_move', request)
        self.check(name + ':complete_idempotent', repeated['idempotent'] and readonly_state(self.db) == old_state)
        changed = copy.deepcopy(request); changed['result']['data']['readout'] = {'changed': True}
        denied = await self.call('transition_research_move', changed, allow_error=True)
        self.check(name + ':result_cannot_be_replaced', denied is None)
        denied = await self.call('transition_research_move', {'project': world['project'], 'move_id': grant['id'],
            'action': 'activate_experiment', 'request_key': world['project'] + ':terminal-retry:' + name}, allow_error=True)
        self.check(name + ':terminal_not_reactivated', denied is None)
        return event, complete

    async def run_world(self, world, oracle):
        from research_cycle009_oracle import signatures
        folder = self.base / 'sessions' / world['id']
        async with measured_stdio(self.db, folder) as (read, write):
            async with ClientSession(read, write) as client:
                self.client = client
                await client.initialize()
                listing = (await client.list_tools()).model_dump(mode='json'); write_json(folder / 'tools-list.json', listing)
                self.check(world['id'] + ':staging20', len(listing['tools']) == 20)
                env = self.base / 'sealed-environments' / (world['id'] + '.json')
                binding = await self.seed(world, hashlib.sha256(env.read_bytes()).hexdigest())
                original = event_rows(self.db, world['project'])
                first = await self.preview(world, binding, world['id'] + '-step1-before')
                test, claim = selected_claim(first['attention']); validate_executable_readout(world, test, first['attention'])
                canary_op = operation(world, test['test_id'], claim['readout'], purpose='unexecuted stale-permission canary')
                canary, _ = await self.propose(world, binding, world['id'] + '-canary', canary_op)
                canary = await self.audit_activate(world, binding, world['id'] + '-canary', canary)
                record, move = await self.propose(world, binding, world['id'] + '-step1', operation(world, test['test_id'], claim['readout']))
                grant = await self.audit_activate(world, binding, world['id'] + '-step1', record)
                measured = await self.measure(world, binding, grant, test, world['id'] + '-step1')
                event, completed = await self.finish(world, binding, grant, measured, claim, world['id'] + '-step1')
                self.check(world['id'] + ':first_negative', completed['completion']['result']['outcome'] == 'FAILURE')
                active = survivors(first['attention'], measured['readout'])
                self.check(world['id'] + ':first_guard_only', len(active) == 2)
                after = await self.preview(world, {**binding, 'active': active}, world['id'] + '-step1-after', event['id'], active=active)
                self.check(world['id'] + ':T_action_changed_after_negative', after['attention']['test_id'] != first['attention']['test_id'])
                rows = {h['id']: h['status'] for h in after['attention']['hypotheses']}
                removed = set(binding['active']) - set(active)
                self.check(world['id'] + ':dependent_guard_excluded_independent_retained', all(rows['D' + h[1:]] == 'EXCLUDED_DEPENDENCY' for h in removed)
                           and rows['IND'] == 'ACTIVE')
                self.ledger.append({'world': world['id'], 'cycle_index': 1, 'source_snapshot': digest(read_history(self.db, world['project'])),
                    'version': 1, 'root_event_id': binding['root_id'], 'I': first['witness'], 'T': first['attention']['test_id'],
                    'move_id': grant['id'], 'measurement_event_id': event['id'], 'outcome': 'FAILURE',
                    'readout': measured['readout'], 'active_before': binding['active'], 'active_after': active,
                    'next_T': after['attention']['test_id'], 'current_grant': completed['execution_permission'],
                    'unexecuted_canary_grant': {'move_id': canary['id'], 'permission': canary['execution_permission']},
                    'operator_inputs': ['fixture', 'reviewed source law', 'narrow initial allowance'], 'algorithm_outputs': ['I witness', 'T rank', 'finite applicability']})
                append(self.base / 'cycle-ledger.jsonl', self.ledger[-1])
                previous = binding
                failures = [{'event_ref': 'event:' + str(event['id']), 'excluded_guard_ids': sorted(removed),
                             'scope': world['scope'], 'not_universal_refutation': True}]
                binding = await self.seed_projection(world, binding, active, 2, previous, failures)
                projected = {**json.loads(event['content'])['observation'], 'version': 2}
                receipt = await self.event(world, 'v2-scoped-negative-projection', {'claim_type': 'COUNTEREXAMPLE',
                    'statement': 'Same earlier measurement re-scoped to v2; not another external observation.',
                    'observation': projected, 'scope': world['scope'], 'version': 2,
                    'relations': [{'type': 'derived_from', 'target_ref': 'event:' + str(event['id'])}]},
                    kind='counterexample', status='experiment', parent=event['id'])
                await self.call('research_obligation_update', {'project': world['project'], 'obligation_id': binding['obligation_id'],
                    'expected_version': 1, 'changes': {'status': 'TESTING', 'source_event_ids': [binding['fixture_id'], binding['root_id'], event['id']],
                        'evidence_refs': ['event:' + str(event['id'])], 'statement': 'Continue only surviving finite guards after negative measurement; no theorem claim.'}})
                stale = await self.call('research_move_history', {'project': world['project'], 'move_id': canary['id']})
                self.check(world['id'] + ':stale_permission_revoked', not stale['execution_permission']['allowed']
                           and stale['execution_permission']['needs_reaudit'] and stale['status'] == 'REQUIRES_REVIEW')
                append(self.base / 'permission-invalidation.jsonl', {'world': world['id'], 'move_id': canary['id'],
                    'before': canary, 'after': stale, 'cause': 'evidence-bearing obligation version1->2'})
                denied = await self.call('transition_research_move', {'project': world['project'], 'move_id': canary['id'],
                    'action': 'activate_experiment', 'request_key': world['project'] + ':stale-canary-reactivate'}, allow_error=True)
                self.check(world['id'] + ':stale_requires_reaudit', denied is None)
                await self.call('transition_research_move', {'project': world['project'], 'move_id': canary['id'], 'action': 'abandon',
                    'request_key': world['project'] + ':canary-cleanup', 'reason': 'Unexecuted old permission invalidated by the evidence-bearing version change.'})
                second = await self.preview(world, binding, world['id'] + '-step2-before', receipt['id'])
                self.check(world['id'] + ':version_projection_preserves_T', second['attention']['test_id'] == after['attention']['test_id'])
                test2, claim2 = selected_claim(second['attention']); validate_executable_readout(world, test2, second['attention'])
                record2, move2 = await self.propose(world, binding, world['id'] + '-step2', operation(world, test2['test_id'], claim2['readout']),
                                                   adverse=[event['id'], receipt['id']])
                self.check(world['id'] + ':adverse_requires_scoped_review', record2['status'] == 'REQUIRES_REVIEW' and
                           'ADVERSE_EVIDENCE_REQUIRES_REVIEW' in record2['audit']['warnings'])
                denied = await self.call('transition_research_move', {'project': world['project'], 'move_id': record2['id'],
                    'action': 'activate_experiment', 'request_key': world['project'] + ':unreviewed-step2'}, allow_error=True)
                self.check(world['id'] + ':diagnostic_label_alone_no_grant', denied is None)
                self.operator_review(world, binding, move2, [event['id'], receipt['id']], 'step2')
                grant2 = await self.audit_activate(world, binding, world['id'] + '-step2', record2)
                measured2 = await self.measure(world, binding, grant2, test2, world['id'] + '-step2')
                event2, complete2 = await self.finish(world, binding, grant2, measured2, claim2, world['id'] + '-step2')
                final_active = survivors(second['attention'], measured2['readout'])
                final = await self.preview(world, binding, world['id'] + '-step2-after', event2['id'], active=final_active)
                self.check(world['id'] + ':second_complete_final_partition', len(final_active) == 1 and final['attention']['status'] == 'NO_INFORMATIVE_TEST')
                self.check(world['id'] + ':frozen_two_step_oracle', [test['test_id'], test2['test_id']] ==
                           [o['attention']['test_id'] for o in oracle['steps']] and measured['readout'] == oracle['steps'][0]['measurement']
                           and measured2['readout'] == oracle['steps'][1]['measurement'])
                self.check(world['id'] + ':original_sources_unchanged', all(event_rows(self.db, world['project'])[i] == r for i, r in original.items()))
                self.ledger.append({'world': world['id'], 'cycle_index': 2, 'version': 2, 'root_event_id': binding['root_id'],
                    'I': second['witness'], 'T': second['attention']['test_id'], 'move_id': grant2['id'],
                    'measurement_event_id': event2['id'], 'outcome': complete2['completion']['result']['outcome'],
                    'readout': measured2['readout'], 'active_before': active, 'active_after': final_active,
                    'next_T': final['attention'].get('test_id'), 'current_grant': complete2['execution_permission'],
                    'operator_inputs': ['current scoped adverse disposition'], 'algorithm_outputs': ['I witness', 'T rank', 'finite applicability'],
                    'source_snapshot': digest(read_history(self.db, world['project']))})
                append(self.base / 'cycle-ledger.jsonl', self.ledger[-1])
                self.invariants[world['id']] = {'binding': binding, 'last_event': event2['id'], 'first': first, 'second': second, 'world': world}
                await self.negative_controls(world, binding, second, event, event2, grant2, measured2, claim2)
        self.check(world['id'] + ':MCP_process_exit_receipt', json.loads((folder / 'server-exit-usage.json').read_text())['CPU_ns_inclusive_descendants'] > 0)
        print(json.dumps({'world': world['id'], 'completed_steps': 2, 'T_changed': True, 'status': 'PASS'}), flush=True)

    async def negative_controls(self, world, binding, second, first_event, final_event, completed_grant, measured, claim):
        """Expected denials, kept separate from genuine failed acceptance cohorts."""
        from live_constructive007_oracle import run as raw_run
        normal, native = requests(self.db, world, binding, final_event['id'])
        cases = {}
        for label in ('foreign_project', 'source_hash', 'stale_version', 'observer', 'C4', 'quota', 'malicious'):
            req = copy.deepcopy(native)
            if label == 'foreign_project': req['project'] = 'FOREIGN_CYCLE009'
            if label == 'source_hash': req['source_bindings'][0]['sha256'] = '0' * 64
            if label == 'stale_version': req['active_frontier_version'] = 1
            if label == 'observer': req['observer']['mod'] = 2
            if label == 'C4': req['question']['context_level'] = 'C4'
            if label == 'quota': req['budget']['native_calls'] = 1
            if label == 'malicious': req['question']['verified'] = True
            cases[label] = req
        for label, req in cases.items():
            out = await self.call('research_native_preview', req, allow_error=label == 'malicious')
            expected = out is None if label == 'malicious' else out['status'] == ('UNKNOWN_BOUNDED' if label == 'quota' else 'INSUFFICIENT_CONTEXT')
            self.check(world['id'] + ':negative:' + label, expected, out.get('reason') if out else None)
        other_project = world['project'] + '_other'
        foreign = await self.call('record_result', {'project': other_project, 'kind': 'hypothesis',
            'focus': 'Existing foreign QA source', 'result': 'Project-local source isolation control only.', 'status': 'hypothesis',
            'request_key': other_project + ':source'})
        foreign_row = event_rows(self.db, other_project)[foreign['id']]
        wrong_source = copy.deepcopy(native)
        wrong_source['source_event_ids'].append(foreign['id'])
        wrong_source['source_bindings'].append({'event_id': foreign['id'], 'sha256': digest(foreign_row)})
        out = await self.call('research_native_preview', wrong_source)
        self.check(world['id'] + ':existing_foreign_QA_source_denied', out['status'] == 'INSUFFICIENT_CONTEXT')
        foreign_move = proposal(world, binding, operation(world, 't0', {'control': 'foreign source'}, 'source isolation'))
        foreign_move['parent_event_ids'].append(foreign['id'])
        denied = await self.call('record_research_move', {'project': world['project'], 'move': foreign_move,
            'request_key': world['project'] + ':foreign-source-move'}, allow_error=True)
        self.check(world['id'] + ':foreign_lifecycle_source_denied', denied is None)
        bad = copy.deepcopy(second); bad['witness']['readouts'][0]['observation'] = 'INTENTIONAL_CORRUPT_WITNESS'
        try:
            validate_witness(world, binding, bad, raw_run)
        except ValueError as error:
            mismatch_denied = str(error) == 'RETURNED_WITNESS_NATIVE_MISMATCH'
        else:
            mismatch_denied = False
        self.check(world['id'] + ':mismatch_returned_witness_rejected', mismatch_denied)
        valid_result = {'outcome': json.loads(final_event['content'])['outcome'], 'data': {'readout': measured['readout']}}
        state = readonly_state(self.db)
        for label, row in [('premise_only', event_rows(self.db, world['project'])[binding['fixture_id']]),
                           ('foreign', {**final_event, 'project': 'FOREIGN_CYCLE009'})]:
            try:
                validate_completion(row, world, binding, measured['test_id'], valid_result)
            except ValueError:
                rejected = True
            else:
                rejected = False
            self.check(world['id'] + ':completion_evidence:' + label, rejected and readonly_state(self.db) == state)
        wrong_scope = {**world, 'scope': world['scope'] + '/OUTSIDE'}
        rec, _ = await self.propose(wrong_scope, binding, world['id'] + '-wrong-scope',
                                   operation(world, 't0', {'control': 'not a measurement'}, 'negative scope'))
        self.check(world['id'] + ':wrong_scope_no_grant', rec['status'] == 'REQUIRES_REVIEW' and not rec['execution_permission']['allowed'])
        await self.call('transition_research_move', {'project': world['project'], 'move_id': rec['id'], 'action': 'abandon',
            'request_key': world['project'] + ':wrong-scope-cleanup', 'reason': 'Expected denial control complete.'})
        # Lexical point/germ examples share spelling, not representation or source identity.
        lexical_ids = []
        for index, representation in enumerate(('point_value', 'analytic_germ')):
            row = await self.call('record_result', {'project': world['project'], 'kind': 'hypothesis', 'focus': 'zero',
                'result': json.dumps({'claim_type': 'SOURCE_CLAIM', 'statement': 'Point zero is not zero analytic germ.',
                    'representation': representation, 'scope': world['scope'], 'version': 2, 'word': []}),
                'status': 'hypothesis', 'request_key': world['project'] + ':lexical:' + str(index)})
            lexical_ids.append(row['id'])
        norm, _ = requests(self.db, world, binding, final_event['id'])
        view = await self.call('research_normalize_preview', norm)
        concepts = [c for c in view['claims'] if c['source_record']['id'] in lexical_ids]
        self.check(world['id'] + ':point_germ_lexical_alias_not_merged', len(concepts) == 2 and len({c['concept_id'] for c in concepts}) == 2
                   and {c['representation'] for c in concepts} == {'point_value', 'analytic_germ'}
                   and any(i['relation'] == 'alias_candidate' and i['substitution_allowed'] is False for i in view['view']['interpretations']))
        # New append-only source view with a wrong representation; old records survive.
        events = event_rows(self.db, world['project'])
        root = json.loads(events[binding['root_id']]['content'])
        germ = lexical_ids[1]
        spec = root['source_spec']; old_ref = 'event:' + str(binding['histories'][binding['active'][0]])
        spec['histories'] = ['event:' + str(germ) if r == old_ref else r for r in spec['histories']]
        for h in spec['hypotheses']:
            if h['ref'] == old_ref: h['ref'] = 'event:' + str(germ)
        newroot = await self.event(world, 'negative-germ-root', root, parent=binding['root_id'])
        law = await self.event(world, 'negative-germ-law', law_payload(world, newroot, 2), parent=newroot['id'])
        germ_binding = copy.deepcopy(binding); germ_binding['histories'][binding['active'][0]] = germ
        germ_binding.update(root_id=newroot['id'], law_id=law['id'])
        _, req = requests(self.db, world, germ_binding, final_event['id'])
        denied = await self.call('research_native_preview', req)
        self.check(world['id'] + ':native_point_germ_substitution_denied', denied['status'] == 'INSUFFICIENT_CONTEXT')
        # Primitive display labels change; ordinal meaning and structural fingerprint do not.
        renamed = copy.deepcopy(world); names = {a: 'renamed_' + str(i) for i, a in enumerate(world['parameters']['actions'])}
        renamed['parameters']['actions'] = [names[a] for a in world['parameters']['actions']]
        renamed['histories'] = {n: [names[a] for a in w] for n, w in world['histories'].items()}
        for t in renamed['tests']: t['suffix'] = [names[a] for a in t['suffix']]
        renamed_binding = await self.seed_projection(renamed, binding, binding['active'], 2, binding,
                                                    [{'event_ref': 'event:' + str(first_event['id']), 'scope': world['scope']}], label_prefix='alias-')
        # seed_projection labels are namespaced separately to avoid reusing immutable request keys.
        _, req = requests(self.db, renamed, renamed_binding, final_event['id'])
        req['question']['known_fingerprints'] = [second['interpretation']['fingerprint']]
        renamed_out = await self.call('research_native_preview', req)
        self.check(world['id'] + ':primitive_rename_no_false_novelty', renamed_out['status'] == 'NO_NEW_DISTINCTION_BOUNDED')
        # Separate operator-specified instrument outcome control, not a third research-cycle success.
        test = {'test_id': world['tests'][0]['id'], **{k: world['tests'][0][k] for k in ('suffix', 'cost', 'ordinal')}}
        op = operation(world, test['test_id'], {'instrument_control': True}, 'INCONCLUSIVE instrument control; not a new T decision')
        record, move = await self.propose(world, binding, world['id'] + '-inconclusive', op, [first_event['id'], final_event['id']])
        self.operator_review(world, binding, move, [first_event['id'], final_event['id']], 'inconclusive')
        grant = await self.audit_activate(world, binding, world['id'] + '-inconclusive', record)
        measurement = await self.measure(world, binding, grant, test, world['id'] + '-inconclusive')
        _, complete = await self.finish(world, binding, grant, measurement, {'readout': None}, world['id'] + '-inconclusive', 'INCONCLUSIVE')
        self.check(world['id'] + ':INCONCLUSIVE_not_success_or_verified', complete['completion']['result']['outcome'] == 'INCONCLUSIVE'
                   and complete['proof_status'] == 'unverified' and not complete['execution_permission']['allowed'])
        await self.call('research_obligation_update', {'project': world['project'], 'obligation_id': binding['obligation_id'],
            'expected_version': 2, 'changes': qa_closure_changes(final_event['id'])})
        _, closed = requests(self.db, world, {**binding, 'version': 3}, final_event['id'])
        out = await self.call('research_native_preview', closed)
        self.check(world['id'] + ':closed_frontier_denied', out['status'] == 'INSUFFICIENT_CONTEXT' and out['reason'] == 'CLOSED_FRONTIER')
        for project, move_id in self.moves:
            if project != world['project']: continue
            current = await self.call('research_move_history', {'project': project, 'move_id': move_id})
            self.check(world['id'] + ':no_remaining_grant:' + str(move_id), not current['execution_permission']['allowed'])
