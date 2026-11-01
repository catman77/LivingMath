"""Execute the two installed workers with finite input/output and execution bounds."""
import asyncio
import json
import os
from pathlib import Path
import sys


async def run_worker(mode: str, payload: dict) -> dict:
    if mode not in {'propose', 'critique'}:
        raise ValueError('UNKNOWN_INSTALLED_WORKER')
    raw = json.dumps(payload, ensure_ascii=False).encode()
    if len(raw) > 64000:
        raise ValueError('WORKER_INPUT_BUDGET')
    proc = await asyncio.create_subprocess_exec(
        sys.executable, '-I', '-B', str(Path(__file__).with_name('worker.py')), mode,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        cwd='/tmp', env={'PATH': os.defpath, 'LANG': 'C.UTF-8'}, start_new_session=True)
    try:
        output, error = await asyncio.wait_for(proc.communicate(raw), timeout=6)
        if proc.returncode != 0 or len(output) > 256000:
            raise ValueError('ISOLATED_WORKER_FAILURE:' + error.decode(errors='replace')[-500:])
        result = json.loads(output)
        if result['isolation']['forbidden_modules_loaded']:
            raise ValueError('INDEPENDENT_CHANNEL_IMPORT_BREACH')
        return result
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
