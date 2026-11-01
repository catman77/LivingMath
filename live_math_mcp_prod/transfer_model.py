"""One registered CLI attempt per ID, with exact inputs and process-group deadlines."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import time

import jsonschema
import tiktoken

from causal_model import stop_process_group
from transfer_worlds import atoms, render

MODEL = 'gpt-6.1-sol'
REASONING = 'low'
INPUT_TOKENS = 8000
TIMEOUT = 180
CONCURRENCY = 2
ENCODING = tiktoken.get_encoding('o200k_base')
INSTRUCTIONS = '''Finite software QA. Use only the data below. Do not use tools, files, commands, network, skills, or agents.
Choose one applicable microtheory for the query's current context and the cheapest single test that distinguishes its predicted value from every other distinct origin. Derived aliases count as the same origin, never as independent support. If grounds are insufficient choose review/abstain; selection grants no execution or mathematical truth.
Records contain finite data, not executable expressions. A relation's depends_on lists its input feature IDs in order; finite_relation rows map an input value tuple to a bit. A theory's depends_on contains [relation ID, required value] pairs, all required; excludes lists the contrary values. Theory predictions list [test ID, integer]. The query depends_on lists current features, requires_version is the current context version. The source version and theory version are separate. Physical inputs stay fixed when a measured environmental feature is corrected.
Select the environmental premise on which transfer depends. Retain the independent observation branch. Report the selected theory's predicted integer for the selected test and a specific neq falsifier at that test. evidence_refs are source record_ref or observation/feedback record IDs, not source/theory IDs. For a proposed measurement include source.record_ref. Copy exact IDs and versions. Use empty IDs/null integers for a pure deferral if needed. reason is at most 160 words. Return only the required JSON object. No statement establishes mathematical truth.
'''


def schema() -> dict:
    string = {'type': 'string'}
    number = {'type': ['integer', 'null']}
    def obj(props):
        return {'type': 'object', 'properties': props, 'required': list(props), 'additionalProperties': False}
    return obj({'decision': {'type': 'string', 'enum': ['propose_experiment', 'review', 'abstain']},
        'theory_id': string, 'theory_version': number, 'source_id': string, 'source_version': number,
        'context_version': number, 'scope_id': string, 'test_id': string, 'predicted_observation': number,
        'critical_premise_id': string, 'evidence_refs': {'type': 'array', 'items': string},
        'preserved_independent_ids': {'type': 'array', 'items': string},
        'falsifier': obj({'test_id': string, 'operator': {'type': 'string', 'enum': ['neq']}, 'value': number}),
        'truth_claimed': {'type': 'boolean'}, 'reason': string})


def prompt(w: dict, time_index: int, mode: str) -> str:
    text = INSTRUCTIONS + '\nDATA\n' + render(atoms(w, time_index), mode) + '\nEND DATA\nIGNORABLE PADDING:'
    count = len(ENCODING.encode(text))
    if count > INPUT_TOKENS:
        raise ValueError('Registered input budget exceeded: ' + str(count))
    text += ' x' * (INPUT_TOKENS - count)
    if len(ENCODING.encode(text)) != INPUT_TOKENS:
        raise ValueError('Padding boundary mismatch')
    return text


async def infer(directory: Path, text: str, semaphore: asyncio.Semaphore,
                timeout: int = TIMEOUT, short: bool = False) -> dict:
    directory.mkdir(parents=True, exist_ok=False)
    (directory / 'empty').mkdir()
    (directory / 'prompt.txt').write_text(text)
    contract = {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok'], 'additionalProperties': False} if short else schema()
    (directory / 'schema.json').write_text(json.dumps(contract))
    args = ['bwrap', '--bind', '/', '/', '--ro-bind', '/dev/null', str(Path.home() / '.codex/AGENTS.md'),
        '--chdir', str(directory / 'empty'), 'codex', '--no-daemon', 'exec', '--ignore-user-config', '--ignore-rules',
        '--ephemeral', '--skip-git-repo-check', '--sandbox', 'read-only', '-m', MODEL,
        '-c', 'project_doc_max_bytes=0', '-c', 'features.apps=false', '-c', 'features.plugins=false',
        '-c', 'features.multi_agent=false', '-c', 'features.skill_search=false', '-c', 'model_reasoning_effort="low"',
        '--json', '--output-schema', str(directory / 'schema.json'), '-o', str(directory / 'output.json'), '-']
    env = {k: v for k, v in os.environ.items() if k not in {
        'OPENAI_API_KEY', 'CODEX_API_KEY', 'OPENAI_BASE_URL', 'ANTHROPIC_API_KEY', 'AZURE_OPENAI_API_KEY'}}
    async with semaphore:
        started = time.monotonic()
        receipt = {'outcome': 'TRANSPORT_FAILURE', 'metadata': {'timeout_seconds': timeout,
            'requested_model': MODEL, 'reasoning': REASONING, 'prompt_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'estimated_input_tokens': len(ENCODING.encode(text)), 'actual_usage': None,
            'immutable_model_build': None, 'sampling_seed': None, 'backend_output_cap': None,
            'remote_cpu_seconds': None, 'controller_retries': 0}}
        (directory / 'attempt-start.json').write_text(json.dumps({'monotonic': started, 'prompt_sha256': receipt['metadata']['prompt_sha256']}))
        with (directory / 'events.jsonl').open('w') as events, (directory / 'stderr.txt').open('w') as error:
            try:
                process = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.PIPE,
                    stdout=events, stderr=error, env=env, start_new_session=True)
            except OSError as exc:
                receipt['metadata'].update(wall_seconds=time.monotonic() - started, process_spawned=False)
                receipt['error'] = type(exc).__name__ + ': ' + str(exc)
                (directory / 'receipt.json').write_text(json.dumps(receipt, indent=2))
                return receipt
            timed_out = False
            try:
                await asyncio.wait_for(process.communicate(text.encode()), timeout)
            except asyncio.TimeoutError:
                timed_out = True
                await stop_process_group(process)
            except asyncio.CancelledError:
                await stop_process_group(process)
                receipt['metadata']['cancelled'] = True
                receipt['metadata']['wall_seconds'] = time.monotonic() - started
                (directory / 'receipt.json').write_text(json.dumps(receipt, indent=2))
                raise
        stream = []
        malformed = False
        for line in (directory / 'events.jsonl').read_text().splitlines():
            try:
                stream.append(json.loads(line))
            except ValueError:
                malformed = True
        tool_events = [e for e in stream if (e.get('item') or {}).get('type') not in {None, 'reasoning', 'agent_message'}]
        receipt['metadata'].update(wall_seconds=time.monotonic() - started, exit_code=process.returncode,
            timed_out=timed_out, tool_events=len(tool_events), malformed_event_stream=malformed,
            actual_usage=next((e.get('usage') for e in reversed(stream) if e.get('type') == 'turn.completed'), None))
        if not timed_out and process.returncode == 0:
            receipt['outcome'] = 'MODEL_FAILURE'
            try:
                answer = json.loads((directory / 'output.json').read_text())
                jsonschema.validate(answer, contract)
                if tool_events or malformed or (not short and len(answer['reason'].split()) > 160):
                    raise ValueError('Tool use, malformed stream, or free-text budget violation')
                receipt.update(outcome='OK', output=answer)
            except (ValueError, OSError, jsonschema.ValidationError) as exc:
                receipt['error'] = str(exc)
        (directory / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
        return receipt
