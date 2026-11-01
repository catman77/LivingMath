"""Transport-only continuation: never repeat an already started model inference.

Run only after causal_qa.py exits. Each remaining world/repeat uses a fresh
owner OAuth session, keeping its maximum inference window below one hour.
The model, prompts, scorer, seeds and 432-cell matrix remain unchanged.
"""
import argparse
import asyncio
import hashlib
import json
import random
from pathlib import Path
import sqlite3
import resource
import time

import httpx
from datetime import timedelta
from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client

from attention_qa import configure, server_cpu
from causal_model import infer, make_prompt, MODEL, INPUT_TOKENS
from causal_oracle import score
from causal_qa import CausalRun
from causal_worlds import MODES, world, digest
from causal_transport_contract import cleanup_patch_valid
from qa_positive_acceptance import oauth, write_json
from research_store import ResearchStore


def read_rows(path):
    return [json.loads(s) for s in path.read_text().splitlines() if s.strip()] if path.exists() else []


def prior_attempt(directory):
    if (directory / 'receipt.json').exists():
        return json.loads((directory / 'receipt.json').read_text())
    if (directory / 'events.jsonl').exists():
        # Interrupted started requests remain failures, even if a partial answer exists.
        return {'outcome': 'TRANSPORT_FAILURE', 'metadata': {
            'requested_model': MODEL, 'reasoning_effort': 'low', 'actual_usage': None,
            'wall_seconds': None, 'estimated_user_input_tokens': INPUT_TOKENS,
            'measurement_limitation': 'Request started but was interrupted before a receipt; no retry and no imputed timing.'}}
    return None


def recorded_attempt(base, label):
    directories = [base / 'models' / label]
    directories.extend((base / 'transport-continuation').glob('*/models/' + label))
    attempted = [directory for directory in directories if (directory / 'events.jsonl').exists() or (directory / 'receipt.json').exists()]
    if len(attempted) > 1:
        raise RuntimeError('More than one inference attempt exists for ' + label + '; no automatic continuation.')
    return prior_attempt(attempted[0]) if attempted else None


class RecoveryTrial(CausalRun):
    def __init__(self, base, checkpoint, db, config, known, definitions, index, repeat, parallelism=4):
        super().__init__(checkpoint, db, config['LIVE_MATH_PUBLIC_URL'], Path(json.loads((base / 'metadata.json').read_text())['report']))
        self.base, self.known = base, known
        self.definitions, self.index, self.repeat = definitions, index, repeat
        self.parallelism = parallelism
        self.semaphore = asyncio.Semaphore(parallelism)

    def persist(self, row):
        if row['id'] in self.known:
            raise RuntimeError('Refusing duplicate inference outcome: ' + row['id'])
        self.known[row['id']] = row
        with (self.base / 'model_outputs.jsonl').open('a') as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        self.append('model_outputs.jsonl', row)
        print(json.dumps({'id': row['id'], 'outcome': row['outcome'], 'completed': len(self.known), 'planned': 432}), flush=True)

    async def step(self, state, mode, step, previous=None):
        label = f'w{self.index:02d}-r{self.repeat}-{mode}-{step}'
        if label in self.known:
            return self.known[label]
        old = self.base / 'models' / label
        receipt = recorded_attempt(self.base, label)
        new_call = receipt is None
        if new_call:
            if (old / 'prompt.txt').exists():
                prompt = (old / 'prompt.txt').read_text()
            else:
                if step == 't0':
                    raise RuntimeError('Missing preregistered t0 prompt; refusing reconstruction from later history.')
                data = {'memory': state['current']}
                if previous and mode in {'M2', 'M3', 'M4'}:
                    data['previous_audit'] = previous.get('audit')
                if previous:
                    data['previous_proposal'] = previous.get('output')
                prompt = make_prompt(data, mode)
            self.append('prompts.jsonl', {'id': label, 'prompt': prompt, 'continuation_of_fixed_matrix': True})
            receipt = await infer(self.private / 'models' / label, prompt, self.semaphore)
        row = {'id': label, 'world': self.index, 'repeat': self.repeat, 'mode': mode, 'step': step,
               'project': state['project'], 'origin': 'LLM', 'transport_continuation': True,
               'new_inference': new_call, 'controller_parallelism': self.parallelism, **receipt}
        if receipt['outcome'] == 'OK':
            scoring_state = {**state, 'mode': mode}
            if step == 't0':
                scoring_state['events'] = {k: v for k, v in state['events'].items()
                                           if k not in {'feedback', 'unrelated_feedback'}}
            row['metrics'] = score(receipt['output'], scoring_state, step == 't1')
            if new_call and mode in {'M2', 'M3', 'M4'}:
                row['audit'] = await self.audit_output(state, receipt['output'])
            elif mode in {'M2', 'M3', 'M4'}:
                row['audit_transport_failure_preserved'] = True
            if mode == 'M3' and receipt['output']['action']['refresh_required']:
                row['actual_reread_sha256'] = digest(await self.context(state))
            if previous and previous.get('output'):
                a, b = previous['output']['action'], receipt['output']['action']
                row['structural_diff'] = {k: {'before': a[k], 'after': b[k]} for k in a if a[k] != b[k]}
        self.persist(row)
        return row

    async def ensure_feedback(self, state):
        store = ResearchStore(self.db)
        with store._connect() as connection:
            moves = connection.execute('SELECT id FROM research_moves WHERE project=?', (state['project'],)).fetchall()
        if len(moves) > 1:
            raise RuntimeError('Unexpected multiple control moves; no automatic recovery.')
        complete = bool(moves and store.moves.inspect(state['project'], moves[0]['id'])['status'] == 'COMPLETED')
        if not complete:
            await self.feedback(state)
        else:
            with store._connect() as connection:
                for key in ('feedback', 'unrelated_feedback'):
                    row = connection.execute('SELECT event_id FROM request_keys WHERE key=?', (state['project'] + ':' + key,)).fetchone()
                    if row:
                        state['events'][key] = row['event_id']
            if 'feedback' not in state['events']:
                raise RuntimeError('Completed experiment without source feedback; no synthetic repair.')
            if 'unrelated_feedback' not in state['events']:
                w = state['world']
                event = await self.call('record_result', {'project': state['project'], 'kind': 'failed_check', 'status': 'experiment',
                    'focus': w['labels'][11], 'result': json.dumps({'source_id': 'separate_source', 'input_id': 'separate_input',
                        'asserted_value': 7, 'measured_value': 6, 'scope': 'A distinct source only.'}),
                    'request_key': state['project'] + ':unrelated_feedback'})
                state['events']['unrelated_feedback'] = event['id']
            state['current'] = await self.context(state)

    async def run(self, token):
        async with httpx.AsyncClient(headers={'Authorization': 'Bearer ' + token}, timeout=45,
            event_hooks={'request': [self.request_hook], 'response': [self.response_hook]}) as http:
            async with streamable_http_client(self.endpoint, http_client=http) as (read, write, _):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=55),
                    client_info=types.Implementation(name='LM-CAUSAL-MEMORY-002-transport-continuation', version='2')) as session:
                    self.session = session
                    await session.initialize()
                    states = []
                    for definition in self.definitions:
                        state = {**definition, 'world': world(self.index, self.repeat)}
                        state['current'] = await self.context(state)
                        states.append(state)
                    normal = next(s for s in states if s['project'].endswith('_n'))
                    conflict = next(s for s in states if s['project'].endswith('_c'))
                    modes = list(MODES)
                    random.Random(normal['world']['seed'] + self.index).shuffle(modes)
                    first = await asyncio.gather(*(self.step(conflict if mode == 'M4' else normal, mode, 't0') for mode in modes))
                    await self.ensure_feedback(normal)
                    await self.ensure_feedback(conflict)
                    await asyncio.gather(*(self.step(conflict if mode == 'M4' else normal, mode, 't1', before)
                                          for mode, before in zip(modes, first)))
                    write_json(self.private / 'postflight.json', {'health': await self.call('service_health', {}),
                        'rh_frontier': await self.call('research_frontier', {'project': 'RH', 'include_closed': True})})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-dir', type=Path, required=True)
    parser.add_argument('--parallelism', type=int, choices=(1, 2, 3, 4), default=4,
                        help='Transport connection cap, never above the registered maximum four.')
    parser.add_argument('--checkpoint-suffix', default='')
    args = parser.parse_args()
    base = args.private_dir.resolve(strict=True)
    root = Path(__file__).resolve().parent.parent
    frozen = json.loads((base / 'source-hashes-before.json').read_text())
    for name in ('causal_model.py', 'causal_oracle.py', 'causal_worlds.py'):
        relative = 'live_math_mcp_prod/' + name
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != frozen[relative]:
            if name == 'causal_model.py' and cleanup_patch_valid(base, root / relative):
                continue
            raise SystemExit('Scientific protocol changed; refusing continuation: ' + name)
    config = configure()
    db = (Path(config['LIVE_MATH_DATA_DIR']) / 'research.sqlite3').resolve(strict=True)
    known = {r['id']: r for r in read_rows(base / 'model_outputs.jsonl')}
    states = json.loads((base / 'states.json').read_text())
    for index in range(12):
        for repeat in range(3):
            if all(f'w{index:02d}-r{repeat}-{mode}-{step}' in known for mode in MODES for step in ('t0', 't1')):
                continue
            checkpoint = base / 'transport-continuation' / (f'w{index:02d}-r{repeat}' + args.checkpoint_suffix)
            checkpoint.mkdir(parents=True, exist_ok=False)
            definitions = [s for s in states if s['world'] == index and s['repeat'] == repeat]
            if len(definitions) != 2:
                raise SystemExit('Incomplete fixture: no new model calls can be safely reconstructed.')
            trial = RecoveryTrial(base, checkpoint, db, config, known, definitions, index, repeat, args.parallelism)
            try:
                oauth(config, trial)
            finally:
                write_json(checkpoint / 'calls.json', trial.calls)
                children = resource.getrusage(resource.RUSAGE_CHILDREN)
                server_end = server_cpu()
                write_json(checkpoint / 'cpu.json', {'client_seconds': time.process_time() - trial.local_cpu,
                    'children_seconds': children.ru_utime + children.ru_stime - trial.children.ru_utime - trial.children.ru_stime,
                    'server_seconds': server_end['seconds'] - trial.server_begin['seconds'] if server_end['pid'] == trial.server_begin['pid'] else None,
                    'wall_seconds': time.monotonic() - trial.started, 'remote_inference_seconds': None})
    print(json.dumps({'fixed_matrix_outcomes': len(known), 'planned': 432}), flush=True)


if __name__ == '__main__':
    main()
