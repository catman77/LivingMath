"""Exercise lifecycle tools through a real MCP client on a private SQLite backup.

The supplied source database is opened read-only and is never used by the
spawned server. Protocol test outcomes are not mathematical research results.
"""
import argparse
import asyncio
import copy
import json
import os
from pathlib import Path
import sqlite3
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from frontier import PRESERVATION_PROPERTIES
from regression_v04 import regression_requests


def unpack(result):
    if result.isError:
        raise AssertionError('MCP error: ' + ''.join(item.text for item in result.content if item.type == 'text'))
    return result.structuredContent if result.structuredContent is not None else json.loads(result.content[0].text)


async def exercise(path, out):
    parameters = StdioServerParameters(command=sys.executable,
        args=[str(Path(__file__).with_name('mcp_server.py')), 'stdio'],
        env={**os.environ, 'LIVE_MATH_DB': str(path)})
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            initialized = await session.initialize()
            assert initialized.serverInfo.version == '0.4.2'
            tools = await session.list_tools()
            assert {'research_move_history', 'audit_research_move', 'transition_research_move'} <= {tool.name for tool in tools.tools}

            async def call(name, arguments, trace=None):
                result = unpack(await session.call_tool(name, arguments))
                if trace is not None:
                    trace.append({'tool': name, 'arguments': arguments, 'result': result})
                return result

            frontier = await call('research_frontier', {'project':'RH','include_closed':True})
            base = regression_requests(frontier)[-1][2]
            active = next(item for item in frontier['obligations'] if item['id'] == base['active_frontier_id'])
            base.update(scope=active['scope'], active_frontier_version=active['version'])
            accepted = []
            record = await call('record_research_move', {'project':'RH','move':base,'request_key':'v041-smoke-propose'}, accepted)
            assert record['status']=='AUDITED' and not record['execution_permission']['allowed']
            allowed = await call('transition_research_move', {'project':'RH','move_id':record['id'],
                'action':'activate_experiment','request_key':'v041-smoke-activate'}, accepted)
            assert allowed['execution_permission']['allowed']
            # The completed task is this software protocol regression, not a
            # source-edge mathematical experiment or a new scientific result.
            completed = await call('transition_research_move', {'project':'RH','move_id':record['id'],
                'action':'complete','request_key':'v041-smoke-complete',
                'evidence_refs':['event:15','artifact:v0.4.2-accepted-trace.json'],
                'result':{'outcome':'SUCCESS','summary':'Software protocol check completed; no mathematical proof.'},
                'reason':'Software lifecycle regression completed on a disposable database clone; no mathematical claim.'}, accepted)
            assert [item['status'] for item in completed['history']] == ['PROPOSED','AUDITED','EXPERIMENT_ALLOWED','COMPLETED']
            assert not completed['execution_permission']['allowed'] and completed['proof_status']=='unverified'
            (out/'accepted-trace.json').write_text(json.dumps({'environment':'Disposable clone of the production backup',
                'mathematical_results_verified':False,'status_path':[item['status'] for item in completed['history']],
                'calls':accepted},ensure_ascii=False,indent=2)+'\n')

            rejected = []
            candidate = copy.deepcopy(base)
            candidate['proposed_operation']['testable_consequence'] += '; protocol-only contract identity check'
            contract = await call('record_transformation_contract', {'project':'RH',
                'source':'Deliberately mismatched protocol control', 'operation':candidate['proposed_operation'],
                'result':candidate['target_representation'], 'source_event_ids':[15],
                'preservation':{prop:{'statement':'Protocol control: no preservation established for '+prop}
                                for prop in PRESERVATION_PROPERTIES}}, rejected)
            candidate['transformation_contract_id']=contract['id']
            denied = await call('record_research_move', {'project':'RH','move':candidate,'request_key':'v041-smoke-reject'}, rejected)
            assert [item['status'] for item in denied['history']] == ['PROPOSED','AUDITED','REJECTED']
            assert not denied['execution_permission']['allowed']
            assert all(not item['decision'].get('allowed') for item in denied['history'])
            arguments={'project':'RH','move_id':denied['id'],'action':'activate_experiment','request_key':'v041-smoke-denied-activation'}
            error = await session.call_tool('transition_research_move', arguments)
            assert error.isError
            rejected.append({'tool':'transition_research_move','arguments':arguments,'result':error.model_dump(mode='json')})
            renamed = copy.deepcopy(candidate)
            renamed['proposed_operation'].update(display_name='Renamed control', mechanism='new-name-only')
            repeat = await call('record_research_move', {'project':'RH','move':renamed,'request_key':'v041-smoke-renamed'}, rejected)
            assert repeat['id']==denied['id'] and repeat['status']=='REJECTED'
            (out/'rejected-trace.json').write_text(json.dumps({'environment':'Disposable clone of the production backup',
                'mathematical_results_verified':False,'status_path':[item['status'] for item in denied['history']],
                'execution_permission_ever_issued':False,'calls':rejected},ensure_ascii=False,indent=2)+'\n')
            health = await call('service_health', {})
            assert health['audit']['ok'] and health['schema_version']==5
            return {'version':initialized.serverInfo.version,'tool_count':len(tools.tools),
                    'accepted_cycle':['PROPOSED','AUDITED','EXPERIMENT_ALLOWED','COMPLETED'],
                    'rejected_cycle':['PROPOSED','AUDITED','REJECTED'],
                    'rejected_activation_failed':True, 'renamed_rejection_deduplicated':True,
                    'mathematical_results_verified':False,'health':health,'result':'PASS'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-db',required=True)
    parser.add_argument('--out',required=True)
    args=parser.parse_args()
    source=Path(args.source_db).expanduser().resolve(strict=True)
    out=Path(args.out).expanduser().resolve()
    out.mkdir(parents=True,exist_ok=True,mode=0o700)
    clone=out/'lifecycle-demo.sqlite3'
    if clone.exists() or clone==source:
        raise SystemExit('Use a fresh output directory; refusing to overwrite an existing database.')
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as connection, sqlite3.connect(clone) as backup:
        connection.backup(backup)
    clone.chmod(0o600)
    result=asyncio.run(exercise(clone,out))
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
