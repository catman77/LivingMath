"""Real MCP acceptance: submit once, automatic progress/restart/input wake, public alchemy."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from dav_acceptance import TappedStream
from davcore.ast import implication
from davcore.storage import Store
from research_automation.contract import Fact, Hypothesis, Prediction, Problem, ResearchInput
from research_automation.source_bridge import public_model_inputs


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))


async def run(out: Path, model_path: Path):
    out.mkdir(parents=True, exist_ok=False)
    code = Path(__file__).resolve().parent
    calls, checks = [], []
    project = 'LM_QA_AUTOMATIC_SUTI_BRIDGE'
    wire = out/'mcp-wire.jsonl'
    params = StdioServerParameters(command=sys.executable, args=[str(code/'mcp_server.py'), 'stdio'], env={
        'LIVE_MATH_DB': str(out/'research.sqlite3'), 'LIVE_MATH_DAV_DB': str(out/'dav.sqlite3'),
        'LIVE_MATH_DAV': '1', 'LIVE_MATH_AUTORESEARCH': '1', 'PYTHONDONTWRITEBYTECODE': '1'})

    def check(name, condition):
        checks.append({'invariant': name, 'result': 'PASS' if condition else 'FAIL'})
        write(out/'checks.json', checks)
        if not condition:
            raise AssertionError(name)

    async def call(client, name, args, error=False):
        raw = await client.call_tool(name, args)
        calls.append({'tool': name, 'arguments': args, 'response': raw.model_dump(mode='json', by_alias=True)})
        write(out/'mcp-transcript.json', calls)
        if error:
            check('EXPECTED_REJECTION_' + name + '_' + str(len(calls)), raw.isError)
            return None
        assert not raw.isError, calls[-1]
        return raw.structuredContent if raw.structuredContent is not None else json.loads(raw.content[0].text)

    async def view(client):
        # Status is a read call, not an instruction to advance the engine.
        cases, offset = [], 0
        while True:
            result = await call(client, 'research_autonomy_status', {'project': project, 'offset': offset, 'limit': 20})
            cases.extend(result['cases'])
            if result['next_offset'] is None:
                return cases
            offset = result['next_offset']

    async def wait(client, predicate, label, seconds=60):
        start = time.monotonic()
        while time.monotonic() - start < seconds:
            cases = await view(client)
            if predicate(cases):
                return cases
            await asyncio.sleep(0.25)
        raise RuntimeError('Automatic acceptance deadline: ' + label)

    with (out/'server-first.log').open('w') as err:
        async with stdio_client(params, errlog=err) as (read, send):
            async with ClientSession(TappedStream(read,wire,'server_to_client'), TappedStream(send,wire,'client_to_server')) as client:
                await client.initialize()
                listing = await client.list_tools()
                write(out/'tools-list.json', listing.model_dump(mode='json'))
                check('AUTOMATIC_PROFILE_30_TOOLS', len(listing.tools) == 30)
                await call(client, 'dav_register_adapter', {'project':project,'spec':{'kind':'gate6','mask':1},'request_key':'gate6'})
                initial = await view(client)
                check('REGISTRATION_AUTOMATICALLY_CREATED_CASE', len(initial) == 1)
                write(out/'before-restart.json', initial)
                initial_case_id = initial[0]['case_id']
    # New real MCP server process; no control/advance/re-submit call.
    with (out/'server-second.log').open('w') as err:
        async with stdio_client(params, errlog=err) as (read, send):
            async with ClientSession(TappedStream(read,wire,'server_to_client'), TappedStream(send,wire,'client_to_server')) as client:
                await client.initialize()
                done = await wait(client, lambda xs: any(x['case_id']==initial_case_id and x['status']=='COMPLETED' for x in xs), 'restart')
                repaired = next(x for x in done if x['case_id']==initial_case_id)
                check('RESTART_RESUMED_THE_SAME_CASE', repaired['result']['observer_mask']==3)
                check('NEGATIVE_CANDIDATE_AND_RCA_PRESERVED', repaired['result']['counterexamples_preserved']>0)
                check('LIFECYCLE_NO_MANUAL_TRANSITIONS', set(['QUEUED','DIAGNOSING','PROPOSING','AUDITING','EXPERIMENTING','CHECKING','COMPLETED']) <= {h['status'] for h in repaired['history']})
                await call(client,'dav_register_adapter',{'project':project,'spec':{'kind':'ca','width':3,'mask':1},'request_key':'ca'})
                model = json.loads(model_path.read_bytes())
                sha = hashlib.sha256(model_path.read_bytes()).hexdigest()
                packets = public_model_inputs(model, sha)
                for index, packet in enumerate(packets):
                    await call(client,'research_autonomy_ingest',{'project':project,'source':packet.model_dump(),'request_key':'public-'+str(index)})
                regular = await call(client,'dav_register_adapter',{'project':project,'spec':{'kind':'gate6'},'request_key':'original-gate6'})
                await call(client,'dav_check_law',{'project':project,'registration_id':regular['id'],'adapter_binding':regular['payload']['binding'],
                    'formula':implication('P','One','Joint','One').model_dump(),'persist':True,'request_key':'original-false-law'})
                scope = 'QA/automatic-input-wake'
                packet = ResearchInput(scope=scope, problems=[Problem(kind='identify_model', scope=scope, hypotheses=[
                    Hypothesis(model_id='A',target='alpha',predictions=[Prediction(feature='color',value='red')]),
                    Hypothesis(model_id='B',target='beta',predictions=[Prediction(feature='color',value='blue')])])])
                first = await call(client,'research_autonomy_ingest',{'project':project,'source':packet.model_dump(),'request_key':'input-gap'})
                duplicate = await call(client,'research_autonomy_ingest',{'project':project,'source':packet.model_dump(),'request_key':'input-gap'})
                check('INTAKE_IDEMPOTENT',first==duplicate)
                waiting = await wait(client, lambda xs: len(xs)==47 and all(x['status'] in {'WAITING_FOR_INPUT','COMPLETED'} for x in xs), 'all automatic stages')
                source_cases = [x for x in waiting if x['scope'].startswith('source/')]
                check('PUBLIC_43_GAPS_AUTOMATICALLY_DIAGNOSED', len(source_cases)==43 and all(x['status']=='WAITING_FOR_INPUT' for x in source_cases))
                check('GENERIC_CA_OBSERVER_AUTOMATICALLY_REPAIRED', any(x['result'].get('observer_mask')==7 for x in waiting))
                check('ORIGINAL_P1_Q0_NOT_FILTERED',any(x['result'].get('outcome')=='LAW_REFUTED' and x['result']['counterexample']['state']==1 for x in waiting))
                facts=ResearchInput(scope=scope,facts=[Fact(feature='color',value='red')])
                await call(client,'research_autonomy_ingest',{'project':project,'source':facts.model_dump(),'request_key':'new-observation'})
                after = await wait(client, lambda xs: next(x for x in xs if x['scope']==scope)['status']=='COMPLETED','automatic new-input wake')
                identified = next(x for x in after if x['scope']==scope)
                check('NEW_INPUT_AUTOMATICALLY_WOKE_CASE', identified['generation']==2 and identified['result']['surviving_models']==['A'])
                conflicting=ResearchInput(scope=scope,facts=[Fact(feature='color',value='blue')])
                await call(client,'research_autonomy_ingest',{'project':project,'source':conflicting.model_dump(),'request_key':'conflicting-observation'})
                final = await wait(client, lambda xs: next(x for x in xs if x['scope']==scope)['status']=='REQUIRES_REVIEW','conflict')
                check('ADVERSE_INPUT_REOPENS_COMPLETED_CASE',next(x for x in final if x['scope']==scope)['generation']==3)
                await call(client,'research_autonomy_status',{'project':'FOREIGN','case_id':initial_case_id},error=True)
                await call(client,'research_autonomy_ingest',{'project':project,'source':packet.model_dump(),'request_key':'input-gap','advance':True},error=True)
                check('NO_MANUAL_ADVANCE_OR_ACTIVATION_TOOL_CALLED',not any(x['tool'] in {'audit_research_move','transition_research_move'} for x in calls))
                health=await call(client,'service_health',{})
                check('AUTONOMOUS_WORKER_RUNNING',health['automatic_research']['background_running'])
                check('NO_AUTOMATIC_VERIFICATION_OR_EXTERNAL_GRANTS', all(x['proof_status']=='unverified' and x['execution_permission']=={'allowed':False} for x in final))
                write(out/'final-cases.json',final)
                # Full append-only steps are exported directly from the private QA journal as evidence.
                s=Store(out/'dav.sqlite3')
                with s.connect() as connection:
                    rows=[s.decode(r) for r in connection.execute("SELECT * FROM dav_records WHERE kind LIKE 'automation_%' ORDER BY id")]
                write(out/'automatic-history.json',rows)
    integrity=Store(out/'dav.sqlite3').integrity()
    check('APPEND_ONLY_HASH_CHAIN_INTACT',integrity['ok'])
    result={'status':'PASS_AUTOMATIC_RESEARCH_PRODUCT_MCP','invariants':checks,'tool_calls':len(calls),
            'automatic_stage_control_calls':0,'restarted_server_processes':2,'source_model_sha256':sha,
            'original_unknown_records_preserved':len(model['uncertainty']),'source_case_count':43,
            'source_status':'WAITING_FOR_INPUT_WITH_SCOPED_REQUIREMENTS','final_case_count':len(final),
            'hash_chain':integrity,'closed_inputs_opened':False,'production_deployed':False,
            'proof_status':'unverified','execution_permission':{'allowed':False}}
    write(out/'result.json',result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);parser.add_argument('--model',type=Path,required=True)
    a=parser.parse_args()
    r=asyncio.run(run(a.out.resolve(),a.model.resolve()))
    print(json.dumps({'status':r['status'],'invariants':len(r['invariants']),'tool_calls':r['tool_calls']}))
