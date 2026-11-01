"""Cancellation/deadline enforcement without an unbounded worker."""
import asyncio
from deploy018_http import Bounds018


def test_request_timeout_cancels_worker_and_releases_slot():
    async def run():
        cancelled, messages = [], []
        async def slow(scope, receive, send):
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.append(True)
        async def receive():
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        async def send(message):
            messages.append(message)
        middleware = Bounds018(slow, request_timeout=0.01)
        await middleware({'type': 'http', 'path': '/mcp'}, receive, send)
        assert cancelled == [True] and middleware.active == 0
        assert messages[0]['status'] == 504
        assert b'018_REQUEST_DEADLINE' in messages[1]['body']
    asyncio.run(run())


def test_disconnected_body_never_dispatches_and_releases_slot():
    async def run():
        calls = []
        async def application(*args):
            calls.append(True)
        async def receive():
            return {'type': 'http.disconnect'}
        async def send(message):
            raise AssertionError('No response on disconnected transport')
        middleware = Bounds018(application)
        await middleware({'type': 'http', 'path': '/mcp'}, receive, send)
        assert not calls and middleware.active == 0
    asyncio.run(run())
