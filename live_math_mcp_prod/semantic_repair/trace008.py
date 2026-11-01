"""Post-compilation DAV questions and separately scoped finite trace certificates."""
from itertools import combinations

from artifact_translation.checker import independent_apply, independent_verdict
from davcore.adapters import Adapter, AdapterSpec
from davcore.ast import Apply, Eq, Formula, Var, digest
from davcore.finite import check
from .compiler import compile_model
from .realization import PROFILE, observe_state


def adapter(model: dict) -> Adapter:
    if model['status']!='COMPILED_CONDITIONAL_MODEL' or model['profile']!=PROFILE:
        raise ValueError('FROZEN_TYPED_MODEL_REQUIRED')
    return Adapter(AdapterSpec.model_validate(model['spec']))


def questions(model: dict) -> list[dict]:
    """Only the frozen model is received. Source predictions cannot enter here."""
    a=adapter(model);out=[];x=Var();n=len(model['premise_ids'])
    def app(op,t=x):return Apply(operation=op,argument=t)
    def add(kind,left,right,**extras):
        f=Formula(body=Eq(left=left,right=right))
        body={'kind':kind,'model_hash':model['compiled_hash'],'profile':model['profile'],
            'observer_version':model['observer_version'],'formula':f.canonical_ast(),**extras}
        out.append({**body,'id':'qt_'+digest(body)[:24]})
    for j in range(n):
        for i in range(a.width):add('PERSISTENCE',app('S'+str(i),app('R'+str(j))),app('S'+str(i)),coordinate=i,operation_ids=[model['premise_ids'][j]])
    for i,j in combinations(range(n),2):
        add('ORDER',app('R'+str(j),app('R'+str(i))),app('R'+str(i),app('R'+str(j))),operation_ids=[model['premise_ids'][i],model['premise_ids'][j]])
        add('ROUND_TRIP_EQUALITY_ONLY',app('R'+str(j),app('R'+str(i))),x,operation_ids=[model['premise_ids'][i],model['premise_ids'][j]])
    return out


def certify(premises: list[dict], binding: dict, model: dict, q: dict, *, context=None) -> dict:
    if compile_model(premises,binding,profile=PROFILE,context=context)!=model:
        raise ValueError('STALE_OR_SUBSTITUTED_TYPED_MODEL')
    if q not in questions(model):raise ValueError('FORMULA_PROFILE_OBSERVER_SUBSTITUTION')
    body={'profile':PROFILE,'observer_version':model['observer_version'], 'source_hashes':model['source_hashes'],
        'premises_hash':digest(premises),'binding':binding,'model_hash':model['compiled_hash'],'query':q,
        'boundary':'Target theorem does not verify source binding or its physical interpretation.'}
    return {**body,'seal':digest(body)}


def evaluate(premises: list[dict], binding: dict, model: dict, certificate: dict, *, states=None, context=None) -> dict:
    expected=certify(premises,binding,model,certificate['query'],context=context)
    if certificate!=expected:raise ValueError('STALE_SOURCE_TARGET_CONTRACT')
    a=adapter(model);f=Formula.model_validate(certificate['query']['formula'])
    assert a.spec.reaction_network is not None
    result=check(a,f,states=states)
    # Reference checker receives the original full formula, no source support.
    independent=independent_verdict(a.spec.reaction_network,f)
    if states is None and independent['status']!=result['status']:
        raise ValueError('INDEPENDENT_DAV_DISAGREEMENT')
    return {'query_id':certificate['query']['id'],'model_hash':model['compiled_hash'],
        'contract_seal':certificate['seal'],'classification':'ENCODING_CHECK','dav':result,
        'independent':independent,'source_claim_verified':False,'proof_status':'unverified'}


def trace(model: dict, state: int, operations: list[str]) -> dict:
    a=adapter(model);n=a.spec.reaction_network
    assert n is not None
    if not a.valid_state(state):raise ValueError('INVALID_TRACE_INITIAL_STATE')
    start=state;steps=[]
    for pid in operations:
        if pid not in model['premise_ids']:raise ValueError('FOREIGN_SOURCE_OPERATION')
        i=model['premise_ids'].index(pid);enabled=bool(a.apply('E'+str(i),state))
        after=a.apply('R'+str(i),state)
        if after!=independent_apply(n,'R'+str(i),state):raise ValueError('INDEPENDENT_TRACE_DISAGREEMENT')
        fired=enabled and after!=state and pid not in model['disabled_premises']
        steps.append({'source_operation_id':pid,'operation':'R'+str(i),'enabled':enabled,
            'fired':fired,'before':state,'after':after,'before_observation':observe_state(model,state),
            'after_observation':observe_state(model,after),
            'identity_is_not_event':after==state,'source_relation_ids':n.reactions[i].source_relation_ids})
        state=after
    body={'model_hash':model['compiled_hash'],'initial_state':start,'registered_initial':start in model['initial_states'],
        'steps':steps,'final_state':state,'final_observation':observe_state(model,state),
        'all_steps_fired':bool(steps) and all(s['fired'] for s in steps),
        'actual_round_trip':len(steps)>=2 and all(s['fired'] for s in steps) and state==start,
        'scope':'FINITE_DECLARED_TRACE_NOT_FULL_STATE_THEOREM', 'classification':'MODEL_DERIVATION',
        'source_claim_verified':False,'proof_status':'unverified'}
    return {**body,'trace_id':'tr_'+digest(body)[:24]}


def study_model(model: dict) -> dict:
    """All reachable markings from registered initials, plus all full-state ops.

    Full-state checks never filter away counterexamples. Reachability invariants
    carry their initial set and all reaction successors separately.
    """
    a=adapter(model);ids=model['premise_ids'];reachable=set(model['initial_states']);front=list(reachable)
    assert a.spec.reaction_network is not None
    while front:
        state=front.pop()
        for i in range(len(ids)):
            after=a.apply('R'+str(i),state)
            if after not in reachable:reachable.add(after);front.append(after)
    tables={pid:[a.apply('R'+str(i),x) for x in a.states()] for i,pid in enumerate(ids)}
    traces=[trace(model,s,ids) for s in model['initial_states']]
    orders: list[dict]=[]
    rounds: list[dict]=[]
    for i,j in combinations(range(len(ids)),2):
        for s in sorted(reachable):
            left=trace(model,s,[ids[i],ids[j]]);right=trace(model,s,[ids[j],ids[i]])
            if left['final_state']!=right['final_state'] and not orders:orders.append({'forward':left,'reverse':right})
            for t in (left,right):
                if t['actual_round_trip']:rounds.append(t)
    invariants={}
    if model['observer']['kind']=='TEXTUAL_PROGRESSION':
        invariants={'single_cursor':all(isinstance(observe_state(model,s)['read_prefix'],int) for s in reachable),
            'no_performance_attested':all(observe_state(model,s)['performance']=='UNKNOWN' for s in reachable)}
    elif model['observer']['kind']=='GUARDED_TRANSFORMATION':
        gs=model['observer']['guard_coordinates']
        invariants={'guards_conserved':all(all(((s>>g)&1)==((a.apply('R'+str(i),s)>>g)&1) for g in gs)
            for s in a.states() for i in range(len(ids)))}
    return {'model_hash':model['compiled_hash'],'traces':traces,'order_witnesses':orders,
        'real_round_trips':rounds,'round_trip_search':{'states':sorted(reachable),'operation_pairs':'BOTH_ORDERS_ALL_DISTINCT_PAIRS'},
        'full_state_count':len(a.states()),'all_operations_independently_replayed':all(
            a.apply(op,s)==independent_apply(a.spec.reaction_network,op,s) for s in a.states() for op in a.ops),
        'reachable_scope':{'initial_states':model['initial_states'],'states':sorted(reachable),
            'successor_closed':all(a.apply('R'+str(i),s) in reachable for s in reachable for i in range(len(ids)))},
        'invariants':invariants,'operation_table_sha256':digest(tables),
        'outcome':'HAS_ENABLED_TRACE' if any(t['all_steps_fired'] for t in traces) else 'NO_ENABLED_COMPLETE_TRACE',
        'classification':'MODEL_DERIVATION','source_support':'CONDITIONAL_RECONSTRUCTION',
        'fresh_transfer':'NOT_RUN','physical_realization':'NOT_ESTABLISHED'}


def compare(left: dict, right: dict) -> dict:
    """Align actions by source operation IDs, observations by source roles.

    Cross-dimension state vocabularies are not comparable by integer bit pattern.
    Such cases compare registered traces, explicitly conditional on initial maps.
    """
    a=adapter(left);b=adapter(right)
    assert a.spec.reaction_network is not None and b.spec.reaction_network is not None
    same_coords=[s.id for s in a.spec.reaction_network.species]==[s.id for s in b.spec.reaction_network.species]
    common=sorted(set(left['premise_ids'])&set(right['premise_ids']));witness=None
    if same_coords:
        for s in a.states():
            for pid in common:
                x=a.apply('R'+str(left['premise_ids'].index(pid)),s);y=b.apply('R'+str(right['premise_ids'].index(pid)),s)
                if x!=y or observe_state(left,x)!=observe_state(right,y):
                    witness={'state':s,'source_operation_id':pid,'outputs':[x,y],
                        'observations':[observe_state(left,x),observe_state(right,y)]};break
            if witness:break
        kind='DISTINGUISHING_EXECUTION_OR_OBSERVER' if witness else 'EXHAUSTIVE_TARGET_PROJECTION_EQUIVALENCE'
    else:
        ls=study_model(left);rs=study_model(right)
        witness={'initial_mapping':'FIRST_INPUT_PRESENT_AND_SAME_ADDRESSED_GUARD_VALUATIONS',
            'left_traces':ls['traces'],'right_traces':rs['traces'],
            'enabled_complete_trace':[ls['outcome'],rs['outcome']]}
        kind='REGISTERED_TRACE_DIFFERENCE' if ls['outcome']!=rs['outcome'] else 'DIFFERENT_COORDINATE_SORT_NO_EQUIVALENCE_ASSERTED'
    return {'models':[left['compiled_hash'],right['compiled_hash']],'kind':kind,'witness':witness,
        'same_coordinate_sort':same_coords,'states_checked':len(a.states()) if same_coords else None,
        'common_source_operations':common,'scope':'This model/observer/action vocabulary only; never global semantic equivalence.'}
