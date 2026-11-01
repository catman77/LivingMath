"""Explicit018 private TLS mount; original24-tool production factory untouched."""
import argparse
import asyncio
from collections import deque
import functools
import json
import os
from pathlib import Path
import resource
import time

from starlette.responses import JSONResponse
import uvicorn
from mcp.types import CallToolResult, TextContent
from mcp_server import create_server as legacy_server
from engine017_controller import EngineController017
from deploy018_authority import template, ReceiptValidator018
from deploy018_storage import private_path, fault

CONTRACT = {'version': '018.1', 'protocol': 'livingmath-http018/v1', 'engine': '017.1',
    'deployment': 'PRIVATE_STAGING', 'old_contract': 'legacy/v1 default factory unchanged',
    'model_authority': ['read', 'proposal', 'precommit', 'validate'],
    'operator_only': ['activate_experiment', 'complete', 'execute', 'commit', 'register_source'],
    'legacy_change': '018 opt-in HTTP policy denies model activation/completion for ALL projects',
    'lease': 'one-shot nonce; maximum900s; restart revokes outstanding grants',
    'proof_status': 'unverified', 'physical_authenticity': 'NOT_CLAIMED'}


class Controller018(EngineController017):
    def precommit(self, request, request_key):
        fault('http_precommit_before')
        result = super().precommit(request, request_key)
        fault('http_precommit_after')
        return result

    def validate_in(self, c, project, move_id, event_id):
        return ReceiptValidator018(self.database).validate_in(c, project, move_id, event_id)

    def history(self, project):
        from deploy018_authority import lease_in
        from typed_cycle011_store import connect
        history = super().history(project)
        with connect(self.database) as c:
            for move in history['moves']:
                if move['execution_permission']['allowed']:
                    try:
                        lease_in(c, project, move['id'])
                    except ValueError as error:
                        move['execution_permission'] = {'allowed': False, 'needs_reaudit': True, 'reason': str(error)}
        return history


class Bounds018:
    def __init__(self, app, max_body=262144, concurrency=8, rate=1000, window=60,
                 body_timeout=2, request_timeout=30):
        self.app, self.max_body, self.concurrency = app, max_body, concurrency
        self.rate, self.window, self.body_timeout, self.request_timeout = rate, window, body_timeout, request_timeout
        self.active, self.arrivals = 0, deque(maxlen=rate)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['path'] == '/healthz':
            return await self.app(scope, receive, send)
        now = time.monotonic()
        while self.arrivals and self.arrivals[0] <= now - self.window:
            self.arrivals.popleft()
        if self.active >= self.concurrency or len(self.arrivals) >= self.rate:
            return await JSONResponse({'error': {'code': '018_RESOURCE_BUSY', 'retryable': True}}, 429)(scope, receive, send)
        self.arrivals.append(now)
        self.active += 1
        started = False
        async def checked_send(message):
            nonlocal started
            if message['type'] == 'http.response.start':
                started = True
            await send(message)
        try:
            body = b''
            try:
                async with asyncio.timeout(self.body_timeout):
                    while True:
                        message = await receive()
                        if message['type'] == 'http.disconnect':
                            return
                        body += message.get('body', b'')
                        if len(body) > self.max_body:
                            return await JSONResponse({'error': {'code': '018_PAYLOAD_TOO_LARGE'}}, 413)(scope, receive, send)
                        if not message.get('more_body'):
                            break
            except TimeoutError:
                return await JSONResponse({'error': {'code': '018_BODY_DEADLINE'}}, 408)(scope, receive, send)
            delivered = False
            async def buffered():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {'type': 'http.request', 'body': body, 'more_body': False}
                return await receive()
            async with asyncio.timeout(self.request_timeout):
                await self.app(scope, buffered, checked_send)
        except TimeoutError:
            if not started:
                await JSONResponse({'error': {'code': '018_REQUEST_DEADLINE', 'retryable': True}}, 504)(scope, receive, send)
        finally:
            self.active -= 1


def create_app(origin: str, data_dir: Path, typed_database: Path, password: str,
               enabled: bool = False, bounds: dict | None = None):
    private_path(data_dir / 'research.sqlite3')
    private_path(typed_database)
    # Fresh module objects avoid changing globals of the deployed entrypoint.
    http = template('http_server')

    def factory(store, **settings):
        if not enabled:
            return legacy_server(store, **settings)
        mount = template('engine017_server')
        mount.base_server = functools.partial(legacy_server, **settings)
        mount.EngineController017 = Controller018
        server = mount.create_server(store.path, typed_database, enabled=True)
        tool = server._tool_manager.get_tool('transition_research_move')
        old = tool.fn
        @functools.wraps(old)
        def transition(*args, **kwargs):
            if kwargs.get('action') in ('activate_experiment', 'complete'):
                denied = {'status': 'DENIED', 'error': {'code': '018_OPERATOR_AUTHORITY_REQUIRED'},
                    'protocol': CONTRACT['protocol'], 'execution_permission': {'allowed': False}}
                return CallToolResult(isError=True, structuredContent=denied,
                    content=[TextContent(type='text', text=json.dumps(denied))])
            return old(*args, **kwargs)
        tool.fn = transition
        contract_tool = server._tool_manager.get_tool('research_contract')
        original = contract_tool.fn
        @functools.wraps(original)
        def contract(*args, **kwargs):
            return {**original(*args, **kwargs), 'http018': CONTRACT}
        contract_tool.fn = contract
        return server

    http.create_server = factory
    app = http.create_app(origin, data_dir, password)
    return Bounds018(app, **(bounds or {})) if enabled else app


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--typed', type=Path, required=True)
    parser.add_argument('--origin', required=True)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--cert', type=Path, required=True)
    parser.add_argument('--key', type=Path, required=True)
    parser.add_argument('--password', type=Path, required=True)
    parser.add_argument('--enable018', action='store_true')
    parser.add_argument('--forbidden', type=Path, action='append', default=[])
    parser.add_argument('--rate', type=int, default=1000)
    parser.add_argument('--window', type=float, default=60)
    args = parser.parse_args()
    os.umask(0o077)
    os.environ['LIVE_MATH_NATIVE_PREVIEW'] = '1'
    os.environ['LIVE_MATH_TYPED_CYCLE_DB'] = str(args.typed)
    if not 1 <= args.rate <= 1000 or not 0.1 <= args.window <= 60:
        parser.error('018 rate must be1..1000 and window0.1..60 seconds')
    app = create_app(args.origin, args.data, args.typed, args.password.read_text().strip(), args.enable018,
        {'rate': args.rate, 'window': args.window})
    if args.enable018:
        import sys
        import typed_cycle011_public  # legacy contract's lazy public dependency
        from law_validation014_isolation import restrict_reads
        for name in ('engine017_executor', 'engine017_operator', 'law_validation014_oracle'):
            if name in sys.modules:
                raise RuntimeError('AUTHORITY_MODULE_PRELOADED:' + name)
        evidence = restrict_reads(args.data, args.forbidden)
        (args.data / 'engine017-isolation.json').write_text(json.dumps(evidence, indent=2) + '\n')
    resource.setrlimit(resource.RLIMIT_AS, (1073741824, 1073741824))
    resource.setrlimit(resource.RLIMIT_CPU, (90, 90))
    uvicorn.run(app, host='127.0.0.1', port=args.port, ssl_certfile=str(args.cert), ssl_keyfile=str(args.key),
                access_log=False, proxy_headers=False, limit_concurrency=32, timeout_keep_alive=2)
