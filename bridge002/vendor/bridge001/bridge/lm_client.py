"""Real MCP read-only adapter. No operator, write, source-ingest or OAuth API."""
import json
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

import httpx
from jsonschema import Draft202012Validator
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .canonical import MAX_BYTES, Refusal, canonical_bytes, statuses

READ_ONLY_TOOLS = frozenset({'service_health', 'research_contract', 'research_context',
                             'research_normalize_preview', 'research_cycle_preview',
                             'research_native_preview', 'research_source_contract'})


class Wire:
    """Record JSON-RPC bodies only, never HTTP/OAuth headers or credentials."""
    def __init__(self, stream, path, direction):
        self.stream, self.path, self.direction = stream, path, direction

    def log(self, value):
        body = value.message.model_dump(mode='json', by_alias=True, exclude_none=True)
        with self.path.open('a') as f:
            f.write(json.dumps({'direction': self.direction, 'body': body}, ensure_ascii=False) + '\n')

    async def send(self, value):
        self.log(value)
        await self.stream.send(value)

    async def receive(self):
        value = await self.stream.receive()
        self.log(value)
        return value

    async def __aenter__(self):
        await self.stream.__aenter__()
        return self

    async def __aexit__(self, *args):
        return await self.stream.__aexit__(*args)

    def __aiter__(self):
        return self

    async def __anext__(self):
        import anyio
        try:
            return await self.receive()
        except anyio.EndOfStream:
            raise StopAsyncIteration

    def __getattr__(self, name):
        return getattr(self.stream, name)


class ReadOnlyClient:
    def __init__(self, session, catalog, projects, max_calls=12):
        if not projects or any(not p.startswith('BRIDGE_QA_') for p in projects):
            raise Refusal('BRIDGE_QA_PROJECT_SCOPE_REQUIRED')
        self.session = session
        self.catalog = {t['name']: t for t in catalog['tools']}
        self.projects = frozenset(projects)
        self.max_calls, self.calls = max_calls, []

    async def call(self, name: str, arguments: dict) -> dict:
        if name not in READ_ONLY_TOOLS:
            raise Refusal('READ_ONLY_BOUNDARY', name)
        tool = self.catalog.get(name)
        # The installed legacy tools omit annotations. Their reviewed RC020
        # implementations/contract establish read-only semantics; hints alone
        # are never an authorization boundary. Explicit non-read-only is denied.
        if tool is None or (tool.get('annotations') or {}).get('readOnlyHint') is False:
            raise Refusal('READ_ONLY_TOOL_NOT_NEGOTIATED', name)
        if len(self.calls) >= self.max_calls or len(canonical_bytes(arguments)) > MAX_BYTES:
            raise Refusal('MCP_BUDGET_EXCEEDED')
        schema = tool['inputSchema']
        def scope(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == 'project' and item not in self.projects:
                        raise Refusal('UNAUTHORIZED_PROJECT', str(item))
                    if key in ('source_event_ids', 'source_bindings') and item:
                        raise Refusal('UNREGISTERED_BRIDGE_SOURCE')
                    scope(item)
            elif isinstance(value, list):
                for item in value:
                    scope(item)
        scope(arguments)
        if name not in ('service_health', 'research_contract'):
            project = arguments.get('project') or arguments.get('request', {}).get('project')
            if project not in self.projects:
                raise Refusal('UNAUTHORIZED_PROJECT')
        def refs(value):
            if isinstance(value, dict):
                if '$ref' in value and not value['$ref'].startswith('#/'):
                    raise Refusal('REMOTE_SCHEMA_REFERENCE_DENIED')
                for v in value.values():
                    refs(v)
            elif isinstance(value, list):
                for v in value:
                    refs(v)
        refs(schema)
        errors = list(Draft202012Validator(schema).iter_errors(arguments))
        if errors:
            raise Refusal('MCP_ARGUMENT_SCHEMA_MISMATCH', errors[0].message)
        response = await self.session.call_tool(name, arguments)
        result = response.model_dump(mode='json')
        self.calls.append({'tool': name, 'arguments': arguments, 'response': result,
                           'read_only_basis': 'EXPLICIT_REVIEWED_RC020_ALLOWLIST',
                           'server_read_only_hint': (tool.get('annotations') or {}).get('readOnlyHint')})
        return result

    def native_preview(self, envelope: dict) -> dict:
        # Bridge manual contracts have no registered source-specific LM adapter.
        # Never substitute a mod5 fixture or invent frontier/evidence IDs.
        return {'status': 'UNSUPPORTED_SOURCE',
                'reason': 'No reviewed LivingMath source-specific lawful adapter or registered source event for this manual contract.',
                'source_id': envelope['source_id'], 'native_call_sent': False,
                **statuses(semantic='REQUIRES_SOURCE_ADAPTER', execution='REFUSED',
                           provenance={'source_hash': envelope['source_hash']})}


@asynccontextmanager
async def connect(endpoint, token_file, wire):
    parsed = urlparse(endpoint)
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise Refusal('HTTPS_ENDPOINT_REQUIRED')
    token_file = Path(token_file)
    if token_file.stat().st_mode & 0o077:
        raise Refusal('OAUTH_FILE_MUST_BE_PRIVATE')
    token = json.loads(token_file.read_text())['access_token']
    async with httpx.AsyncClient(verify=True, headers={'Authorization': 'Bearer ' + token}, timeout=35) as http:
        async with streamable_http_client(endpoint, http_client=http) as (read, write, _):
            async with ClientSession(Wire(read, wire, 'response'), Wire(write, wire, 'request')) as session:
                yield session


def payload(response: dict) -> dict:
    if response.get('structuredContent') is not None:
        return response['structuredContent']
    body = ''.join(x.get('text', '') for x in response.get('content', []) if x['type'] == 'text')
    try:
        return json.loads(body)
    except ValueError:
        return {'status': 'MCP_TOOL_ERROR' if response.get('isError') else 'UNSTRUCTURED', 'message': body}
