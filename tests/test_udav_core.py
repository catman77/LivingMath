"""Real primitives and workers; independent oracles are never production imports."""
import copy,hashlib,json
from pathlib import Path
import pytest
from lm_suti_assurance.udav_core.symbolic import run,binding
from lm_suti_assurance.udav_core.frontier import arguments,family_size
from lm_suti_assurance.udav_core.numeric import distinctions
from lm_suti_assurance.symbolic.state import History,SymbolicState,Atom,source_states
from lm_suti_assurance.errors import AssuranceError
ROOT=Path(__file__).resolve().parents[1]


def request(seed=119):
    q=json.loads((ROOT/'docs/udav-core001/fixtures/split-request.json').read_text());q['search'].update(strategy='frontier_argument_coverage_v1',seed=seed);return q


@pytest.mark.parametrize('seed',range(119,125))
def test_full_split_coverage_real_state_engine(seed):
    r=run(request(seed),None);states={s['node_id']:s for s in r['states']};words={tuple(s['tokens']) for s in states.values()};root=next(iter(states.values()))['tokens']
    target={tuple(root[a:b]) for a in range(9) for b in range(a,9)}
    assert len(target)==22 and words==target and r['summary']['applied']==72
    all_inputs={c['input_node'] for t in r['ops_trace'] for c in t['candidates']}
    assert any(all(i in all_inputs and len(states[i]['tokens'])>=2 for i in c['outputs']) for t in r['ops_trace'] for c in t['candidates'])
    work=[(c['input_node'],c['operator'],c['parameter_key']) for t in r['ops_trace'] for c in t['candidates']]
    assert len(work)==len(set(work)) and r['checks']['DAG_acyclic_and_hashed']
    assert not r['summary']['global_exhaustion_proved']


def test_operator_order_and_provenance_identity():
    a=request();a['operators']=['SPLIT','REVERSE'];b=copy.deepcopy(a);b['operators'].reverse()
    left,right=run(a,None),run(b,None);assert left['ops_trace']==right['ops_trace'] and left['history']==right['history']
    a=request();a['search']['history_identity']='provenance';p=run(a,None)
    assert len(p['history'])>p['summary']['unique_literal_words'] and p['checks']['DAG_acyclic_and_hashed']


def test_raw_hashes_do_not_become_structural_novelty():
    q=request();q['operators']=['RENAME'];q['observers']=['literal','composition','alpha_pattern'];r=run(q,None)
    assert r['summary']['new_raw_observation']>0 and r['summary']['new_structural_class']==0
    assert r['summary']['parameter_coverage']['RENAME']['status']=='ARGUMENT_FAMILY_PARTIAL'
    q=request();q['observers']=['literal','composition'];r=run(q,None)
    assert r['summary']['new_structural_class'] is None and r['summary']['structural_novelty_status']=='STRUCTURAL_NOVELTY_UNDEFINED'
    q=request();r=run(q,None);assert r['summary']['new_structural_class']>0


@pytest.mark.parametrize('field,value',[('max_nodes',3),('max_total_tokens',16),('max_observations',2),('cpu_budget_ms',1)])
def test_resource_bound_is_partial_and_keeps_provenance(field,value):
    q=request();q['search'][field]=value;r=run(q,None)
    assert r['summary']['halt_reason'] in ['MAX_NODES','MAX_TOTAL_TOKENS','MAX_OBSERVATIONS','CPU_BOUND']
    assert not r['summary']['global_exhaustion_proved'] and r['checks']['DAG_acyclic_and_hashed']


def test_exact_positions_and_insert_kinds():
    q=request();h=History();_,roots,_=source_states(q,h);s=h.states[roots[0]]
    assert [arguments(s,'SPLIT',i,roots,h)[0]['position'] for i in range(family_size(s,'SPLIT',roots,3))]==list(range(9))
    assert {arguments(s,'INSERT_CANCEL_PAIR',i,roots,h)[0]['kind'] for i in range(family_size(s,'INSERT_CANCEL_PAIR',roots,3))}=={'SP','PS'}


def test_fake_alias_rejected_and_ambiguity_not_assigned():
    d={'concepts':[{'id':x} for x in 'ABC']};atlas={'charts':[{'view':0,'aliases':[{'concepts':['A','B']},{'concepts':['A','C']}]}]}
    r=distinctions(d,atlas)[0];assert r['alias_resolution']=='DISTINCTION_AMBIGUOUS' and r['distinction_key'] is None
    atlas['charts'][0]['aliases'][0]['concepts']=['A','FAKE']
    with pytest.raises(AssuranceError):distinctions(d,atlas)


def test_sha_scope_and_request_key_fail_before_new_history(tmp_path):
    import asyncio
    from lm_suti_assurance.udav_core.service import UDAVService
    from lm_suti_assurance.service import Service
    root=tmp_path/'state';Service(root).new('qa','init');s=UDAVService(root,None);w=s.base.workspace('qa');before=w.history()
    q=request();q['source']['sha256']='0'*64
    with pytest.raises(AssuranceError,match='SOURCE_MISMATCH'):asyncio.run(s.explore('qa','wrong','symbolic',q))
    assert w.history()==before


def test_duplicate_word_outputs_keep_their_actual_source_spans():
    q=request();q['source']['text']='a a a';q['source']['sha256']=hashlib.sha256(b'a a a').hexdigest();r=run(q,None)
    outputs=[p['observed_output'] for t in r['ops_trace'] for c in t['candidates'] for p in c['output_parts']]
    assert outputs and all(all(span[0]==q['source']['sha256'] for links in s['source_spans'] for span in links) for s in outputs)
    single=[s['source_spans'] for s in outputs if s['tokens']==['a']]
    assert len({json.dumps(x) for x in single})>1


def test_idempotency_and_conflict_do_not_append_duplicate_records(tmp_path):
    import asyncio
    from lm_suti_assurance.udav_core.service import UDAVService
    from lm_suti_assurance.service import Service
    root=tmp_path/'state';Service(root).new('qa','init');s=UDAVService(root,None);q=request()
    first=asyncio.run(s.explore('qa','same','symbolic',q));w=s.base.workspace('qa');prefix=(w.path/'journal.jsonl').read_bytes()
    assert asyncio.run(s.explore('qa','same','symbolic',q))==first
    assert (w.path/'journal.jsonl').read_bytes()==prefix
    with pytest.raises(AssuranceError,match='REJECTED_PROVENANCE'):s.inspect('qa',first['run_id'],expected_result_sha256='0'*64)
    changed=copy.deepcopy(q);changed['search']['seed']+=1
    with pytest.raises(AssuranceError,match='REQUEST_KEY_CONFLICT'):asyncio.run(s.explore('qa','same','symbolic',changed))
    assert (w.path/'journal.jsonl').read_bytes()==prefix
