"""Bounded isolated source-only subprocesses; no provider/API calls."""
import asyncio
import json
import os
from pathlib import Path
import sys


async def run_worker(name: str,payload: dict) -> dict:
    if name not in {'worker','postcheck'}:raise ValueError('UNKNOWN_INSTALLED_WORKER')
    raw=json.dumps(payload,ensure_ascii=False).encode()
    if len(raw)>64000:raise ValueError('SOURCE_WORKER_INPUT_BOUND')
    p=await asyncio.create_subprocess_exec(sys.executable,'-I','-B',str(Path(__file__).with_name(name+'.py')),
        stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,
        cwd='/tmp',env={'PATH':os.defpath,'LANG':'C.UTF-8'},start_new_session=True)
    try:
        data,error=await asyncio.wait_for(p.communicate(raw),timeout=6)
        if p.returncode!=0 or len(data)>256000:raise ValueError('SOURCE_WORKER_FAILURE:'+error.decode(errors='replace')[-300:])
        return json.loads(data)
    finally:
        if p.returncode is None:p.kill();await p.wait()
