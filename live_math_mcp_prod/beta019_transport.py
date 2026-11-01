"""Actual bounded private HTTPS/OAuth019 driver; no source predictions here."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import time
import httpx
from deploy018_transport import tls, oauth, client
from native_preview008_server import MeasuredProcess

SOURCE = Path(__file__).resolve().parent


@asynccontextmanager
async def serving(data, database, out, label, forbidden=(), enabled=True, port=None, fault_point=None, rate=1000):
    if not (data / 'tls').exists():
        tls(data / 'tls')
    cert, key, password = (data / 'tls' / name for name in ('ca.pem', 'tls-key.pem', 'owner-password'))
    context = ssl.create_default_context(cafile=str(cert))
    if port is None:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    origin = 'https://localhost:' + str(port)
    argv = [sys.executable, str(SOURCE / 'beta019_http.py'), '--data', str(data), '--typed', str(database),
        '--origin', origin, '--port', str(port), '--cert', str(cert), '--key', str(key), '--password', str(password), '--rate', str(rate)]
    if enabled:
        argv.append('--enable019')
    for p in forbidden:
        argv += ['--forbidden', str(p)]
    env = {**os.environ, 'LM014_NATIVE_LEDGER': str(data / 'native-I-T.jsonl')}
    env.pop('LM018_FAULT', None)
    if fault_point:
        env['LM018_FAULT'] = fault_point
    error = (out / (label + '-stderr.txt')).open('w')
    start = time.perf_counter_ns()
    process = MeasuredProcess(argv, env=env, stdout=error, stderr=error)
    try:
        async with httpx.AsyncClient(verify=context, timeout=0.5) as http:
            for _ in range(240):
                if process.poll() is not None:
                    raise RuntimeError('019_SERVER_EXIT:' + str(process.returncode) + ':' + label)
                try:
                    if (await http.get(origin + '/healthz')).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.05)
            else:
                raise RuntimeError('019_STARTUP_DEADLINE')
        tokens = await asyncio.to_thread(oauth, origin, context, password)
        yield origin, context, tokens, process
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, 5)
            except subprocess.TimeoutExpired:
                process.kill(); await asyncio.to_thread(process.wait)
        error.close()
        usage = process.child_usage
        with (out / 'http-processes.jsonl').open('a') as stream:
            stream.write(json.dumps({'label': label, 'pid': process.pid, 'exit_code': process.returncode,
                'wall_ns': time.perf_counter_ns() - start, 'CPU_ns': round((usage.ru_utime + usage.ru_stime) * 1e9),
                'peak_RSS_KiB': usage.ru_maxrss, 'beta_enabled': enabled}) + '\n')
