"""Fresh-project real HTTPS/OAuth causal-memory experiment (fixed 432 model calls)."""
import argparse
import asyncio
from datetime import datetime, timezone, timedelta
import hashlib
import json
import logging
import os
from pathlib import Path
import random
import resource
import sqlite3
import subprocess
import sys
import time

import httpx
from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client

from attention_qa import configure, intact, server_cpu
from causal_model import CONCURRENCY, MODEL, infer, make_prompt
from causal_oracle import score
from causal_worlds import MODES, SEEDS, digest, execute, public_definition, world
from frontier import fingerprint_hash
from qa_positive_acceptance import Acceptance, oauth, snapshot, write_json
from research_store import ResearchStore


class CriticalDefect(RuntimeError):
    pass


class CausalRun(Acceptance):
    def __init__(self, private, db, origin, report):
        super().__init__(private, db, origin)
        self.private, self.report = private, report
        self.lock = asyncio.Lock()
        self.semaphore = asyncio.Semaphore(CONCURRENCY)
        self.rows, self.states, self.lifecycle = [], [], []
        self.control_moves = []
        self.stopped = False
        self.started = time.monotonic()
        self.local_cpu = time.process_time()
        self.children = resource.getrusage(resource.RUSAGE_CHILDREN)
        self.server_begin = server_cpu()

    def append(self, name, value):
        with (self.private / name).open('a') as stream:
            stream.write(json.dumps(value, ensure_ascii=False) + '\n')

    async def call(self, name, arguments, allow_error=False):
        async with self.lock:
            response = await self.session.call_tool(name, arguments)
            raw = response.model_dump(mode='json')
            entry = {'index': len(self.calls) + 1, 'tool': name, 'arguments': arguments, 'response': raw}
            self.calls.append(entry)
            self.append('calls.jsonl', entry)
            if response.isError:
                if allow_error:
                    return None
                raise RuntimeError(name + ': ' + ''.join(c.text for c in response.content if c.type == 'text'))
            return response.structuredContent if response.structuredContent is not None else json.loads(response.content[0].text)

    async def seed(self, w, fork):
        project = f'LM_QA_CM2_{self.private.name}_{w["index"]}_{w["repeat"]}_{fork}'
        events = {}
        for key in w['event_order']:
            if key == 'conflict' and fork != 'c':
                continue
            event = w['events'][key]
            arguments = {'project': project, 'kind': event['kind'], 'status': event['status'],
                'focus': w['labels'][w['event_order'].index(key)], 'result': json.dumps(event['content'], sort_keys=True),
                'request_key': project + ':event:' + key}
            if key != 'source':
                arguments['parent_id'] = events['source']
            response = await self.call('record_result', arguments)
            events[key] = response['id']
        with ResearchStore(self.db)._connect() as connection:
            sources = [dict(connection.execute('SELECT * FROM events WHERE id=?', (i,)).fetchone()) for i in events.values()]
        grounds = {'measure': ['source', 'x', 'y'], 'archive': ['archive'], 'closed': ['counter'],
                   'diagnose': ['source', 'counter', 'diagnostic']}
        statuses = {'measure': 'OPEN', 'archive': 'SUPERSEDED', 'closed': 'REFUTED', 'diagnose': 'OPEN'}
        statements = {'measure': 'Read finite item values using the declared observable.',
            'archive': 'Aggregate view from source version 1, replaced by version 2.',
            'closed': 'The stated item equality disagrees with its retained comparison.',
            'diagnose': 'Inspect the item-level trace behind the recorded discrepancy.'}
        obligations = []
        for key in w['obligation_order']:
            ids = [events[k] for k in grounds[key]]
            item = {'key': key, 'statement': statements[key], 'scope': w['scope'],
                    'source_event_ids': ids, 'evidence_refs': ['event:' + str(i) for i in ids], 'status': statuses[key]}
            if key in {'archive', 'closed'}:
                item.update(closure_reason=statements[key], reopen_conditions=['New source-specific evidence and an explicit new version.'])
            obligations.append(item)
        blueprint = {'import_key': project + ':fixture', 'project': project,
            'sources': [{'id': s['id'], 'sha256': fingerprint_hash(s)} for s in sources],
            'obligations': obligations,
            'constraints': [{'kind': 'allowed_experiment', 'obligation_key': 'measure',
                'mechanisms': [w['mechanism']], 'source_event_ids': [events['source']],
                'source_representations': [w['representation']], 'scope': w['scope'],
                'reason': 'User-authorized finite synthetic source reading; no transformations or truth claims.',
                'reopen_conditions': ['Changed source, operation or scope requires review.']}]}
        imported = ResearchStore(self.db).frontier.import_history(blueprint, 'Preregistered causal-memory QA operator fixture')
        state = {'world': w, 'project': project, 'events': events, 'obligations': imported['obligation_ids'], 'fork': fork}
        self.states.append(state)
        self.append('operator-imports.jsonl', {'project': project, 'request': blueprint, 'response': imported,
                                             'origin': 'human(operator)_precommitted_fixture'})
        state['stale'] = await self.context(state)
        await self.call('research_obligation_update', {'project': project, 'obligation_id': state['obligations']['measure'],
            'expected_version': 1, 'changes': {'status': 'TESTING'}})
        # Keep diagnostic version aligned for unambiguous scopes, no new permission.
        await self.call('research_obligation_update', {'project': project, 'obligation_id': state['obligations']['diagnose'],
            'expected_version': 1, 'changes': {'status': 'TESTING'}})
        state['current'] = await self.context(state)
        return state

    async def context(self, state):
        context = await self.call('research_context', {'project': state['project'], 'limit': 100})
        frontier = await self.call('research_frontier', {'project': state['project'], 'include_closed': True})
        events = [{k: e[k] for k in ('id', 'kind', 'focus', 'status', 'parent_id')} |
                  {'content': json.loads(e['content'])} for e in context['events']]
        return {'project': state['project'], 'events': events, 'frontier': frontier}

    def move(self, state, a):
        operation = {'mechanism': a['mechanism'], 'intent': 'experiment',
            'premises': a['assumes'] or ['Read only the declared finite source'],
            'mathematical_properties': [a['observable']],
            'testable_consequence': json.dumps({'inputs': a['input_ids'], 'tests': a['tests'], 'falsification': a['falsification']}, sort_keys=True),
            'required_evidence': ['Project-local finite observation retaining input origin IDs']}
        move = {'parent_event_ids': a['parent_event_ids'], 'proposed_operation': operation,
            'source_representation': a['source_representation'], 'target_representation': a['target_representation'],
            'verification_plan': {'method': a['minimal_experiment'], 'failure_condition': json.dumps(a['falsification'])},
            'evidence_refs': a['evidence_refs']}
        if a['obligation_id'] is not None:
            move['active_frontier_id'] = a['obligation_id']
        return move

    async def audit_output(self, state, output):
        report = await self.call('audit_research_shift', {'project': state['project'],
            'proposal': output['action']['reason'], **self.move(state, output['action'])}, allow_error=True)
        if report and (report.get('execution_permission', {}).get('allowed') or report.get('proof_status') == 'verified'):
            self.stopped = True
            raise CriticalDefect('MCP_CORE_BUG: advisory audit issued a permission/proof.')
        return report

    async def feedback(self, state):
        w, project, events = state['world'], state['project'], state['events']
        f = w['feedback']
        operation = {'mechanism': w['mechanism'], 'intent': 'experiment',
            'premises': ['Read the fixed finite source'], 'mathematical_properties': [w['observable']],
            'testable_consequence': f['input_id'] + ' = ' + str(f['asserted_value']),
            'required_evidence': ['One source-linked finite item measurement']}
        move = {'active_frontier_id': state['obligations']['measure'], 'active_frontier_version': 2,
            'scope': w['scope'], 'parent_event_ids': [events['source']], 'proposed_operation': operation,
            'source_representation': w['representation'], 'target_representation': w['representation'],
            'verification_plan': {'method': 'Evaluate the declared source observable on the selected input.',
                                  'failure_condition': 'Observed integer differs from the stated assertion.'}}
        recorded = await self.call('record_research_move', {'project': project, 'move': move, 'request_key': project + ':compute:record'})
        mid = recorded['id']
        self.control_moves.append((project, mid))
        await self.call('audit_research_move', {'project': project, 'move_id': mid, 'request_key': project + ':compute:audit'})
        granted = await self.call('transition_research_move', {'project': project, 'move_id': mid,
            'action': 'activate_experiment', 'request_key': project + ':compute:activate'})
        if not granted['execution_permission']['allowed']:
            raise CriticalDefect('MCP_CORE_BUG or DATA_FIXTURE_BUG: exact finite control experiment not permitted.')
        measured = execute(w, f['input_id'])
        result = {'outcome': 'FAILURE', 'summary': 'The finite item measurement differs from the hypothesized value.',
            'data': {'source_id': w['source_id'], 'source_version': 2, 'input_id': f['input_id'],
                     'statement_id': f['premise_id'], 'asserted_value': f['asserted_value'], 'measured_value': measured,
                     'observable': w['observable'], 'label': f['label'], 'text': f['text'], 'scope': 'This item comparison only.'}}
        event = await self.call('record_result', {'project': project, 'kind': 'failed_check', 'status': 'experiment',
            'focus': w['labels'][10], 'result': json.dumps(result['data'], sort_keys=True), 'parent_id': events['source'],
            'request_key': project + ':feedback'})
        events['feedback'] = event['id']
        done = await self.call('transition_research_move', {'project': project, 'move_id': mid, 'action': 'complete',
            'result': result, 'reason': 'Precommitted independent bounded check returned a counter-observation, not a theorem.',
            'evidence_refs': ['event:' + str(event['id'])], 'request_key': project + ':compute:complete'})
        if done['proof_status'] != 'unverified' or done['execution_permission']['allowed']:
            self.stopped = True
            raise CriticalDefect('MCP_CORE_BUG: completed control retains grant or verified status.')
        unrelated = await self.call('record_result', {'project': project, 'kind': 'failed_check', 'status': 'experiment',
            'focus': w['labels'][11], 'result': json.dumps({'source_id': 'separate_source', 'input_id': 'separate_input',
                'asserted_value': 7, 'measured_value': 6, 'scope': 'A distinct source only.'}),
            'request_key': project + ':unrelated_feedback'})
        events['unrelated_feedback'] = unrelated['id']
        self.lifecycle.append({'project': project, 'move_id': mid, 'state': done, 'origin': 'compute',
            'selection_origin': 'human(operator)_precommitted', 'assisted_disposition': False})
        self.append('lifecycles.jsonl', self.lifecycle[-1])
        state['current'] = await self.context(state)

    async def model_step(self, state, mode, step, previous=None):
        if self.stopped:
            return None
        w = state['world']
        visible = state['stale'] if mode == 'M3' and step == 't0' else state['current']
        data = {'memory': visible}
        if mode == 'M3' and step == 't0':
            data['freshness_receipt'] = {'current_obligation_versions': {
                str(state['obligations'][k]): 2 for k in ('measure', 'diagnose')},
                'snapshot_is_current': False}
        if previous and mode in {'M2', 'M3', 'M4'}:
            data['previous_audit'] = previous.get('audit')
        if previous:
            data['previous_proposal'] = previous.get('output')
        # M0 remains without history at both steps, including no proposal replay.
        prompt = make_prompt(data, mode)
        label = f'w{w["index"]:02d}-r{w["repeat"]}-{mode}-{step}'
        self.append('prompts.jsonl', {'id': label, 'world': w['index'], 'repeat': w['repeat'], 'mode': mode,
            'step': step, 'prompt': prompt, 'payload_hash': digest(data) if mode != 'M0' else None})
        result = await infer(self.private / 'models' / label, prompt, self.semaphore)
        row = {'id': label, 'world': w['index'], 'repeat': w['repeat'], 'mode': mode, 'step': step,
            'project': state['project'], 'origin': 'LLM', **result}
        if result['outcome'] == 'OK':
            metrics = score(result['output'], {**state, 'mode': mode}, step == 't1')
            row['metrics'] = metrics
            if mode in {'M2', 'M3', 'M4'}:
                row['audit'] = await self.audit_output(state, result['output'])
            if mode == 'M3' and result['output']['action']['refresh_required']:
                fresh = await self.context(state)
                row['actual_reread_sha256'] = digest(fresh)
                # Fixed second step receives fresh state; no extra model call or hidden correction.
            if previous and previous.get('output'):
                a, b = previous['output']['action'], result['output']['action']
                row['structural_diff'] = {k: {'before': a[k], 'after': b[k]} for k in a if a[k] != b[k]}
        self.rows.append(row)
        self.append('model_outputs.jsonl', row)
        print(json.dumps({'id': label, 'outcome': row['outcome'], 'completed': len(self.rows), 'planned': 432}), flush=True)
        return row

    async def group(self, w):
        try:
            normal, conflict = await self.seed(w, 'n'), await self.seed(w, 'c')
            modes = list(MODES)
            random.Random(w['seed'] + w['index']).shuffle(modes)
            first = await asyncio.gather(*(self.model_step(conflict if m == 'M4' else normal, m, 't0') for m in modes))
            if self.stopped:
                return
            await self.feedback(normal)
            await self.feedback(conflict)
            await asyncio.gather(*(self.model_step(conflict if m == 'M4' else normal, m, 't1', before)
                                  for m, before in zip(modes, first)))
        except CriticalDefect as error:
            self.stopped = True
            self.append('failures.jsonl', {'world': w['index'], 'repeat': w['repeat'], 'classification': 'MCP_CORE_BUG', 'error': str(error)})
            raise
        except Exception as error:
            self.append('failures.jsonl', {'world': w['index'], 'repeat': w['repeat'],
                'classification': 'TRANSPORT_FAILURE', 'error': type(error).__name__ + ': ' + str(error)})

    async def run(self, token):
        async with httpx.AsyncClient(headers={'Authorization': 'Bearer ' + token}, timeout=45,
            event_hooks={'request': [self.request_hook], 'response': [self.response_hook]}) as http:
            async with streamable_http_client(self.endpoint, http_client=http) as (read, write, _):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=55),
                    client_info=types.Implementation(name='LM-CAUSAL-MEMORY-002', version='1.0')) as session:
                    self.session = session
                    initialize = await session.initialize()
                    tools = await session.list_tools()
                    write_json(self.private / 'tools-list.json', tools.model_dump(mode='json'))
                    preflight = {'initialize': initialize.model_dump(mode='json'),
                        'health': await self.call('service_health', {}),
                        'contract': await self.call('research_contract', {}),
                        'rh_frontier': await self.call('research_frontier', {'project': 'RH', 'include_closed': True})}
                    write_json(self.private / 'preflight.json', preflight)
                    if initialize.serverInfo.version != '0.4.2' or len(tools.tools) != 18:
                        raise RuntimeError('Unexpected live contract; no QA writes performed.')
                    regression = self.private / ('regression-' + self.private.name)
                    with (self.private / 'regression-output.txt').open('w') as log:
                        process = await asyncio.create_subprocess_exec(sys.executable,
                            str(Path(__file__).with_name('qa_positive_acceptance.py')), '--out', str(regression),
                            stdout=log, stderr=asyncio.subprocess.STDOUT)
                        if await process.wait():
                            raise RuntimeError('Existing real 86-invariant regression failed; no model calls started.')
                    tasks = [asyncio.create_task(self.group(world(i, r))) for i in range(12) for r in range(3)]
                    try:
                        await asyncio.gather(*tasks)
                    except CriticalDefect:
                        for task in tasks:
                            task.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)
                    finally:
                        for project, mid in self.control_moves:
                            current = await self.call('research_move_history', {'project': project, 'move_id': mid})
                            if current['execution_permission']['allowed']:
                                await self.call('transition_research_move', {'project': project, 'move_id': mid,
                                    'action': 'abandon', 'reason': 'Finite QA stop/cleanup.',
                                    'request_key': project + ':cleanup:' + str(mid)})
                    write_json(self.private / 'postflight.json', {'health': await self.call('service_health', {}),
                        'rh_frontier': await self.call('research_frontier', {'project': 'RH', 'include_closed': True})})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-root', type=Path)
    parser.add_argument('--previous-preparation', type=Path, help='Preserve a stopped pre-inference preparation; never reuse its projects.')
    parser.add_argument('--previous-invalid-run', type=Path, help='Preserve an aborted invalid prompt run; do not pool its outcomes.')
    args = parser.parse_args()
    os.umask(0o077)
    root = Path(__file__).resolve().parent.parent
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    private = Path.home() / '.local/state/livingmath/causal-memory' / stamp
    private.mkdir(parents=True, exist_ok=False)
    report = (args.report_root or root / 'docs/qa') / ('LM-CAUSAL-MEMORY-002-' + stamp)
    config = configure()
    db = (Path(config['LIVE_MATH_DATA_DIR']) / 'research.sqlite3').resolve(strict=True)
    backup = private / 'research-before.sqlite3'
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(backup) as dst:
        src.backup(dst)
    before = snapshot(backup)
    before['inode'] = db.stat().st_ino
    write_json(private / 'before.json', before)
    write_json(private / 'metadata.json', {'private': str(private), 'report': str(report),
        'endpoint': config['LIVE_MATH_PUBLIC_URL'] + '/mcp', 'backup_sha256': hashlib.sha256(backup.read_bytes()).hexdigest(),
        'original_events': len(before['tables']['events']), 'original_operations': len(before['tables']['operations']),
        'codex_version': subprocess.check_output(['codex', '--version'], text=True).strip(),
        'native_generation': False, 'model': MODEL, 'seeds': SEEDS, 'planned_model_calls': 432,
        'previous_preparation': str(args.previous_preparation) if args.previous_preparation else None,
        'previous_invalid_run': str(args.previous_invalid_run) if args.previous_invalid_run else None,
        'protocol_revision': 2, 'inference_concurrency': CONCURRENCY,
        'preregistered_protocol': 'docs/superpowers/plans/2026-10-26-causal-memory-002.md'})
    definitions = [world(i, r) for i in range(12) for r in range(3)]
    write_json(private / 'worlds.json', [public_definition(w) for w in definitions])
    write_json(private / 'oracle.json', [w['oracle'] for w in definitions])
    source_hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in (root / 'live_math_mcp_prod').glob('*.py')}
    source_hashes['AGENTS.md'] = hashlib.sha256((root / 'AGENTS.md').read_bytes()).hexdigest()
    write_json(private / 'source-hashes-before.json', source_hashes)
    (private / 'preregistration.md').write_text((root / 'docs/superpowers/plans/2026-10-26-causal-memory-002.md').read_text())
    write_json(private / 'registration.json', {'frozen_utc': datetime.now(timezone.utc).isoformat(),
        'oracle_sha256': hashlib.sha256((private / 'oracle.json').read_bytes()).hexdigest(),
        'worlds_sha256': hashlib.sha256((private / 'worlds.json').read_bytes()).hexdigest(),
        'protocol_sha256': hashlib.sha256((private / 'preregistration.md').read_bytes()).hexdigest()})
    print(json.dumps({'private': str(private), 'report': str(report), 'planned': 432}), flush=True)
    with (private / 'pytest.txt').open('w') as output:
        tests = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(root / 'live_math_mcp_prod')],
                               cwd=root, stdout=output, stderr=subprocess.STDOUT)
    if tests.returncode:
        raise SystemExit('Local regression failed; no public writes or model calls performed. See ' + str(private / 'pytest.txt'))
    logging.basicConfig(level=logging.WARNING)
    runner = CausalRun(private, db, config['LIVE_MATH_PUBLIC_URL'], report)
    try:
        oauth(config, runner)
    finally:
        write_json(private / 'calls.json', runner.calls)
        write_json(private / 'states.json', [{'project': s['project'], 'world': s['world']['index'],
            'repeat': s['world']['repeat'], 'events': s['events'], 'obligations': s['obligations']} for s in runner.states])
        server_end = server_cpu()
        children_end = resource.getrusage(resource.RUSAGE_CHILDREN)
        write_json(private / 'cpu.json', {'client_seconds': time.process_time() - runner.local_cpu,
            'children_seconds': children_end.ru_utime + children_end.ru_stime - runner.children.ru_utime - runner.children.ru_stime,
            'server_seconds': server_end['seconds'] - runner.server_begin['seconds'] if server_end['pid'] == runner.server_begin['pid'] else None,
            'wall_seconds': time.monotonic() - runner.started, 'remote_inference_seconds': None})
        from causal_report import export
        result = export(private)
        print(json.dumps({'result': result, 'report': str(report)}), flush=True)


if __name__ == '__main__':
    main()
