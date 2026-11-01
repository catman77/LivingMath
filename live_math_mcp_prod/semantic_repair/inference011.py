"""Owner-started inference subprocess pipe; no credentials in the MCP process.

This is a bounded model backend, not a second research engine or an MCP tool.
Start before the existing service read boundary closes. Only source annotation
requests cross its pipe; mathematical workers keep their original limits.
"""
import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from artifact_genesis.contract import RawPacket
from davcore.ast import digest

from semantic_repair import prompts011, prompts012, prompts013, prompts014
from semantic_repair.meaning014_contract import SourceProposals014, SourceReview014
from semantic_repair.relations011 import (
    SourceProposals,
    SourceReview,
    decode_proposals,
    strict_response_schema,
)
from semantic_repair.relations012 import (
    SourceProposals012,
    SourceReview012,
    decode_proposals012,
)
from semantic_repair.relations013 import SourceProposals013, SourceReview013

MODEL = 'gpt-6.1-sol'
MAX_WALL = 120
MAX_REQUEST = 64000
MAX_RESPONSE = 256000


def canonical_packet(packet: dict) -> tuple[dict, dict[str, str]]:
    """LLM annotations can be reused; project/source authority cannot."""
    raw = RawPacket.model_validate(packet)
    name = 'source_' + raw.document_sha256[:24]
    mapping = {}
    def span(s):
        ref = name + ':' + str(s.start) + ':' + str(s.end)
        mapping[ref] = s.id
        return {**s.model_dump(), 'id': ref, 'document_id': name,
                'source_address': {'byte_start': s.start, 'byte_end': s.end}}
    spans = [span(s) for s in raw.spans]
    context = [span(s) for s in raw.context]
    result = {**raw.model_dump(), 'id': name + ':window:' + str(raw.spans[0].start),
              'document_id': name, 'spans': spans, 'context': context}
    return result, mapping


class SubscriptionInference:
    """The owner chooses the backend before creating the HTTP application."""
    assurance = 'REAL_LLM_SOURCE_PROPOSER'
    def __init__(self, spool: Path, *, model: str = MODEL):
        if not model or len(model) > 100:
            raise ValueError('PINNED_INFERENCE_MODEL_REQUIRED')
        self.model = model
        self.last_status = 'NOT_YET_CALLED'
        self.fingerprint = digest({'version': 'subscription-source011/1', 'model': model,
            'instructions': prompts011.INSTRUCTIONS, 'proposer': prompts011.PROPOSE,
            'critic': prompts011.CRITIC, 'schema': strict_response_schema(SourceProposals),
            'critic_schema': strict_response_schema(SourceReview), 'wall_s': MAX_WALL,
            'observer012': [prompts012.PROPOSE, prompts012.CRITIC,
                strict_response_schema(SourceProposals012), strict_response_schema(SourceReview012)],
            'observer013': [prompts013.PROPOSE, prompts013.CRITIC,
                strict_response_schema(SourceProposals013), strict_response_schema(SourceReview013)],
            'meaning014': [prompts014.PROPOSE, prompts014.CRITIC, strict_response_schema(SourceProposals014), strict_response_schema(SourceReview014)],
            'implementation': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
        spool = Path(spool).resolve()
        spool.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.spool = spool
        self.process = subprocess.Popen([sys.executable, '-I', '-B', str(Path(__file__)),
            '--owner-pipe', str(spool), '--model', model], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=(spool/'backend-stderr.log').open('ab'))
        self.lock = asyncio.Lock()

    async def infer(self, role: str, packet: dict, proposals=None, feedback=None) -> dict:
        canonical, _ = canonical_packet(packet)
        value = {'role': role, 'packet': canonical, 'proposals': proposals, 'feedback': feedback}
        raw = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode() + b'\n'
        if len(raw) > MAX_REQUEST:
            return {'status': 'ERROR', 'reason': 'INFERENCE_INPUT_BOUND', 'model': self.model}
        queued_at = time.monotonic()
        async with self.lock:
            queue_s = time.monotonic() - queued_at
            def exchange():
                if self.process.poll() is not None:
                    raise ValueError('OWNER_MODEL_PIPE_UNAVAILABLE')
                assert self.process.stdin is not None and self.process.stdout is not None
                self.process.stdin.write(raw)
                self.process.stdin.flush()
                data = self.process.stdout.readline(MAX_RESPONSE + 1)
                if not data or len(data) > MAX_RESPONSE:
                    raise ValueError('MODEL_RESPONSE_BOUND_OR_PIPE_CLOSED')
                return json.loads(data)
            result = await asyncio.wait_for(asyncio.to_thread(exchange), MAX_WALL + 15)
            if role.endswith('014'): result = {**result, 'queue_wait_s': queue_s, 'source_pipe_return_UTC': datetime.now(UTC).isoformat()}
            self.last_status = result['status']
            return result

    def close(self):
        if self.process.poll() is None:
            assert self.process.stdin is not None
            self.process.stdin.close()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=5)


def run_inference(value: dict, spool: Path, model: str) -> dict:
    if set(value) != {'role', 'packet', 'proposals', 'feedback'}:
        raise ValueError('STRICT_SOURCE_INFERENCE_REQUEST_REQUIRED')
    role = value['role']
    packet = RawPacket.model_validate(value['packet']).model_dump()
    if role not in {'proposer', 'critic', 'direct', 'neutral_repair',
                    'proposer012', 'critic012', 'direct012', 'neutral_repair012',
                    'proposer013', 'critic013', 'direct013', 'neutral_repair013',
                    'proposer014', 'critic014', 'direct014', 'repair014'}:
        raise ValueError('UNREGISTERED_SOURCE_INFERENCE_ROLE')
    proposals = value['proposals']
    if proposals is not None:
        proposals = (SourceProposals014 if role.endswith('014') else SourceProposals013 if role.endswith('013') else SourceProposals012 if role.endswith('012') else SourceProposals).model_validate(proposals).model_dump()
    if role in {'critic', 'critic012', 'critic013', 'critic014'} and proposals is None:
        raise ValueError('SOURCE_CRITIC_CANDIDATES_REQUIRED')
    prompts = prompts014 if role.endswith('014') else prompts013 if role.endswith('013') else prompts012 if role.endswith('012') else prompts011
    prompt = prompts.request(role, packet, proposals, value['feedback'])
    response_model = (SourceReview014 if role == 'critic014' else SourceProposals014) if role.endswith('014') else (SourceReview013 if role == 'critic013' else SourceProposals013) if role.endswith('013') else (SourceReview012 if role == 'critic012' else SourceProposals012) if role.endswith('012') else (SourceReview if role == 'critic' else SourceProposals)
    schema = strict_response_schema(response_model)
    key = digest({'decoder': 'meaning014/1' if role.endswith('014') else 'addressed-values013/1' if role.endswith('013') else 'addressed-partials012/1' if role.endswith('012') else 'addressed-partials011/2', 'model': model, 'prompt': prompt, 'schema': schema,
                  'instructions': prompts011.INSTRUCTIONS})
    directory = spool / key
    receipt_path = directory / 'receipt.json'
    if receipt_path.exists():
        cached = json.loads(receipt_path.read_text())
        return {**cached, 'cache_hit': True, 'requested_role': role}
    directory.mkdir(mode=0o700, exist_ok=False)
    cwd = directory / 'empty-cwd'
    cwd.mkdir(mode=0o700)
    (directory/'instructions.txt').write_text(prompts011.INSTRUCTIONS)
    (directory/'schema.json').write_text(json.dumps(schema))
    (directory/'prompt.json').write_text(prompt)
    command = ['codex', 'exec', '--ignore-user-config', '--ignore-rules', '--ephemeral',
        '--skip-git-repo-check', '--sandbox', 'read-only', '-C', str(cwd), '-m', model,
        '-c', 'model_reasoning_effort="medium"', '-c', 'web_search="disabled"',
        '-c', 'project_doc_max_bytes=0',
        '-c', 'model_instructions_file=' + json.dumps(str(directory/'instructions.txt'))]
    for feature in ['shell_tool', 'apps', 'plugins', 'skill_search', 'multi_agent',
                    'browser_use', 'computer_use', 'code_mode', 'view_image', 'sleep_tool']:
        command += ['-c', 'features.' + feature + '=false']
    command += ['-c', 'features.skip_host_skill_discovery=true', '--json',
        '--output-schema', str(directory/'schema.json'), '-o', str(directory/'answer.json'), '-']
    env = {k: v for k, v in os.environ.items() if k not in {
        'CODEX_THREAD_ID', 'CODEX_SESSION_ID', 'CODEX_TOOL_CALL_ID', 'OPENAI_API_KEY', 'CODEX_API_KEY'}}
    started = time.monotonic()
    started_UTC = datetime.now(UTC).isoformat()
    reason = None
    with (directory/'events.jsonl').open('w') as log, (directory/'stderr.log').open('w') as err:
        try:
            process = subprocess.run(command, input=prompt, text=True, env=env,
                stdout=log, stderr=err, timeout=MAX_WALL, check=False)
            if process.returncode:
                reason = 'MODEL_CLI_EXIT_' + str(process.returncode)
        except subprocess.TimeoutExpired:
            reason = 'MODEL_CALL_WALL_BOUND'
    events = []
    for line in (directory/'events.jsonl').read_text().splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            reason = reason or 'MODEL_EVENT_NOT_JSON'
    forbidden = [e for e in events if e.get('item', {}).get('type') not in {
        None, 'agent_message', 'reasoning', 'error'}]
    if forbidden:
        reason = 'MODEL_USED_UNAUTHORIZED_TOOL'
    usage = next((e['usage'] for e in reversed(events) if e.get('type') == 'turn.completed'), None)
    output = None
    decoding_losses: list[dict] = []
    preserved_A0 = None
    if reason is None:
        try:
            raw_output = json.loads((directory/'answer.json').read_text())
            if role.endswith('014') and isinstance(raw_output, dict):
                candidate = raw_output.get('readable_model')
                if isinstance(candidate,str) and 0 < len(candidate) <= 12000: preserved_A0 = candidate
            if role in {'critic', 'critic012', 'critic013', 'critic014'}:
                output = response_model.model_validate(raw_output).model_dump()
            elif role.endswith('014'):
                output = SourceProposals014.model_validate(raw_output).model_dump()
            elif role.endswith('013'):
                output = SourceProposals013.model_validate(raw_output).model_dump()
            elif role.endswith('012'):
                decoded, decoding_losses = decode_proposals012(raw_output)
                output = decoded.model_dump()
            else:
                decoded011, decoding_losses = decode_proposals(raw_output)
                output = decoded011.model_dump()
        except (ValueError, OSError) as exc:
            reason = 'INVALID_MODEL_ANNOTATION:' + str(exc)[:1000]
    receipt = {'status': 'OK' if reason is None else 'ERROR', 'reason': reason,
        'output': output, 'decoding_losses': decoding_losses,
        'raw_output_sha256': hashlib.sha256((directory/'answer.json').read_bytes()).hexdigest() if (directory/'answer.json').exists() else None,
        'model': model, 'requested_role': role, 'request_sha256': key,
        'prompt': prompt, 'instructions': prompts011.INSTRUCTIONS, 'response_schema': schema,
        'events': events, 'usage': usage, 'latency_s': time.monotonic() - started,
        'authentication': 'EXISTING_CHATGPT_CODEX_LOGIN_NO_API_KEY', 'cache_hit': False,
        'CLI_version': subprocess.check_output(['codex', '--version'], text=True).strip(),
        'hosted_model_revision': 'NOT_EXPOSED_BY_CLI; requested model alias is pinned',
        'developer_cost_USD': None, 'cost_assurance': 'Usage tokens measured; subscription billing attribution not returned by CLI',
        'tools_used': len(forbidden), 'raw_source_only': True,
        'semantic_status': 'HYPOTHESIS_NOT_ORACLE'}
    if role.endswith('014'):
        receipt.update(preserved_readable_A0=preserved_A0,started_UTC=started_UTC,completed_UTC=datetime.now(UTC).isoformat())
    raw = json.dumps(receipt, ensure_ascii=False)
    if len(raw.encode()) > MAX_RESPONSE:
        receipt = {**receipt, 'events': [], 'status': 'ERROR', 'reason': 'MODEL_RECEIPT_OUTPUT_BOUND'}
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    return receipt


def owner_pipe(spool: Path, model: str):
    os.umask(0o077)
    while True:
        raw = sys.stdin.buffer.readline(MAX_REQUEST + 1)
        if not raw:
            return
        try:
            if len(raw) > MAX_REQUEST or not raw.endswith(b'\n'):
                raise ValueError('BOUNDED_SOURCE_REQUEST_LINE_REQUIRED')
            result = run_inference(json.loads(raw), spool, model)
        except Exception as exc:  # noqa: BLE001 - owner pipe must return a bounded ERROR for every failed model request
            result = {'status': 'ERROR', 'reason': type(exc).__name__ + ':' + str(exc)[:1000], 'model': model}
        sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n')
        sys.stdout.flush()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--owner-pipe', type=Path, required=True)
    parser.add_argument('--model', default=MODEL)
    options = parser.parse_args()
    owner_pipe(options.owner_pipe, options.model)
