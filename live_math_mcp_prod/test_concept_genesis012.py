import ast
import asyncio
import copy
import json
from pathlib import Path

from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest
from pydantic import ValidationError

from native_preview008_qa import readonly_state
from research_store import ResearchStore
from concept_genesis012_worlds import declarations
from concept_genesis012_native import Port,Ledger
from concept_genesis012_oracle import run as oracle_run
from concept_genesis012_qa import seed,request
from concept_genesis012_source import Request
from concept_genesis012 import evaluate
from live_transfer006 import endpoint,initial_cache


@pytest.mark.parametrize('index',range(4))
def test_fresh_source_primitives_match_independent_finite_oracle(index):
    world=declarations('UNIT012')[index];ledger=Ledger(20000,10)
    port=Port(world['parameters'],world['histories'],ledger)
    for word in world['histories'].values():
        cache=initial_cache(port,word)
        for t in world['tests']:
            assert endpoint(port,cache,t['suffix'],world['observer'])==oracle_run(world['parameters'],word,t['suffix'],world['observer'])


def prepared(tmp_path,index=0):
    db=tmp_path/'qa.sqlite3';ResearchStore(db);world=declarations('UNIT012')[index];binding=seed(db,world)
    args=request(db,world,binding);negative=evaluate(db,Request.model_validate(args),'negative')
    assert negative['status']=='SOURCE_COUNTEREXAMPLE'
    from normalizer import canonical
    event=ResearchStore(db).record(world['project'],'counterexample','Computed native counterexample',canonical(negative['counterexample']),'experiment')
    return db,world,binding,request(db,world,binding,event['id'])


@pytest.mark.parametrize('index',range(4))
def test_source_refinement_is_grounded_and_does_not_manufacture_a_grant(tmp_path,index):
    db,world,binding,args=prepared(tmp_path,index);before=readonly_state(db)
    out=evaluate(db,Request.model_validate(args));baseline=evaluate(db,Request.model_validate(args),'baseline')
    assert out['status'] in {'CANDIDATE_REFINEMENT','NO_VALID_INTERPRETATION'}
    assert not out['execution_permission']['allowed'] and out['proof_status']=='unverified'
    assert baseline['status']=='BASELINE_FINITE_CENSUS'
    if out['status']=='CANDIDATE_REFINEMENT':
        suffix=[world['parameters']['actions'][i] for i in out['concept']['suffix_ordinals']]
        test=next(t for t in world['tests'] if t['suffix']==suffix)
        assert len(out['concept']['interpretations'])>=2
        for cell in out['concept']['interpretations']:
            for ref in cell['source_members']:assert baseline['table'][ref][test['id']]==cell['prediction']
        assert out['concept']['asserts_future_congruence'] is False
    assert readonly_state(db)==before


@pytest.mark.parametrize('case',['trace','feedback','hash','version','observer','quota'])
def test_incomplete_or_false_context_fails_closed_and_retains_error_cost(tmp_path,case):
    db,world,binding,args=prepared(tmp_path);before=readonly_state(db)
    if case=='trace':args['trace_access']=False
    elif case=='feedback':args['negative_event_id']=None
    elif case=='hash':args['source_bindings'][0]['sha256']='0'*64
    elif case=='version':args['version']=99
    elif case=='observer':args['observer']['mod']=1
    else:args['max_calls']=1
    out=evaluate(db,Request.model_validate(args))
    assert out['status'] in {'INSUFFICIENT_CONTEXT','NO_NEGATIVE_FEEDBACK','BUDGET_EXHAUSTED'}
    if case=='quota':assert out['costs']['total_native_calls']==1
    assert not out['execution_permission']['allowed'] and readonly_state(db)==before


def test_runtime_has_no_oracle_world_or_environment_dependency():
    source=Path(__file__).resolve().parent
    for name in ('concept_genesis012','concept_genesis012_source','concept_genesis012_native','concept_genesis012_server'):
        text=(source/(name+'.py')).read_text();tree=ast.parse(text)
        imports=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        assert not any(any(bad in module for bad in ('_oracle','_worlds','_qa','_model')) for module in imports)
        if name=='concept_genesis012':
            assert not any(isinstance(n,ast.Constant) and isinstance(n.value,str) and n.value in {'boolean_relations','annihilation','coloured_stack','quadratic_residues'} for n in ast.walk(tree))


def test_real_private_mcp_readonly_schema_and_no_operator_authority(tmp_path):
    db,world,binding,args=prepared(tmp_path);before=readonly_state(db)
    async def work():
        import sys
        p=StdioServerParameters(command=sys.executable,args=[str(Path(__file__).with_name('concept_genesis012_server.py')),'--db',str(db)])
        async with stdio_client(p) as (read,write):
            async with ClientSession(read,write) as client:
                await client.initialize();tools=await client.list_tools()
                assert len(tools.tools)==3 and all(t.annotations.readOnlyHint for t in tools.tools)
                assert all(t.inputSchema['additionalProperties'] is False for t in tools.tools)
                response=await client.call_tool('concept_genesis_preview',{'request':args});assert not response.isError
                response=await client.call_tool('concept_genesis_preview',{'request':{**args,'verified':True}});assert response.isError
    asyncio.run(work());assert readonly_state(db)==before
