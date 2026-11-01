"""Real loopback HTTP + OAuth/PKCE + MCP client; no production tokens or stores."""
import argparse
import asyncio
import json
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from dav_acceptance import TappedStream
from davcore.ast import implication
from test_http import register, approve, exchange


class LoopbackTransport(httpx.BaseTransport):
    """Route only the QA HTTPS origin to its local server, preserving logical secure cookies."""
    def __init__(self, port):
        self.port = port
        self.inner = httpx.HTTPTransport()

    def handle_request(self, request):
        assert request.url.host == 'livingmath.example'
        forwarded = httpx.Request(request.method, request.url.copy_with(scheme='http', host='127.0.0.1', port=self.port),
                                  headers=request.headers, stream=request.stream, extensions=request.extensions)
        return self.inner.handle_request(forwarded)

    def close(self):
        self.inner.close()


async def session_checks(url, token, out):
    headers={'Authorization':'Bearer '+token,'Host':'livingmath.example'}
    calls=[]
    async with httpx.AsyncClient(headers=headers,timeout=20) as http:
        async with streamable_http_client(url+'/mcp',http_client=http) as (read,write,_):
            async with ClientSession(TappedStream(read,out/'mcp-wire.jsonl','server_to_client'),TappedStream(write,out/'mcp-wire.jsonl','client_to_server')) as session:
                await session.initialize()
                listing=await session.list_tools()
                assert len(listing.tools)==26
                for kind,formula in [('ca',implication('R0','R2','T0','T2')),('graph',implication('S0','S2','P','Q'))]:
                    args={'project':'LM_QA_DAV_HTTP','spec':{'kind':kind},'request_key':'register-'+kind}
                    r=await session.call_tool('dav_register_adapter',args)
                    assert not r.isError
                    registration=r.structuredContent if r.structuredContent is not None else json.loads(r.content[0].text)
                    calls.append({'tool':'dav_register_adapter','arguments':args,'response':r.model_dump(mode='json')})
                    args={'project':'LM_QA_DAV_HTTP','registration_id':registration['id'],'adapter_binding':registration['payload']['binding'],'formula':formula.model_dump(),'backend':'smt'}
                    r=await session.call_tool('dav_check_law',args)
                    value=r.structuredContent if r.structuredContent is not None else json.loads(r.content[0].text)
                    assert not r.isError and value['status']=='proved'
                    calls.append({'tool':'dav_check_law','arguments':args,'response':r.model_dump(mode='json')})
    (out/'mcp-transcript.json').write_text(json.dumps(calls,indent=2))
    return {'status':'PASS_REAL_LOOPBACK_HTTP_OAUTH_MCP','tool_count':len(listing.tools),'domains':['ca','graph'],
            'tool_calls':len(calls),'anonymous_rejected':True,'oauth_flow':'DCR, owner login, PKCE, resource-bound token',
            'oauth_credentials_recorded':False,'production_accessed':False,'public_HTTPS_tunnel_tested':False}


def run(out):
    out.mkdir(parents=True,exist_ok=False)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    code=Path(__file__).resolve().parent
    app="from http_server import create_app; from pathlib import Path; import uvicorn; uvicorn.run(create_app('https://livingmath.example',Path("+repr(str(out))+"),'a-long-local-test-password'),host='127.0.0.1',port="+str(port)+",access_log=False)"
    import os
    env={**os.environ,'LIVE_MATH_DAV':'1','LIVE_MATH_DAV_DB':str(out/'dav.sqlite3'),'PYTHONDONTWRITEBYTECODE':'1'}
    with (out/'server.log').open('w') as log:
        p=subprocess.Popen([sys.executable,'-c',app],cwd=code,env=env,stdout=log,stderr=subprocess.STDOUT)
        try:
            url='http://127.0.0.1:'+str(port)
            with httpx.Client(base_url='https://livingmath.example',transport=LoopbackTransport(port)) as client:
                for _ in range(100):
                    try:
                        if client.get('/healthz').status_code==200:break
                    except httpx.ConnectError:pass
                    time.sleep(0.05)
                else:raise RuntimeError('QA HTTP startup failed')
                assert client.post('/mcp',json={'jsonrpc':'2.0','id':1,'method':'tools/list'}).status_code==401
                registration=register(client)
                code,verifier=approve(client,registration)
                response=exchange(client,registration,code,verifier)
                assert response.status_code==200,response.text
                result=asyncio.run(session_checks(url,response.json()['access_token'],out))
            (out/'result.json').write_text(json.dumps(result,indent=2))
            return result
        finally:
            p.terminate()
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:p.kill();p.wait()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    print(json.dumps(run(parser.parse_args().out.resolve())))
