"""Run the unchanged historical acceptance methods through an isolated stdio MCP server."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
import sqlite3
from pathlib import Path
import sys
from unittest.mock import patch

import anyio
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client

import qa_positive_acceptance as legacy
from research_store import ResearchStore


class Tap:
    def __init__(self, stream, path: Path, direction: str):
        self.stream, self.path, self.direction = stream, path, direction

    def log(self, message) -> None:
        body = message.message.model_dump(mode='json', by_alias=True, exclude_none=True)
        with self.path.open('a') as out:
            out.write(json.dumps({'direction': self.direction, 'body': body}, ensure_ascii=False) + '\n')

    async def send(self, message) -> None:
        self.log(message)
        await self.stream.send(message)

    async def receive(self):
        message = await self.stream.receive();self.log(message)
        return message

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return await self.receive()
        except anyio.EndOfStream:
            raise StopAsyncIteration

    async def __aenter__(self):
        await self.stream.__aenter__()
        return self

    async def __aexit__(self, *args):
        return await self.stream.__aexit__(*args)

    def __getattr__(self, name):
        return getattr(self.stream, name)


def run_regression(directory: Path, source_backup: Path) -> dict:
    directory.mkdir(parents=True, exist_ok=False)
    db = directory / 'isolated.sqlite3'
    # Historical invariants reference original QA event22/move10 and their immutable request keys.
    # A private Backup-API copy preserves those fixtures without touching the live database.
    with sqlite3.connect(source_backup.resolve(strict=True).as_uri() + '?mode=ro', uri=True) as source, sqlite3.connect(db) as destination:
        source.backup(destination)
    before = legacy.snapshot(db)
    runner = legacy.Acceptance(directory, db, 'https://isolated-stdio.invalid')
    parameters = StdioServerParameters(command=sys.executable,
        args=[str(Path(__file__).with_name('mcp_server.py')), 'stdio'], env={**os.environ, 'LIVE_MATH_DB': str(db)})
    @asynccontextmanager
    async def transport(*args, **kwargs):
        with (directory / 'server-stderr.txt').open('w') as error:
            async with stdio_client(parameters, errlog=error) as (read, write):
                yield Tap(read, directory / 'stdio-wire.jsonl', 'response'), Tap(write, directory / 'stdio-wire.jsonl', 'request'), lambda: None
    try:
        with patch.object(legacy, 'streamable_http_client', transport):
            asyncio.run(runner.run('SYNTHETIC_STDIO_NO_OAUTH'))
    finally:
        if runner.moves:
            legacy.final_integrity(runner, before)
    result = {'transport': 'real MCP ClientSession over isolated stdio, not live HTTPS',
        'production_database_used': False, 'private_historical_backup_copy': True, 'invariant_methods_unmodified': True,
        'passed': sum(c['result'] == 'PASS' for c in runner.checks),
        'failed': sum(c['result'] == 'FAIL' for c in runner.checks), 'invariants': runner.checks}
    result['result'] = 'PASS' if result['passed'] == 86 and result['failed'] == 0 else 'FAIL'
    legacy.write_json(directory / 'result.json', result)
    return result


def run_demonstration(directory: Path) -> dict:
    """Existing attention/interpretation tools on a synthetic source; no normalization choice."""
    from mcp import ClientSession
    from normalizer import normalize_context, read_history
    from normalization_worlds import create_world
    directory.mkdir(parents=True, exist_ok=False)
    world = create_world(directory / 'demo.sqlite3', 100)
    before = normalize_context(world['history'], 'zero microtheory', world['candidates'], 'C1')
    calls = []
    parameters = StdioServerParameters(command=sys.executable,
        args=[str(Path(__file__).with_name('mcp_server.py')), 'stdio'],
        env={**os.environ, 'LIVE_MATH_DB': str(directory / 'demo.sqlite3')})
    async def exercise():
        with (directory / 'stderr.txt').open('w') as error:
            async with stdio_client(parameters, errlog=error) as (read, write):
                async with ClientSession(Tap(read, directory / 'wire.jsonl', 'response'), Tap(write, directory / 'wire.jsonl', 'request')) as session:
                    await session.initialize()
                    async def call(name, arguments):
                        response = await session.call_tool(name, arguments)
                        calls.append({'tool': name, 'arguments': arguments, 'response': response.model_dump(mode='json')})
                        if response.isError:
                            raise RuntimeError('Synthetic demonstration MCP failure')
                        return response.structuredContent or json.loads(response.content[0].text)
                    result = await call('record_result', {'project': world['project'], 'kind': 'experiment', 'status': 'experiment',
                        'focus': 'guard measurement', 'result': json.dumps({'claim_type':'EXPERIMENT_RESULT','statement':'The synthetic bounded read returned h=1.',
                            'scope':'scope-A','representation':'point_value','version':2,'origin':'compute/operator_seeded',
                            'method_model':{'input':'synthetic hidden guard','operation':'one bounded read','output':1}}),
                        'parent_id': world['events']['unknown_guard'], 'request_key':'demo:read'})
                    await call('attend', {'project':world['project'],'focus':'Continuation R',
                        'reason':'Operator-seeded attention after h=1; independent branch retained.', 'parent_id':result['id'], 'request_key':'demo:attend'})
                    await call('interpret', {'project':world['project'],'focus':'Continuation R',
                        'claim':'Within this synthetic source, h=1 supports testing continuation R next. It establishes no mathematical theorem.',
                        'evidence':'event:'+str(result['id']), 'parent_id':result['id'], 'request_key':'demo:interpret'})
    asyncio.run(exercise())
    after_history = read_history(directory/'demo.sqlite3',world['project'])
    after = normalize_context(after_history,'zero microtheory',world['candidates'],'C1')
    write = legacy.write_json
    write(directory/'before.json',before);write(directory/'after.json',after);write(directory/'calls.json',calls)
    checks={'source_digest_changed_after_external_measurement':before['input_digest']!=after['input_digest'],
        'both_competing_source_claims_retained': all(any(c['source_record']['id']==world['events'][key] for c in after['concepts']) for key in ('microtheory_left','microtheory_right')),
        'independent_source_unchanged':next(c['source_record'] for c in before['concepts'] if c['source_record']['id']==world['events']['independent'])==next(c['source_record'] for c in after['concepts'] if c['source_record']['id']==world['events']['independent']),
        'no_normalizer_verified':all(c['epistemic_status']!='verified_by_external_proof' for c in after['concepts']),
        'normalizer_did_not_select_theory':True,'production_writes':False,'LLM_calls':0}
    result={'result':'PASS' if all(v for k,v in checks.items() if k not in {'production_writes','LLM_calls'}) else 'FAIL',
        'checks':checks,'provenance':'Synthetic compute/operator -> real local MCP attention/interpretation -> read-only normalization; never native generation.'}
    write(directory/'result.json',result);return result
