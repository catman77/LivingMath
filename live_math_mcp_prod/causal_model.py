"""Fixed-budget, isolated one-action model calls; no MCP or oracle access in children."""
import asyncio
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import subprocess
import time

import jsonschema
import tiktoken

MODEL = 'gpt-6.1-sol'
INPUT_TOKENS = 9500
TIMEOUT = 240
CONCURRENCY = 4
ENCODING = tiktoken.get_encoding('o200k_base')
TASK = ('Choose exactly one next research action in the current finite-source task. State its premises, '
        'the previously unknown fact it would distinguish, a minimal executable test, a concrete falsifier, '
        'and which retained events allow or constrain it. Request review if grounds are insufficient. '
        'Do not claim mathematical truth. Keep independent observations available.')
RULES = ('This is a finite software QA experiment. Use only the supplied task/data; no tools, commands, files, '
         'skills, network or subagents. Return one JSON action, at most 220 words in free-text fields. '
         'Measure only the recorded source/observable; max_items <= 4. For a new diagnostic trace use diagnose '
         'and measurement_form=trace (retain item-level derivation, not just its scalar); changing an intent label '
         'alone does not create a new measurement. Use measurement_form=not_executed for a pure review request '
         'and request review if not independently authorized. Assume and test are distinct: assumes are required '
         'true premises, tests are assertions that the experiment may refute. A point witness cannot prove a '
         'universal assertion. In assumes and tests use ONLY exact statement_id identifiers from the supplied '
         'events, never sentences or paraphrases. If no named assumption is required, return assumes=[]. '
         'Put ordinary source-reading assumptions in reason, not in the ID lists. A point witness cannot prove a '
         'universal assertion. Copy exact source/scope/representation and obligation version when available. '
         'Do not invent IDs. Without data, use empty IDs, null versions, and requires_review=true. '
         'A freshness discrepancy requires refresh_required=true and deferral, not guessing an updated grant. '
         'Record independent inputs that remain available. Selection never authorizes execution. '
         'The enum fields describe the requested action, not its expected category or correctness.')


def schema():
    def obj(properties):
        return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}
    text = {'type': 'string'}
    strings = {'type': 'array', 'items': text}
    ints = {'type': 'array', 'items': {'type': 'integer'}}
    boolean = {'type': 'boolean'}
    return obj({'action': obj({
        'intent': {'type': 'string', 'enum': ['measure', 'diagnose', 'request_review', 'refresh']},
        'measurement_form': {'type': 'string', 'enum': ['scalar', 'trace', 'not_executed']},
        'source_id': text, 'source_version': {'type': ['integer', 'null']}, 'input_ids': strings,
        'observable': text, 'scope': text, 'mechanism': text, 'source_representation': text,
        'target_representation': text, 'obligation_id': {'type': ['integer', 'null']},
        'obligation_version': {'type': ['integer', 'null']}, 'parent_event_ids': ints,
        'evidence_refs': strings, 'considered_event_ids': ints,
        'assumes': {'type': 'array', 'items': {'type': 'string', 'description': 'Exact statement_id identifier from an event, not prose.'}},
        'tests': {'type': 'array', 'items': {'type': 'string', 'description': 'Exact statement_id identifier from an event, not prose.'}},
        'independent_inputs': strings, 'max_items': {'type': 'integer'},
        'falsification': obj({'input_id': text, 'operator': {'type': 'string', 'enum': ['eq', 'neq']},
                              'value': {'type': 'integer'}}),
        'reason': text, 'unknown_distinction': text, 'minimal_experiment': text,
        'requires_review': boolean, 'refresh_required': boolean, 'execution_requested': boolean,
        'truth_claimed': boolean, 'asserts_result': boolean,
        'claim_scope': {'type': 'string', 'enum': ['listed_inputs', 'all_source_inputs', 'undetermined']},
    })})


def flat(value, path='record'):
    """One scalar statement per line; retains empty containers and every JSON leaf."""
    if isinstance(value, dict) and value:
        return '\n'.join(flat(v, path + '.' + k) for k, v in value.items())
    if isinstance(value, list) and value:
        return '\n'.join(flat(v, path + '[' + str(i) + ']') for i, v in enumerate(value))
    return path + ': ' + json.dumps(value, ensure_ascii=False)


def make_prompt(data, mode):
    rendered = '[No historical data supplied.]' if mode == 'M0' else (
        flat(data) if mode == 'M1' else json.dumps(data, ensure_ascii=False, separators=(',', ':')))
    # Mode names, oracle labels, repeat/seed and expected choices are absent.
    prompt = RULES + '\nTASK: ' + TASK + '\nDATA:\n' + rendered + '\nEND DATA\n'
    count = len(ENCODING.encode(prompt))
    if count > INPUT_TOKENS - 10:
        raise ValueError('Precommitted input budget exceeded: ' + str(count))
    # Padding is identical neutral tokens, outside the untrusted research record.
    prompt += 'IGNORABLE PADDING:'
    prompt += ' x' * (INPUT_TOKENS - len(ENCODING.encode(prompt)))
    while len(ENCODING.encode(prompt)) < INPUT_TOKENS:
        prompt += ' x'
    if len(ENCODING.encode(prompt)) != INPUT_TOKENS:
        raise ValueError('Padding token boundary mismatch')
    return prompt


async def stop_process_group(process):
    if process.stdin is not None:
        process.stdin.close()
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass  # The group can exit between the deadline and the signal.
        try:
            await asyncio.wait_for(process.wait(), 5)
            return
        except asyncio.TimeoutError:
            continue
    raise RuntimeError('Unable to confirm that the timed-out inference process stopped')


async def infer(directory, prompt, semaphore):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    work = directory / 'empty-work'
    work.mkdir()
    (directory / 'prompt.txt').write_text(prompt)
    schema_path = directory / 'schema.json'
    schema_path.write_text(json.dumps(schema()))
    answer = directory / 'output.json'
    command = ['bwrap', '--bind', '/', '/', '--ro-bind', '/dev/null', str(Path.home() / '.codex/AGENTS.md'),
        '--chdir', str(work), 'codex', '--no-daemon', 'exec', '--ignore-user-config', '--ignore-rules',
        '--ephemeral', '--skip-git-repo-check', '--sandbox', 'read-only', '-m', MODEL,
        '-c', 'project_doc_max_bytes=0', '-c', 'features.apps=false', '-c', 'features.plugins=false',
        '-c', 'features.multi_agent=false', '-c', 'features.skill_search=false',
        '-c', 'model_reasoning_effort="low"', '--json', '--output-schema', str(schema_path), '-o', str(answer), '-']
    env = {k: v for k, v in os.environ.items() if k not in
           {'OPENAI_API_KEY', 'OPENAI_BASE_URL', 'ANTHROPIC_API_KEY', 'AZURE_OPENAI_API_KEY'}}
    async with semaphore:
        started = time.monotonic()
        with (directory / 'events.jsonl').open('w') as output, (directory / 'stderr.txt').open('w') as err:
            process = await asyncio.create_subprocess_exec(*command, stdin=asyncio.subprocess.PIPE,
                stdout=output, stderr=err, env=env, start_new_session=True)
            timeout = False
            try:
                await asyncio.wait_for(process.communicate(prompt.encode()), TIMEOUT)
            except asyncio.CancelledError:
                await stop_process_group(process)
                raise
            except asyncio.TimeoutError:
                timeout = True
                await stop_process_group(process)
        events = [json.loads(line) for line in (directory / 'events.jsonl').read_text().splitlines() if line.strip()]
        tool_events = [e for e in events if e.get('item', {}).get('type') not in {None, 'agent_message', 'reasoning'}]
        metadata = {'requested_model': MODEL, 'reasoning_effort': 'low', 'timeout_seconds': TIMEOUT,
            'wall_seconds': time.monotonic() - started, 'exit_code': process.returncode, 'timed_out': timeout,
            'tool_events': len(tool_events), 'estimated_user_input_tokens': len(ENCODING.encode(prompt)),
            'tokenizer': 'o200k_base', 'tokenizer_version': importlib.metadata.version('tiktoken'),
            'actual_usage': next((e.get('usage') for e in reversed(events) if e['type'] == 'turn.completed'), None),
            'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(), 'immutable_model_build': None,
            'output_budget': 'same schema and <=220 free-text words; no exposed service output-token cap',
            'remote_cpu_seconds': None, 'auth': 'existing ChatGPT subscription login, API-key environment removed'}
        result = {'outcome': 'OK', 'metadata': metadata}
        if timeout or process.returncode:
            result['outcome'] = 'TRANSPORT_FAILURE'
        elif tool_events:
            result['outcome'] = 'MODEL_FAILURE'
        else:
            try:
                result['output'] = json.loads(answer.read_text())
                jsonschema.validate(result['output'], schema())
                a = result['output']['action']
                if sum(len(a[k].split()) for k in ('reason', 'unknown_distinction', 'minimal_experiment')) > 220:
                    result['outcome'] = 'MODEL_FAILURE'
            except (ValueError, OSError, jsonschema.ValidationError) as error:
                result.update(outcome='MODEL_FAILURE', error=str(error))
        (directory / 'receipt.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        return result
