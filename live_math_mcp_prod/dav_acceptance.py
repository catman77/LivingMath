"""Real MCP stdio acceptance, two builtin domains and source-bound public Ripley replay."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from davcore.ast import implication
from davcore.storage import Store


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))


class TappedStream:
    def __init__(self, stream, path, direction):
        self.stream, self.path, self.direction = stream, path, direction

    def record(self, message):
        if hasattr(message, 'message'):
            with self.path.open('a') as f:
                f.write(json.dumps({'direction': self.direction, 'message': message.message.model_dump(mode='json', by_alias=True, exclude_none=True)}, ensure_ascii=False) + '\n')

    async def send(self, message):
        self.record(message)
        await self.stream.send(message)

    async def receive(self):
        message = await self.stream.receive()
        self.record(message)
        return message

    def __aiter__(self):
        return self

    async def __anext__(self):
        import anyio
        try:
            return await self.receive()
        except anyio.EndOfStream:
            raise StopAsyncIteration from None

    async def aclose(self):
        await self.stream.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.aclose()


async def run(out: Path, model: Path):
    out.mkdir(parents=True, exist_ok=False)
    code = Path(__file__).resolve().parent
    calls, invariants, registrations = [], [], {}
    project = 'LM_QA_DAV001_ALCH'

    def passed(name, condition):
        invariants.append({'invariant': name, 'result': 'PASS' if condition else 'FAIL'})
        if not condition:
            raise AssertionError(name)

    async def call(session, name, args, error=False):
        response = await session.call_tool(name, args)
        calls.append({'tool': name, 'arguments': args, 'response': response.model_dump(mode='json', by_alias=True)})
        write(out/'mcp-transcript.json', calls)
        if error:
            passed('EXPECTED_REJECTION_' + name + '_' + str(len(calls)), response.isError)
            return response
        assert not response.isError, calls[-1]
        if response.structuredContent is not None:
            return response.structuredContent
        return json.loads(response.content[0].text)

    parameters = StdioServerParameters(command=sys.executable, args=[str(code/'mcp_server.py'), 'stdio'], env={
        'LIVE_MATH_DB': str(out/'research.sqlite3'), 'LIVE_MATH_DAV': '1', 'LIVE_MATH_DAV_DB': str(out/'dav.sqlite3'),
        'PYTHONDONTWRITEBYTECODE': '1'})
    with (out/'mcp-stderr.log').open('w') as err:
        async with stdio_client(parameters, errlog=err) as (read, send):
            async with ClientSession(TappedStream(read,out/'mcp-wire.jsonl','server_to_client'),
                                     TappedStream(send,out/'mcp-wire.jsonl','client_to_server')) as client:
                init = await client.initialize()
                write(out/'initialize.json', init.model_dump(mode='json'))
                tools = await client.list_tools()
                write(out/'tools-list.json', tools.model_dump(mode='json'))
                passed('REAL_MCP_26_TOOLS', len(tools.tools) == 26)
                for kind, good, bad in [('ca', implication('R0','R2','T0','T2'), implication('T0','T1','T0','T2')),
                                        ('graph', implication('S0','S2','P','Q'), implication('S0','S0','P','Q'))]:
                    request = {'project': project, 'spec': {'kind': kind}, 'request_key': 'register-' + kind}
                    r = await call(client,'dav_register_adapter',request)
                    registrations[kind] = r
                    duplicate = await call(client,'dav_register_adapter',request)
                    passed('REGISTRATION_IDEMPOTENT_' + kind, r['id'] == duplicate['id'])
                    args = {'project':project,'registration_id':r['id'],'adapter_binding':r['payload']['binding']}
                    obs = await call(client,'dav_observe',args | {'states':[0,255]})
                    passed('OBSERVATION_SAMPLE_ONLY_' + kind, obs['status']=='consistent_with_observations')
                    for backend in ['finite','smt']:
                        outcome = await call(client,'dav_check_law',args | {'formula':good.model_dump(),'backend':backend,
                            'persist':True,'request_key':'law-'+kind+'-'+backend})
                        passed('GOLDEN_'+kind+'_'+backend, outcome['payload']['status']=='proved' and outcome['payload']['proof_status']=='unverified')
                        exported = await call(client,'dav_export_evidence',{'project':project,'evidence_id':outcome['id']})
                        passed('CERTIFICATE_EXPORT_'+kind+'_'+backend, exported['certificate_current'])
                    sample = await call(client,'dav_check_law',args | {'formula':good.model_dump(),'states':[0,255]})
                    passed('SAMPLE_NOT_FULL_PROOF_'+kind, sample['status']=='consistent_with_observations')
                    failure = await call(client,'dav_find_counterexample',args | {'formula':bad.model_dump(),'persist':True,'request_key':'bad-'+kind})
                    passed('CONCRETE_COUNTEREXAMPLE_'+kind, failure['payload']['status']=='refuted' and bool(failure['payload']['counterexample']['steps']))
                    reduced = await call(client,'dav_reduce_library',args | {'persist':True,'request_key':'library-'+kind})
                    passed('LIBRARY_'+kind, reduced['payload']['status']=='proved' and reduced['payload']['search_complete'])
                    passed('COUNTEREXAMPLE_LINKED_'+kind, any(v['evidence_id']==failure['id'] for v in reduced['payload']['counterexample_links']))
                    generated = await call(client,'dav_generate_candidates',args | {'budget':{'max_candidates':3}})
                    passed('BOUNDED_GENERATION_'+kind, len(generated['laws'])==3 and generated['next_cursor']==3)
                    audited = await call(client,'dav_audit_adapter',args)
                    passed('ADAPTER_AUDIT_'+kind, audited['congruent'])
                a = {'project':project,'registration_id':registrations['graph']['id'],
                     'adapter_binding':registrations['graph']['payload']['binding'],'formula':implication('S0','S2','P','Q').model_dump()}
                await call(client,'dav_check_law',a | {'complete':True},error=True)
                await call(client,'dav_check_law',a | {'project':'OTHER_PROJECT'},error=True)
                await call(client,'dav_check_law',a | {'adapter_binding':'0'*64},error=True)
                await call(client,'dav_register_adapter',{'project':project,'spec':{'kind':'ca','python':'import os'},'request_key':'hostile'},error=True)
                # Public source wrapper is read, never the holdout/split/ciphertext/key.
                raw = model.read_bytes()
                public = json.loads(raw)
                original = public['logic']['accepted003']['gate6_revisions']
                alchemy = {'source_model_sha256':hashlib.sha256(raw).hexdigest(), 'source_identity':public['source_identity'],
                    'source_refs':original[0]['source_refs'], 'original_revision_hashes':[x['record_hash'] for x in original],
                    'source_model_preserved':True,'closed_material_opened':False,'comparative_evaluation':'COMPARATIVE_NOT_RUN',
                    'physical_measurements':0,'psychological_efficacy':'NOT_ESTABLISHED','proof_status':'unverified',
                    'critical_distinctions':8,'branches':len(public['models']),'states':len(public['states']),
                    'transitions':len(public['transitions']),'cross_layer_links':len(public['cross_layer_links'])}
                gate_law = implication('P','One','Joint','One').model_dump()
                results = {}
                for label,spec in [('original',{'kind':'gate6'}),
                                   ('conditional',{'kind':'gate6','assumption':'P_implies_Q_NOT_SOURCE_ATTESTED'}),
                                   ('projected',{'kind':'gate6','mask':1}),('refined',{'kind':'gate6','mask':3})]:
                    r = await call(client,'dav_register_adapter',{'project':project,'spec':spec,'request_key':'alch-'+label})
                    args = {'project':project,'registration_id':r['id'],'adapter_binding':r['payload']['binding']}
                    ar = await call(client,'dav_audit_adapter',args)
                    checks = {}
                    if label in {'original','conditional'}:
                        for backend in ['finite','smt']:
                            checks[backend] = await call(client,'dav_check_law',args | {'formula':gate_law,'backend':backend,
                                'persist':True,'request_key':'alch-'+label+'-'+backend})
                    results[label] = {'registration_id':r['id'],'binding':r['payload']['binding'],'audit':ar,'checks':checks}
                passed('ALCH_ORIGINAL_COUNTERVALUATION_P1_Q0',all(x['payload']['status']=='refuted' and x['payload']['counterexample']['state']==1 for x in results['original']['checks'].values()))
                passed('ALCH_CONDITIONAL_ONLY_EXPLICIT_ASSUMPTION',all(x['payload']['status']=='proved' and x['payload']['scope']['adapter']['assumptions']==['P_implies_Q_NOT_SOURCE_ATTESTED'] for x in results['conditional']['checks'].values()))
                passed('ALCH_PROJECTED_CONTINUATION_INSUFFICIENT',results['projected']['audit']['congruent'] is False)
                passed('ALCH_REPRESENTATION_REFINEMENT_CONGRUENT',results['refined']['audit']['congruent'] is True)
                # Search the complete two-bit observer-refinement family, with required retention of P.
                # The allowed candidates are exactly 1 and 3; no changing source, domain or assumptions.
                alchemy['bounded_representation_cycle'] = {'domain_changes':False,'new_assumptions':[],
                    'original_observer_mask':1,'candidate_refinements':[1,3],'minimal_congruent_refinement':3,
                    'criterion':'retain P and distinguish all operation continuations; no constant projection',
                    'result':'FORMAL_OBSERVER_INSUFFICIENCY_RESOLVED',
                    'external_Q_observation':'STILL_UNKNOWN_NO_NEW_MEASUREMENT','evidence':results}
                alchemy['remaining_gaps'] = [dict(record_id=r['record_id'],field=r['payload']['field'],
                     reason=r['payload']['reason'],source_refs=r['source_refs'],status='UNKNOWN_RETAINED') for r in public['uncertainty']]
                alchemy['remaining_gaps_count'] = len(alchemy['remaining_gaps'])
                alchemy['text_only_fragments'] = sum(x['payload']['modeling_status']=='TEXT_ONLY' for x in public['reverse_traces'])
                write(out/'alchemy-result.json',alchemy)
                await call(client,'service_health',{})
    result = {'status':'PASS_DAV_MCP_AND_PUBLIC_ALCHEMY_REPLAY','transport':'real MCP ClientSession over stdio',
              'tool_calls':len(calls),'invariants':invariants,'registrations':{k:r['id'] for k,r in registrations.items()},
              'dav_integrity':Store(out/'dav.sqlite3').integrity(),'production_deployed':False,
              'execution_grants':0,'scientifically_verified_claims':0}
    assert result['dav_integrity']['ok']
    write(out/'result.json',result)
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--model',type=Path,required=True)
    args=parser.parse_args()
    result=asyncio.run(run(args.out.resolve(),args.model.resolve()))
    print(json.dumps({'status':result['status'],'tool_calls':result['tool_calls'],'invariants':len(result['invariants'])}))
