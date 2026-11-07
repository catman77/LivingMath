"""Causal protocol checks. Fixture providers here are explicit unit doubles."""
import asyncio
import copy
import hashlib
import json
import pytest
from lm_suti_assurance.core import digest
from lm_suti_assurance.errors import AssuranceError
from lm_suti_assurance.nl_proposal.causal import arm_candidates, check_primitive_path, primitive_successors, redecode, ARMS
from lm_suti_assurance.nl_proposal.finite_relations import relation
from lm_suti_assurance.nl_proposal.decoder import source_packet, decode, build_request
from lm_suti_assurance.nl_proposal.causal_service import CausalService
from lm_suti_assurance.formal_bridge.fol import typecheck
from test_nl_proposal import AST, SIG, POLICY, source, answer

P = {'max_candidates_per_source': 8, 'max_ast_nodes': 32, 'max_cpu_ms': 4000, 'sham_seed': 2211, 'max_primitive_depth': 2,
     'model_class': {'domain_sizes': [1,2,3], 'max_models': 530, 'max_relation_cells': 9}}
NO_TICK = lambda: None


def frozen():
    s=source();a=answer(s);packet=source_packet(s)
    items=[{'source_ref':'1'*64,'packet':packet,'signature':SIG,'answer':a,'traces':[]}]
    req=build_request(items,POLICY);raw=json.dumps({'items':[a]})
    receipt={'status':'OK','request':req,'request_sha256':digest(req),'raw_output':raw,'raw_output_sha256':hashlib.sha256(raw.encode()).hexdigest()}
    bundle={'receipt':receipt,'receipt_digest':digest(receipt),'policy':POLICY,'items':items,
            'decoded_sha256':digest([decode(packet,SIG,a,receipt,[],POLICY)])}
    t={'trace_sha256':'2'*64,'source_order':[{'byte_utf8':x['byte_utf8'],'literal':x['literal']} for x in reversed(packet['tokens'])]}
    return bundle,t


def test_four_arms_one_frozen_response_and_constructive_swap():
    b,t=frozen();before=digest(b)
    r=redecode(b,[0],{'0':[t]},list(ARMS),P)
    assert digest(b)==before and not r['execution_permission']
    assert r['invariants']['model_calls_delta']==0 and r['invariants']['raw_output_equal']
    i=r['items'][0];arms=i['arms']
    assert len({x['base_proposals_sha256'] for x in arms.values()})==1
    assert all(x['attempt_slots']==8 and len(x['attempts'])==8 for x in arms.values())
    assert i['incremental_status']=='NO_INCREMENTAL_STRUCTURAL_EXPRESSIVITY_ON_BOUND'
    new=next(c for c in arms['REAL_TRACE']['candidates'] if c['structural_move'])
    assert new['primitive_reproduction']['cost']==1
    assert new['finite_relation']['status']=='STRONGER_ON_BOUND'
    assert new['finite_relation']['models_checked']==530
    assert new['finite_relation']['different_models']==176
    assert all(c['semantic_alignment_status']=='PROPOSED' for a in arms.values() for c in a['candidates'])
    assert arms['SHAM_ORDER']['provenance_claim']=='SHAM_NOT_EVIDENCE'


@pytest.mark.parametrize('kind',['same','stronger','weaker','incomparable','budget'])
def test_independent_finite_classification(kind):
    b,t=frozen();wide=next(primitive_successors(AST))[0];base=AST;other=wide
    expected={'same':'SAME_ON_BOUND','stronger':'STRONGER_ON_BOUND','weaker':'WEAKER_ON_BOUND','incomparable':'INCOMPARABLE_ON_BOUND','budget':'UNKNOWN_BOUND'}[kind]
    if kind=='same':other=AST
    if kind=='weaker':base,other=wide,AST
    if kind=='incomparable':other={'not':AST}
    bound=copy.deepcopy(P['model_class'])
    if kind=='budget':bound['max_models']=1
    v=relation(base,other,SIG,bound,NO_TICK)
    assert v['status']==expected and v['equivalence_claim']=='UNIVERSAL_EQUIVALENCE_NOT_CLAIMED'
    if kind=='incomparable':assert v['base_true_candidate_false'] and v['base_false_candidate_true']


def test_alpha_capture_and_not_scope_and_sort_rejection():
    successors=list(primitive_successors(AST))
    assert all(typecheck(a,SIG)['status']=='TYPED' for a,_ in successors)
    alpha=next(a for a,op in successors if op['operator']=='ALPHA_RENAME_BINDER')
    assert relation(AST,alpha,SIG,P['model_class'],NO_TICK)['status']=='SAME_ON_BOUND'
    assert all(op['operator']!='SWAP_ADJACENT_OUTER_QUANTIFIERS' for _,op in primitive_successors({'not':AST}))
    bad=copy.deepcopy(AST);bad['body']['var']='x'
    assert typecheck(bad,SIG)['status']=='TYPE_REJECTED' # different types sharing binder
    bad=copy.deepcopy(AST);bad['body']['body']['args'].reverse()
    assert relation(AST,bad,SIG,P['model_class'],NO_TICK)['status']=='UNKNOWN_BOUND'
    out,op=successors[0];step={'primitive':op,'before_ast_sha256':digest(AST),'after_ast_sha256':'0'*64}
    assert not check_primitive_path(AST,out,[step],SIG)


@pytest.mark.parametrize('mutation',['receipt','answer','ast','no_trace','budget','no_base','cap'])
def test_frozen_fail_closed_and_unknown_not_negative(mutation):
    b,t=frozen();p=copy.deepcopy(P)
    if mutation in ('receipt','answer','ast'):
        if mutation=='receipt':b['receipt']['raw_output']='{}'
        if mutation=='answer':b['items'][0]['answer']['unsupported']=['tampered']
        if mutation=='ast':b['items'][0]['answer']['proposals'][0]['formula_json']='{}'
        with pytest.raises(AssuranceError):redecode(b,[0],{'0':[t]},list(ARMS),p)
    elif mutation=='no_trace':
        with pytest.raises(AssuranceError):redecode(b,[0],{},list(ARMS),p)
    elif mutation=='budget':
        p['max_cpu_ms']=0
        r=redecode(b,[0],{'0':[t]},list(ARMS),p)
        assert r['items'][0]['incremental_status']=='UNKNOWN_BOUND'
    elif mutation=='cap':
        # One base fits, but no room for transformation. The ceiling is explicit.
        p['max_candidates_per_source']=1
        r=redecode(b,[0],{'0':[t]},list(ARMS),p)
        assert all(len(a['candidates'])<=1 for a in r['items'][0]['arms'].values())
    else:
        b['items'][0]['answer']['proposals']=[]
        raw=json.dumps({'items':[b['items'][0]['answer']]});b['receipt']['raw_output']=raw
        b['receipt']['raw_output_sha256']=hashlib.sha256(raw.encode()).hexdigest();b['receipt_digest']=digest(b['receipt'])
        b['decoded_sha256']=digest([decode(i['packet'],i['signature'],i['answer'],b['receipt'],[],b['policy']) for i in b['items']])
        r=redecode(b,[0],{'0':[t]},list(ARMS),p)
        assert r['items'][0]['incremental_status']=='NO_BASE_PROPOSALS'


def test_owned_immutable_service_idempotency_replay_and_original_unchanged(tmp_path):
    from lm_suti_assurance.service import Service
    from lm_suti_assurance.symbolic.executor import Executor
    from lm_suti_assurance.symbolic.service import SymbolicService
    from lm_suti_assurance.nl_proposal.service import NLService
    from lm_suti_assurance.workspace import validate_history
    from lm_suti_assurance.white_star import blobs
    pool=Executor();root=tmp_path/'state';base=Service(root);base.new('causal','init');base.new('foreign','init')
    class ExplicitFixtureProvider:
        async def generate(self,request):
            raw=json.dumps({'items':[answer(source())]})
            return {'status':'OK','request':request,'request_sha256':digest(request),'raw_output':raw,'raw_output_sha256':hashlib.sha256(raw.encode()).hexdigest(),'tools_used':0,'usage':{}}
    async def run():
        nl=NLService(root,pool,ExplicitFixtureProvider());s=source()
        ref=(await nl.formal.operation('causal','s','store',{'kind':'source','data':s}))['stored_object_ref']
        a={'source_ref':ref,'target_signature':SIG,'provider':{'kind':'owner_hosted'},'requirements':{},'policy':POLICY}
        begun=await nl.propose('causal','nl',a);await asyncio.gather(*list(nl.tasks))
        original=nl.inspect('causal',begun['run_ref'],'result');assert 'bundle' in original
        req={'schema':'levinmas-white-star-symbolic-request/1','source':{'text':s['text_utf8'],'sha256':s['sha256'],'rights':s['rights'],'edition':'causal-unit','language':'ru','title':'Unit'},'normalization':'none','segmentation':{'unit':'whitespace','record_boundaries':'lines','renaming_scope':'local'},'algebra':{'kind':'FREE','allow_reduce':False,'preserve_history':True},'operators':['REVERSE','SPLIT'],'observers':['literal','alpha_pattern'],'search':{'max_steps':4,'max_candidates_per_step':2,'max_nodes':32,'max_word_tokens':32,'history_identity':'provenance','seed':21,'strategy':'local_structural_novelty'},'task':{'mode':'discover_relations','max_rules':4}}
        sy=await SymbolicService(root,pool).explore('causal','sy',req)
        args={'source_nl_run_ref':begun['run_ref'],'source_item_indices':[0],'structural_run_refs':[{'engine':'symbolic_v1','run_id':sy['run_id']}],'arms':list(ARMS),'policy':P}
        cs=CausalService(root,pool);record=cs.execute('causal','k',args)
        assert cs.execute('causal','k',args)==record
        assert cs.inspect('causal',record['run_ref'],'replay')['status']=='REPLAY_MATCH'
        assert nl.inspect('causal',begun['run_ref'],'result')==original
        with pytest.raises(AssuranceError,match='REQUEST_KEY_CONFLICT'):cs.execute('causal','k',{**args,'arms':['NO_MOVE']})
        with pytest.raises(AssuranceError):cs.execute('foreign','k',args)
        with pytest.raises(AssuranceError):cs.inspect('foreign',record['run_ref'])
        for mutation in ('missing','fake_node','snapshot','foreign_run','changed_ast'):
            bad=copy.deepcopy(args)
            if mutation=='missing':bad['structural_run_refs']=[]
            if mutation=='fake_node':bad['structural_run_refs'][0]['node_refs']=['0'*64]
            if mutation=='snapshot':bad['structural_run_refs'][0]['snapshot_sha256']='0'*64
            if mutation=='foreign_run':bad['structural_run_refs'][0]['run_id']='0'*64
            if mutation=='changed_ast':
                with pytest.raises(AssuranceError):cs.inspect('causal',record['run_ref'],'replay',expected_ast_sha256='0'*64)
                continue
            with pytest.raises(AssuranceError):cs.execute('causal',mutation,bad)
        w=base.workspace('causal');history=w.history()
        assert sum(r['action']=='nl.causal.finish' for r in history)==1
        validate_history(history)
    try:asyncio.run(run())
    finally:pool.close()


def test_cpu_budget_is_per_computation_thread(monkeypatch):
    import lm_suti_assurance.nl_proposal.causal as module
    def forbidden():
        raise AssertionError('process-wide CPU mixes concurrent MCP requests')
    monkeypatch.setattr(module.time, 'process_time', forbidden)
    b,t=frozen()
    assert redecode(b,[0],{'0':[t]},list(ARMS),P)['items'][0]['incremental_status']=='NO_INCREMENTAL_STRUCTURAL_EXPRESSIVITY_ON_BOUND'


def test_finished_without_real_receipt_is_never_reconstructed(tmp_path):
    from lm_suti_assurance.service import Service
    from lm_suti_assurance.nl_proposal.service import NLService
    from lm_suti_assurance.white_star import blobs
    root=tmp_path/'state';service=Service(root);service.new('no-receipt','init')
    # Explicit unit fixture represents an existing provider-unavailable history.
    # No provider or result is fabricated as OK.
    nl=NLService(root,None);w=service.workspace('no-receipt')
    with w.locked():packet_ref,_=blobs.put(w,{'items':[],'policy':POLICY})
    start={'schema':'nl-proposal-run/1','run_ref':'9'*64,'status':'RUNNING','packet_ref':packet_ref,'execution_permission':False}
    nl.finish(w,start,{'status':'PROVIDER_UNAVAILABLE','model_calls':0,'execution_permission':False})
    args={'source_nl_run_ref':start['run_ref'],'source_item_indices':[0],'arms':['NO_MOVE'],'policy':P}
    with pytest.raises(AssuranceError,match='FROZEN_RECEIPT_UNAVAILABLE'):
        CausalService(root).execute('no-receipt','causal',args)
    assert not any(r['action']=='nl.causal.finish' for r in w.history())
