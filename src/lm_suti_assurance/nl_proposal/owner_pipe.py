"""Start before server isolation; HTTP never receives provider credentials."""
import asyncio,json,subprocess,sys,os
from pathlib import Path
MAX=4*1024*1024

class HostedProvider:
    def __init__(self,spool):
        spool=Path(spool);spool.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.stderr=(spool/'owner.private.log').open('ab')
        self.process=subprocess.Popen([sys.executable,'-I','-B',str(Path(__file__).resolve()),'--spool',str(spool)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.stderr)
        self.lock=asyncio.Lock()
    async def generate(self,request):
        async with self.lock:
            def exchange():
                raw=json.dumps(request,ensure_ascii=False,separators=(',',':')).encode()+b'\n'
                if len(raw)>262144:raise ValueError('PROVIDER_INPUT_BOUND')
                self.process.stdin.write(raw);self.process.stdin.flush();answer=self.process.stdout.readline(MAX+1)
                if not answer or len(answer)>MAX:raise ValueError('PROVIDER_RECEIPT_BOUND')
                return json.loads(answer)
            return await asyncio.to_thread(exchange)
    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:self.process.terminate();self.process.wait(timeout=5)
        self.stderr.close()

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--spool',type=Path,required=True);a=p.parse_args();os.umask(0o077)
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
    from lm_suti_assurance.nl_proposal.provider import generate
    while True:
        line=sys.stdin.buffer.readline(262145)
        if not line:break
        try:
            if len(line)>262144 or not line.endswith(b'\n'):raise ValueError('PROVIDER_INPUT_BOUND')
            answer=generate(json.loads(line),a.spool)
        except Exception as e:answer={'status':'PROVIDER_UNAVAILABLE','reason':type(e).__name__}
        out=json.dumps(answer,ensure_ascii=False,separators=(',',':')).encode()
        if len(out)>MAX:out=b'{"status":"PROVIDER_UNAVAILABLE","reason":"PROVIDER_RECEIPT_BOUND"}'
        sys.stdout.buffer.write(out+b'\n');sys.stdout.buffer.flush()
