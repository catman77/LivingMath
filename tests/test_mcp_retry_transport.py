"""Retries preserve the exact request and only handle the pre-execution guard."""

import asyncio, importlib.util
from pathlib import Path
import httpx

spec = importlib.util.spec_from_file_location(
    "retry_helper", Path(__file__).parents[1] / "tools/mcp_retry_transport.py"
)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def test_preexecution_retry_preserves_body_and_waits():
    async def run():
        requests = []
        waits = []

        async def handler(r):
            requests.append(await r.aread())
            return (
                httpx.Response(
                    429,
                    headers={"Retry-After": "2"},
                    json={"error": {"code": "018_RESOURCE_BUSY", "retryable": True}},
                )
                if len(requests) == 1
                else httpx.Response(200, json={"ok": True})
            )

        async def sleep(n):
            waits.append(n)

        async with httpx.AsyncClient(
            transport=helper.ResourceRetryTransport(
                httpx.MockTransport(handler), sleep=sleep
            )
        ) as c:
            r = await c.post(
                "https://example.test/mcp",
                json={"request_key": "stable", "payload": "unchanged"},
            )
        assert (
            r.status_code == 200
            and len(requests) == 2
            and requests[0] == requests[1]
            and waits == [2]
        )

    asyncio.run(run())


def test_unrelated_429_is_not_retried():
    async def run():
        count = 0

        async def handler(r):
            nonlocal count
            count += 1
            return httpx.Response(429, json={"error": {"code": "OTHER"}})

        async with httpx.AsyncClient(
            transport=helper.ResourceRetryTransport(httpx.MockTransport(handler))
        ) as c:
            r = await c.post("https://example.test/mcp", json={"request_key": "stable"})
        assert r.status_code == 429 and count == 1

    asyncio.run(run())
