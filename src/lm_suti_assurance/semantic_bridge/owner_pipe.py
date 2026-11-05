"""Owner-started proposer pipe, following the accepted inference011 isolation pattern.

No credentials enter HTTP. Only pinned source/frame data and an untrusted JSON
proposal cross this bounded pipe; no caller-selected command, path or model.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

MAX_BYTES=2*1024*1024


class HostedPipe:
    def __init__(self,spool):
        spool=Path(spool);spool.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.stderr=(spool/'backend.private.log').open('ab')
        self.process=subprocess.Popen([sys.executable,'-I','-B',str(Path(__file__).resolve()),'--spool',str(spool)],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.stderr)
        self.lock=asyncio.Lock();self.last_status='NOT_YET_CALLED'

    async def generate(self,project,source,edition,phase,parent,challenge,request_key):
        value={'project':project,'source':source,'edition':edition,'phase':phase,'parent':parent,
               'challenge':challenge,'request_key':request_key}
        raw=json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()+b'\n'
        if len(raw)>MAX_BYTES:return {'status':'MODEL_UNAVAILABLE','reason_code':'PROPOSER_INPUT_BOUND'}
        async with self.lock:
            def exchange():
                if self.process.poll() is not None:raise ValueError('OWNER_PROPOSER_PIPE_CLOSED')
                self.process.stdin.write(raw);self.process.stdin.flush()
                response=self.process.stdout.readline(MAX_BYTES+1)
                if not response or len(response)>MAX_BYTES:raise ValueError('OWNER_PROPOSER_RESPONSE_BOUND')
                return json.loads(response)
            try:result=await asyncio.to_thread(exchange)
            except (OSError,ValueError):result={'status':'MODEL_UNAVAILABLE','reason_code':'OWNER_PROPOSER_PIPE_UNAVAILABLE'}
            self.last_status=result.get('receipt',result)['status'];return result

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:self.process.terminate();self.process.wait(timeout=5)
        self.stderr.close()


def main(spool):
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
    from lm_suti_assurance.core import digest
    from lm_suti_assurance.validation import parse
    from lm_suti_assurance.workspace import SLUG
    from lm_suti_assurance.semantic_bridge.proposer import generate
    os.umask(0o077)
    while True:
        raw=sys.stdin.buffer.readline(MAX_BYTES+1)
        if not raw:return
        try:
            if len(raw)>MAX_BYTES or not raw.endswith(b'\n'):raise ValueError('OWNER_PIPE_INPUT_BOUND')
            v=parse(raw.decode());expected={'project','source','edition','phase','parent','challenge','request_key'}
            if not isinstance(v,dict) or set(v)!=expected or not SLUG.fullmatch(v['project']):raise ValueError('OWNER_PIPE_CONTRACT')
            if v['phase'] not in ('initial','revise'):raise ValueError('OWNER_PIPE_PHASE')
            project_spool=Path(spool)/digest(v['project'])
            attempts=project_spool/'MODEL_ATTEMPTS.jsonl'
            before=len(attempts.read_text().splitlines()) if attempts.exists() else 0
            receipt=generate(v['source'],v['edition'],v['phase'],v['parent'],v['challenge'],project_spool,v['project']+':'+v['request_key'])
            after=len(attempts.read_text().splitlines()) if attempts.exists() else 0
            result={'receipt':receipt,'model_attempt_created':after>before}
        except Exception as exc:
            result={'status':'MODEL_UNAVAILABLE','reason_code':getattr(exc,'code',type(exc).__name__)}
        output=json.dumps(result,ensure_ascii=False,separators=(',',':')).encode()
        if len(output)>MAX_BYTES:output=b'{"status":"MODEL_UNAVAILABLE","reason_code":"PROPOSER_RECEIPT_BOUND"}'
        sys.stdout.buffer.write(output+b'\n');sys.stdout.buffer.flush()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--spool',type=Path,required=True);main(p.parse_args().spool)
