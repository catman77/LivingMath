"""Frozen external proposals, real FOL primitives, and independent certificates."""
import copy,json
from pathlib import Path
import pytest
from lm_suti_assurance.semantic_bridge.contextual.alpha import canonicalize,prove_alpha
from lm_suti_assurance.semantic_bridge.contextual.checker import check_certificate
from lm_suti_assurance.semantic_bridge.contextual.relations import prove_entailment
ROOT=Path(__file__).resolve().parents[1]
PACK=json.loads((ROOT/'docs/SEMANTIC_BRIDGE_PATCH001_20261109/reference/SB_EXP01_FROZEN_INPUT.json').read_text())
H=PACK['hypotheses'];SIG=PACK['signature']


def test_alpha_is_structural_and_has_independent_certificate():
    proof=prove_alpha(H['H0'],H['H2'],SIG)
    assert proof['status']=='PROVED_ALPHA_EQ' and proof['model_enumerations']==0
    assert check_certificate(H['H0'],H['H2'],SIG,proof['certificate'])
    assert prove_alpha(H['H0'],H['H1'],SIG)['status']=='NOT_ALPHA_EQ'
    bad=copy.deepcopy(proof['certificate']);bad['canonical_sha256_left']='0'*64
    assert not check_certificate(H['H0'],H['H2'],SIG,bad)


def test_exact_entailment_has_16_assignments_and_no_converse_claim():
    proof=prove_entailment(H['H1'],H['H0'],SIG)
    assert proof['status']=='PROVED_ENTAILMENT' and proof['certificate']['rows_checked']==16
    assert check_certificate(H['H1'],H['H0'],SIG,proof['certificate'])
    assert prove_entailment(H['H0'],H['H1'],SIG)['status']=='UNKNOWN_NOT_TAUTOLOGY'
    bad=copy.deepcopy(proof['certificate']);bad['rows_checked']=15
    assert not check_certificate(H['H1'],H['H0'],SIG,bad)


@pytest.mark.parametrize('kind',['shadow','unbound','unsupported'])
def test_malformed_ast_does_not_reach_normalizer(kind):
    q=copy.deepcopy(H['H0'])
    if kind=='shadow':q['body']['var']=q['var']
    elif kind=='unbound':q['var']='unbound_replacement'
    else:q={'future':q}
    with pytest.raises(ValueError):canonicalize(q,SIG)


@pytest.fixture
def services(tmp_path):
    from lm_suti_assurance.symbolic.executor import Executor as FormalExecutor,SharedBudget
    from lm_suti_assurance.semantic_bridge.contextual.executor import Executor
    from lm_suti_assurance.semantic_bridge.contextual.service import ContextualService
    from lm_suti_assurance.formal_bridge.service import FormalService
    from lm_suti_assurance.service import Service
    budget=SharedBudget();old=FormalExecutor(shared_budget=budget);new=Executor(budget)
    assert old.status()['ready'] and new.status()['ready']
    Service(tmp_path).new('qa','init');Service(tmp_path).new('foreign','init')
    yield FormalService(tmp_path,old),ContextualService(tmp_path,new)
    new.close();old.close()


def make_arguments(source_ref):
    q=json.loads((ROOT/'docs/SEMANTIC_BRIDGE_PATCH001_20261109/API_EXAMPLES.json').read_text())['register_request_example'];q['source_ref']=source_ref
    return {k:v for k,v in q.items() if k not in ('project','request_key')}


def mk_model(s,c,p,r,world='closed'):
    return {'domains':{'researcher':['r0'],'manager':['m0'],'hypothesis':['h0']},'relations':{'Supervises':[['m0','r0']] if s else [],'Checked':[['r0','h0']] if c else [],'Planned':[['r0','h0']] if p else [],'Reported':[['r0','m0','h0']] if r else []},'world':world}


def test_complete_actual_services_replay_and_context_vector(services):
    import asyncio,base64
    from lm_suti_assurance.core import digest
    from lm_suti_assurance.workspace import validate_history
    formal,sb=services
    async def exercise():
        source=await formal.operation('qa','source','store',{'kind':'source','data':PACK['source']});args=make_arguments(source['stored_object_ref'])
        reg=await sb.operation('qa','register','register',args);assert reg['status']=='COMPLETED' and len(reg['hypothesis_refs'])==5
        before=sb.formal.ext.workspace('qa').history()
        assert (await sb.operation('qa','register','register',args))==reg
        assert sb.formal.ext.workspace('qa').history()==before
        models=[]
        for i,m in enumerate([mk_model(1,1,1,1),mk_model(1,0,0,1),mk_model(1,1,0,0),mk_model(0,0,0,0),mk_model(1,1,1,1,'open')]):
            row=await formal.operation('qa','model'+str(i),'store',{'kind':'model','data':m});models.append(row['stored_object_ref'])
        run=await sb.operation('qa','analyze','analyze',{'batch_ref':reg['batch_ref'],'pairs':[['H0','H2'],['H0','H1'],['H0','H3']],'model_refs':models,'scenario_origin':'HUMAN_PROVIDED'})
        w=sb.formal.ext.workspace('qa');result=sb.result(w,run);edges=result['graph']['relations'];assert all(e['comparison_scope']=='ALL_CANDIDATE_ASSUMPTIONS_HOLD' for e in edges);assert edges[0]['status']=='PROVED_ALPHA_EQ' and edges[0]['model_enumerations']==0
        assert edges[1]['directions']['B_IMPLIES_A']['status']=='PROVED_ENTAILMENT'
        assert edges[2]['status']=='INCOMPARABLE_PROVED_BY_TWO_COUNTERMODELS' and len(edges[2]['countermodels'])==2
        m4=next(v for v in result['scenario_vectors'] if v['client_id']=='H0' and v['model_ref']==models[3]);assert m4['formula_truth']=='TRUE' and m4['assumption_truths'][0]['status']=='FALSE' and m4['applicability']=='CONTEXT_INCOMPATIBLE'
        m5=next(v for v in result['scenario_vectors'] if v['client_id']=='H0' and v['model_ref']==models[4]);assert m5['formula_truth']=='UNKNOWN' and m5['applicability']=='UNKNOWN_CONTEXT'
        assert all(o['status']=='OPEN' for v in result['obligations'] for o in v['items'])
        for row in [reg,run]:assert (await sb.replay('qa',row['run_ref'],row['result_sha256']))['status']=='REPLAY_MATCH'
        chunks=[];offset=0
        while True:
            page=sb.inspect('qa',run['run_ref'],'bundle',offset=offset,limit=1);chunks.append(base64.b64decode(page['data']))
            if page['next_offset'] is None:break
            offset=page['next_offset']
        raw=b''.join(chunks);assert digest(json.loads(raw))==page['sha256'] and json.loads(raw)['result_sha256']==run['result_sha256'];validate_history(w.history())
        assert result['checks']['LLM_calls']==0 and result['source_alignment_status']=='PROPOSED'
    asyncio.run(exercise())


@pytest.mark.parametrize('attack',['source_sha','span','ast_path','source_ref','key_conflict','foreign_source','foreign_batch','foreign_model','inspect','replay','hash_guard'])
def test_ownership_and_negative_requests_do_not_append(services,attack):
    import asyncio
    from lm_suti_assurance.errors import AssuranceError
    formal,sb=services
    async def exercise():
        source=await formal.operation('qa','source','store',{'kind':'source','data':PACK['source']});args=make_arguments(source['stored_object_ref']);reg=await sb.operation('qa','register','register',args)
        foreign=await formal.operation('foreign','model','store',{'kind':'model','data':mk_model(1,1,1,1)})
        before={project:(sb.formal.ext.workspace(project).path/'journal.jsonl').read_bytes() for project in ['qa','foreign']}
        q=copy.deepcopy(args)
        with pytest.raises((AssuranceError,ValueError,UnicodeError)):
            if attack=='source_sha':q['expected_source_sha256']='0'*64;await sb.operation('qa','bad','register',q)
            elif attack=='span':q['hypotheses'][0]['source_links'][0]['byte_utf8'][1]-=1;await sb.operation('qa','bad','register',q)
            elif attack=='ast_path':q['hypotheses'][0]['source_links'][0]['ast_path']=['missing'];await sb.operation('qa','bad','register',q)
            elif attack=='source_ref':q['hypotheses'][0]['source_ref']='0'*64;await sb.operation('qa','bad','register',q)
            elif attack=='key_conflict':q['hypotheses'][0]['construction_trace'][0]['candidate']='rename';await sb.operation('qa','register','register',q)
            elif attack=='foreign_source':await sb.operation('foreign','bad','register',q)
            elif attack=='foreign_batch':await sb.operation('foreign','bad','analyze',{'batch_ref':reg['batch_ref'],'pairs':[],'model_refs':[]})
            elif attack=='foreign_model':await sb.operation('qa','bad','analyze',{'batch_ref':reg['batch_ref'],'pairs':[],'model_refs':[foreign['stored_object_ref']]})
            elif attack=='inspect':sb.inspect('foreign',reg['run_ref'])
            elif attack=='replay':await sb.replay('qa',reg['run_ref'],'0'*64)
            else:sb.inspect('qa',reg['run_ref'],expected_result_sha256='0'*64)
        for project,raw in before.items():assert (sb.formal.ext.workspace(project).path/'journal.jsonl').read_bytes()==raw
    asyncio.run(exercise())


def test_invalid_and_unsupported_hypotheses_are_kept_separate():
    from lm_suti_assurance.semantic_bridge.contextual.engine import register
    q=make_arguments('a'*64);q['hypotheses'][1]['formula_ast']={'future':H['H0']};q['hypotheses'][2]['formula_ast']['var']='broken'
    batch=register({'arguments':q,'source':PACK['source']});assert len(batch['hypotheses'])==5
    assert [h['type_status'] for h in batch['hypotheses']]==['TYPED','TYPE_REJECTED','TYPE_REJECTED','TYPED','LANGUAGE_INSUFFICIENT']
    assert batch['hypotheses'][1]['language_gap']['status']=='OPEN'
    assert len(set(batch['hypothesis_refs'].values()))==5


def test_budget_halt_does_not_become_equivalence():
    from lm_suti_assurance.semantic_bridge.contextual.engine import register,analyze
    q=make_arguments('a'*64);batch=register({'arguments':q,'source':PACK['source']});refs=batch['hypothesis_refs']
    out=analyze({'batch':batch,'pairs':[[refs['H0'],refs['H1']]],'models':[],'budget':{'max_steps':1}})
    assert out['status']=='UNKNOWN_BOUND' and out['halt_reason'] and out['checks']['completed_pairs']==0


def test_proof_fragment_rejects_existential_and_positional_aliases():
    a={'quant':'exists','var':'x','sort':'researcher','body':{'pred':'Checked','args':[{'var':'x'},{'var':'h'}]}}
    # Use valid closed existential formulas, never infer a theorem from bounded agreement.
    a=copy.deepcopy(H['H0']);a['quant']='exists'
    assert prove_entailment(a,H['H0'],SIG)['status']=='UNKNOWN_UNSUPPORTED_PROOF_CLASS'
    assert prove_entailment(H['H1'],H['H0'],SIG,max_atoms=2)['reason']=='ATOM_BOUND'


def test_strict_schema_and_complexity_bomb_rejected():
    from lm_suti_assurance.semantic_bridge.contextual.contracts import validate,guard
    from lm_suti_assurance.errors import AssuranceError
    q=make_arguments('a'*64);q.update(project='qa',request_key='init');validate('semantic_bridge_register',q)
    q['verified']=True
    with pytest.raises(AssuranceError):validate('semantic_bridge_register',q)
    deep={}
    for _ in range(60):deep={'next':deep}
    with pytest.raises(AssuranceError,match='INPUT_COMPLEXITY_BOUND'):guard(deep)


def test_generated_gap_does_not_change_obligation_ids_or_cap():
    from lm_suti_assurance.semantic_bridge.contextual.engine import register
    q=make_arguments('a'*64);h=q['hypotheses'][0];h['formula_ast']={'future':H['H0']}
    h['obligations']=[{'id':'automatic_language_gap' if i==0 else 'o'+str(i),'kind':'CONTEXT','description':'Original open item','status':'OPEN'} for i in range(8)]
    before=copy.deepcopy(h['obligations']);batch=register({'arguments':q,'source':PACK['source']});actual=batch['hypotheses'][0]
    assert actual['obligations']==before and len(actual['obligations'])==8
    assert actual['language_gap']['status']=='OPEN'


def test_alpha_pair_never_calls_finite_enumerator(monkeypatch):
    from lm_suti_assurance.formal_bridge import fol
    from lm_suti_assurance.semantic_bridge.contextual.engine import register,analyze
    def forbidden(*args,**kwargs):raise AssertionError('Alpha pair must short-circuit before enumeration')
    monkeypatch.setattr(fol,'countermodels',forbidden)
    q=make_arguments('a'*64);batch=register({'arguments':q,'source':PACK['source']});refs=batch['hypothesis_refs']
    out=analyze({'batch':batch,'pairs':[[refs['H0'],refs['H2']]],'models':[],'budget':{}})
    assert out['graph']['relations'][0]['status']=='PROVED_ALPHA_EQ' and out['checks']['model_enumerations']==0


@pytest.mark.parametrize('replacement',[False,0.0])
def test_certificate_json_types_are_strict(replacement):
    proof=prove_entailment(H['H1'],H['H0'],SIG)['certificate'];bad=copy.deepcopy(proof)
    found=False
    for atom in bad['atoms']:
        if 0 in atom[-1]:atom[-1][atom[-1].index(0)]=replacement;found=True;break
    assert found and not check_certificate(H['H1'],H['H0'],SIG,bad)


def test_exhausted_evaluation_stops_total_analysis_budget():
    from lm_suti_assurance.semantic_bridge.contextual.relations import Work
    from lm_suti_assurance.formal_bridge.ir import Bound
    sig={'sorts':['s'],'predicates':{'P':['s']}};phi={'pred':'P','args':[{'var':'x0'}]}
    for i in reversed(range(7)):phi={'quant':'forall','var':'x'+str(i),'sort':'s','body':phi}
    model={'world':'closed','domains':{'s':['0','1','2','3']},'relations':{'P':[[str(i)] for i in range(4)]}}
    work=Work({'max_steps':100})
    with pytest.raises(Bound,match='FORMULA_EVALUATION_BOUND'):work.evaluate(phi,sig,model)
    assert work.counter.steps==100
    model['world']='open';assert Work({'max_steps':100}).evaluate(phi,sig,model)['status']=='UNKNOWN'


@pytest.mark.parametrize('case',['unsupported_empty','unsupported_false_context','typed_formula_bad_assumption'])
def test_context_is_independent_of_formula_typing(case):
    from lm_suti_assurance.semantic_bridge.contextual.engine import register
    from lm_suti_assurance.semantic_bridge.contextual.relations import scenario,Work
    q=make_arguments('a'*64)
    if case=='unsupported_false_context':q['hypotheses'][4]['assumptions']=copy.deepcopy(q['hypotheses'][0]['assumptions'])
    if case=='typed_formula_bad_assumption':q['hypotheses'][0]['assumptions']=[{'future':H['H0']}]
    batch=register({'arguments':q,'source':PACK['source']});h=batch['hypotheses'][0 if case=='typed_formula_bad_assumption' else 4]
    v=scenario(h,SIG,mk_model(0,0,0,0),Work({}))
    if case=='unsupported_empty':assert v['formula_truth']=='ILL_TYPED' and v['applicability']=='APPLICABLE' and v['assumption_scope']=='NO_DECLARED_ASSUMPTIONS'
    elif case=='unsupported_false_context':assert v['formula_truth']=='ILL_TYPED' and v['assumption_truths'][0]['status']=='FALSE' and v['applicability']=='CONTEXT_INCOMPATIBLE'
    else:assert v['formula_truth']=='TRUE' and v['assumption_truths'][0]['status']=='UNKNOWN' and v['applicability']=='UNKNOWN_CONTEXT'
