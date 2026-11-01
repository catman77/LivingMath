"""Actual MCP stdio wire transport with wait4 through whole server-process exit."""
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import anyio
from mcp import types
from mcp.shared.message import SessionMessage
from native_preview008_server import MeasuredProcess


@asynccontextmanager
async def measured_stdio(database: Path, output: Path):
    output.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).with_name('mcp_server.py')
    started = time.perf_counter_ns()
    error = (output / 'server-stderr.txt').open('w')
    process = MeasuredProcess([sys.executable, str(source), 'stdio'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=error, env={**os.environ, 'LIVE_MATH_DB': str(database), 'LIVE_MATH_NATIVE_PREVIEW': '1'}, start_new_session=True)
    read_send, read_receive = anyio.create_memory_object_stream(0)
    write_send, write_receive = anyio.create_memory_object_stream(0)

    def log(direction, body):
        with (output / 'wire.jsonl').open('a') as stream:
            stream.write(json.dumps({'direction': direction, 'body': body}, ensure_ascii=False) + '\n')

    async def reader():
        async with read_send:
            while True:
                line = await anyio.to_thread.run_sync(process.stdout.readline)
                if not line:
                    break
                message = types.JSONRPCMessage.model_validate_json(line)
                log('response', message.model_dump(mode='json', by_alias=True, exclude_none=True))
                try:
                    await read_send.send(SessionMessage(message))
                except (anyio.BrokenResourceError, anyio.ClosedResourceError):
                    break

    async def writer():
        async with write_receive:
            async for value in write_receive:
                message = value.message
                log('request', message.model_dump(mode='json', by_alias=True, exclude_none=True))
                data = (message.model_dump_json(by_alias=True, exclude_none=True) + '\n').encode()
                await anyio.to_thread.run_sync(process.stdin.write, data)
                await anyio.to_thread.run_sync(process.stdin.flush)

    try:
        async with anyio.create_task_group() as group:
            group.start_soon(reader); group.start_soon(writer)
            try:
                yield read_receive, write_send
            finally:
                process.stdin.close()
                try:
                    await anyio.to_thread.run_sync(lambda: process.wait(timeout=5))
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    await anyio.to_thread.run_sync(process.wait)
                group.cancel_scope.cancel()
    finally:
        error.close()
        usage = process.child_usage
        receipt = {'pid': process.pid, 'returncode': process.returncode, 'wall_ns': time.perf_counter_ns() - started,
            'CPU_method': 'OS wait4 through exit; includes waited-for descendants on this Linux kernel. Child preview CPU is a subset, not summed again.',
            'CPU_ns_inclusive_descendants': round((usage.ru_utime + usage.ru_stime) * 1e9) if usage else None,
            'peak_rss_KiB': usage.ru_maxrss if usage else None}
        (output / 'server-exit-usage.json').write_text(json.dumps(receipt, indent=2) + '\n')
        process.stdout.close()
        await read_receive.aclose(); await write_send.aclose()
