"""OAuth HTTP acceptance: automatic research continues with NO MCP client connected."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from dav_acceptance import TappedStream
from dav_http_acceptance import LoopbackTransport
from research_automation.contract import ResearchInput, Problem, Fact
from test_http import register, approve, exchange


def latest(database: Path, scope: str | None = None):
    with sqlite3.connect(database) as c:
        cases = [(i, json.loads(raw)['problem']['scope']) for i, raw in c.execute("SELECT id,payload_json FROM dav_records WHERE kind='automation_case'")]
        if scope is not None:
            cases = [(i, s) for i, s in cases if s == scope]
        out = []
        for ident, name in cases:
            row = c.execute("SELECT payload_json FROM dav_records WHERE kind='automation_step' AND json_extract(payload_json,'$.case_id')=? ORDER BY id DESC LIMIT 1", (ident,)).fetchone()
            out.append((ident, name, json.loads(row[0])['status']))
        return out


async def mcp_call(url: str, token: str, out: Path, name: str, args: dict):
    async with httpx.AsyncClient(headers={'Host':'livingmath.example','Authorization':'Bearer '+token},timeout=20) as client:
        async with streamable_http_client(url+'/mcp',http_client=client) as (read,send,_):
            async with ClientSession(TappedStream(read,out/'mcp-wire.jsonl','server_to_client'),TappedStream(send,out/'mcp-wire.jsonl','client_to_server')) as session:
                await session.initialize()
                listing=await session.list_tools()
                assert len(listing.tools)==30
                raw=await session.call_tool(name,args)
                assert not raw.isError,raw
                with (out/'mcp-transcript.jsonl').open('a') as f:
                    f.write(json.dumps({'tool':name,'arguments':args,'response':raw.model_dump(mode='json')})+'\n')
                return raw.structuredContent if raw.structuredContent is not None else json.loads(raw.content[0].text)


def wait_database(database, predicate, seconds=20):
    start=time.monotonic()
    while time.monotonic()-start<seconds:
        if predicate(latest(database)):
            return
        time.sleep(0.1)
    raise AssertionError('No autonomous progress during MCP-idle interval: '+repr(latest(database)))


def run(out: Path):
    out.mkdir(parents=True,exist_ok=False);inbox=out/'inbox';inbox.mkdir()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    code=Path(__file__).resolve().parent
    app="from http_server import create_app; from pathlib import Path; import uvicorn; uvicorn.run(create_app('https://livingmath.example',Path("+repr(str(out))+"),'a-long-local-test-password'),host='127.0.0.1',port="+str(port)+",access_log=False)"
    env={**os.environ,'LIVE_MATH_DAV':'1','LIVE_MATH_DAV_DB':str(out/'dav.sqlite3'),
         'LIVE_MATH_AUTORESEARCH':'1','LIVE_MATH_AUTORESEARCH_INBOX':str(inbox),'PYTHONDONTWRITEBYTECODE':'1'}
    with (out/'server.log').open('w') as log:
        process=subprocess.Popen([sys.executable,'-B','-c',app],cwd=code,env=env,stdout=log,stderr=subprocess.STDOUT)
        try:
            with httpx.Client(base_url='https://livingmath.example',transport=LoopbackTransport(port)) as client:
                for _ in range(100):
                    try:
                        if client.get('/healthz').status_code==200:break
                    except httpx.ConnectError:pass
                    time.sleep(0.05)
                else:raise RuntimeError('QA HTTP startup failed')
                assert client.post('/mcp',json={'jsonrpc':'2.0','id':1,'method':'tools/list'}).status_code==401
                registration=register(client);code_value,verifier=approve(client,registration)
                result=exchange(client,registration,code_value,verifier);assert result.status_code==200
                token=result.json()['access_token']
            url='http://127.0.0.1:'+str(port)
            asyncio.run(mcp_call(url,token,out,'dav_register_adapter',{
                'project':'LM_QA_AUTOMATION_HTTP','spec':{'kind':'gate6','mask':1},'request_key':'r'}))
            # All MCP contexts closed above. Only SELECTs observe progress; they cannot advance a case.
            wait_database(out/'dav.sqlite3',lambda rows:len(rows)==1 and rows[0][2]=='COMPLETED')
            no_client_completion=latest(out/'dav.sqlite3')
            scope='HTTP_INBOX_INPUT'
            packet=ResearchInput(scope=scope,problems=[Problem(kind='input_gap',scope=scope,required_features=['Q'])])
            (inbox/'01-problem.json').write_text(json.dumps({'project':'LM_QA_AUTOMATION_HTTP','input':packet.model_dump()}))
            wait_database(out/'dav.sqlite3',lambda rows:any(s==scope and state=='WAITING_FOR_INPUT' for _,s,state in rows))
            waiting=latest(out/'dav.sqlite3',scope)
            fact=ResearchInput(scope=scope,facts=[Fact(feature='Q',value='new declared source input')])
            (inbox/'02-observation.json').write_text(json.dumps({'project':'LM_QA_AUTOMATION_HTTP','input':fact.model_dump()}))
            wait_database(out/'dav.sqlite3',lambda rows:any(s==scope and state=='COMPLETED' for _,s,state in rows))
            final=asyncio.run(mcp_call(url,token,out,'research_autonomy_status',{'project':'LM_QA_AUTOMATION_HTTP'}))
            assert all(c['status']=='COMPLETED' for c in final['cases'])
            result={'status':'PASS_AUTOMATIC_HTTP_IDLE_AND_INBOX_WAKE','anonymous_denied':True,'auth':'real OAuth/PKCE',
                'tool_count':30,'MCP_tools_called':['dav_register_adapter','research_autonomy_status'],
                'manual_stage_advance_calls':0,'completed_without_MCP_client':no_client_completion,
                'inbox_waiting_case':waiting,'inbox_automatically_resumed':True,'final':final,
                'physical_execution_grants':0,'scientific_proof_status':'unverified','public_TLS_tested':False}
            (out/'result.json').write_text(json.dumps(result,indent=2))
            return result
        finally:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    r=run(parser.parse_args().out.resolve());print(json.dumps({'status':r['status']}))
