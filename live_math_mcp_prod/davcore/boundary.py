"""Async process boundary: bounded queue, concurrency, per-project rate and cancellation."""
import asyncio
from collections import deque
import os
from pathlib import Path
import sys
import time

from .ast import canonical


class Boundary:
    def __init__(self):
        self.semaphore = asyncio.Semaphore(2)
        self.calls: deque[float] = deque()
        self.running = set()

    async def run(self, request: dict):
        raw = canonical(request).encode()
        if len(raw) > 256000:
            raise ValueError('INPUT_BYTE_BOUND')
        now = time.monotonic()
        while self.calls and now - self.calls[0] >= 60:
            self.calls.popleft()
        if len(self.calls) >= 120:
            return {'status': 'timeout', 'reason': 'DAV_SERVER_RATE_LIMIT_120_PER_MINUTE'}
        self.calls.append(now)
        process = None
        try:
            async with asyncio.timeout(request['budget']['deadline_ms'] / 1000 + 1):
                async with self.semaphore:
                    process = await asyncio.create_subprocess_exec(
                        sys.executable, '-I', '-B', str(Path(__file__).with_name('worker.py')),
                        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                        cwd='/tmp', env={'PATH': os.defpath, 'LANG': 'C.UTF-8'}, start_new_session=True,
                        limit=2100000)
                    self.running.add(process.pid)
                    data, error = await process.communicate(raw)
                    if process.returncode != 0:
                        return {'status': 'timeout' if process.returncode is not None and process.returncode < 0 else 'unknown', 'reason': 'WORKER_EXIT',
                                'exit_code': process.returncode}
                    if len(data) > request['budget']['max_output_bytes']:
                        return {'status': 'timeout', 'reason': 'OUTPUT_BYTE_BOUND'}
                    import json
                    out = json.loads(data)
                    out['boundary_wall_ms'] = (time.monotonic() - now) * 1000
                    return out
        except TimeoutError:
            return {'status': 'timeout', 'reason': 'HARD_WALL_OR_QUEUE_TIMEOUT'}
        finally:
            if process is not None:
                if process.returncode is None:
                    process.kill()
                    await process.wait()
                self.running.discard(process.pid)
