"""QA-only bounded retry of the server's pre-execution018_RESOURCE_BUSY guard."""

import asyncio, json, time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
import httpx


class ResourceRetryTransport(httpx.AsyncBaseTransport):
    def __init__(self, inner, log=None, sleep=asyncio.sleep):
        self.inner, self.log, self.sleep = inner, log, sleep

    async def handle_async_request(self, request):
        body = await request.aread()
        for attempt in range(13):
            retry = httpx.Request(
                request.method,
                request.url,
                headers=request.headers,
                content=body,
                extensions=request.extensions,
            )
            response = await self.inner.handle_async_request(retry)
            if response.status_code != 429 or attempt == 12:
                return response
            raw = await response.aread()
            try:
                payload = json.loads(raw)
            except ValueError:
                return response
            if (
                payload.get("error", {}).get("code") != "018_RESOURCE_BUSY"
                or payload["error"].get("retryable") is not True
            ):
                return response
            await response.aclose()
            delay = 60.0
            header = response.headers.get("Retry-After")
            if header:
                try:
                    delay = max(0.1, float(header))
                except ValueError:
                    try:
                        delay = max(
                            0.1,
                            (
                                parsedate_to_datetime(header)
                                - datetime.now(timezone.utc)
                            ).total_seconds(),
                        )
                    except (ValueError, TypeError):
                        pass
            if self.log:
                with self.log.open("a") as f:
                    f.write(
                        json.dumps(
                            {
                                "utc": datetime.now(timezone.utc).isoformat(),
                                "status": 429,
                                "code": "018_RESOURCE_BUSY",
                                "attempt": attempt + 1,
                                "delay_s": delay,
                                "method": request.method,
                                "path": request.url.path,
                                "same_request_body": True,
                            }
                        )
                        + "\n"
                    )
            # Long waits stay interruptible and do not issue early retries.
            while delay > 0:
                chunk = min(delay, 30)
                await self.sleep(chunk)
                delay -= chunk
        raise AssertionError("unreachable")

    async def aclose(self):
        await self.inner.aclose()


def install(client, log):
    """Wrap the client's already-selected HTTP/proxy transports, preserving routing."""
    client._transport = ResourceRetryTransport(client._transport, log)
    client._mounts = {
        key: ResourceRetryTransport(value, log) if value is not None else None
        for key, value in client._mounts.items()
    }
