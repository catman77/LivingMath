"""Pure deterministic contextual checks. No model generation, network or semantics."""
from pathlib import Path
from ...core import digest,byte_digest
from ...formal_bridge import fol
from ...formal_bridge.ir import Bound
from .contracts import source_bindings
from .relations import Work,compare_pairs,scenario


def binding():
    root=Path(__file__).parent;formal=root.parents[1]/'formal_bridge'
    return digest({'contextual':{n:byte_digest((root/n).read_bytes()) for n in ['contracts.py','alpha.py','checker.py','relations.py','proofs.py','finite.py','resources.py','engine.py']},'formal':{n:byte_digest((formal/n).read_bytes()) for n in ['fol.py','ir.py']}})


def register(payload):
    args,source=payload['arguments'],payload['source'];source_bindings(args,source);signature=args['target_signature'];fol.signature(signature);hypotheses=[]
    for supplied in args['hypotheses']:
        h={**supplied,'schema':'contextual-hypothesis/1','source_ref':args['source_ref'],'source_sha256':source['sha256'],'signature_sha256':digest(signature),'creator':supplied.get('creator','imported'),'creator_status':'UNVERIFIED_DECLARATION','source_alignment_status':'PROPOSED','semantic_adjudication':'NOT_EVALUATED','execution_permission':False}
        typed=fol.typecheck(h['formula_ast'],signature) if 'formula_ast' in h else {'status':'LANGUAGE_INSUFFICIENT','reason':h['unsupported']['reason']}
        checks=[fol.typecheck(a,signature) for a in h['assumptions']]
        obligations=[fol.typecheck(o['assumption_ast'],signature) for o in h['obligations'] if 'assumption_ast' in o]
        status=typed['status']
        if any(c['status']!='TYPED' for c in checks+obligations):status='TYPE_REJECTED'
        if status!='TYPED':
            h['language_gap']={'status':'OPEN','reason':typed.get('reason','Invalid assumption or obligation AST; external revision required'),'source_links':h['source_links'],'input_obligations_preserved':True}
        h.update(type_status=status,typecheck=typed,assumption_typechecks=checks,obligation_typechecks=obligations)
        if status=='LANGUAGE_INSUFFICIENT':h['source_alignment_status']='LANGUAGE_INSUFFICIENT'
        h['hypothesis_ref']=digest(h);hypotheses.append(h)
    return {'schema':'semantic-bridge-batch/1','source_ref':args['source_ref'],'source_sha256':source['sha256'],'source':source,'target_signature':signature,'hypotheses':hypotheses,'hypothesis_refs':{h['client_id']:h['hypothesis_ref'] for h in hypotheses},'rejected_or_unsupported':[{'client_id':h['client_id'],'status':h['type_status'],'typecheck':h['typecheck'],'assumption_typechecks':h['assumption_typechecks'],'obligation_typechecks':h['obligation_typechecks'],**({'language_gap':h['language_gap']} if 'language_gap' in h else {})} for h in hypotheses if h['type_status']!='TYPED'],'semantic_adjudication':'NOT_EVALUATED','LLM_calls':0,'execution_permission':False}


def analyze(payload):
    batch = payload['batch']
    signature = batch['target_signature']
    budget = payload.get('budget', {})
    work = Work(budget)
    lookup = {h['hypothesis_ref']: h for h in batch['hypotheses']}
    edges, halt = compare_pairs([(lookup[a], lookup[b]) for a, b in payload['pairs']], signature, budget, work, len(payload['models']) * len(batch['hypotheses']))
    vectors = []
    try:
        for model in payload['models']:
            fol.check_model(model['model'], signature)
            for h in batch['hypotheses']:
                work.tick()
                vectors.append({'model_ref': model['model_ref'], 'model_sha256': digest(model['model']),
                                'scenario_origin': model['origin'], **scenario(h, signature, model['model'], work)})
    except Bound as exc:
        halt = str(exc)
    requested = len(payload['pairs']) * 2
    completed = sum(e['summary']['completed'] for e in edges)
    coverage = {'requested': requested, 'completed': completed, 'undecided': requested - completed}
    scenario_requested = len(payload['models']) * len(batch['hypotheses'])
    if halt and not any(e['proof_phase_completed'] for e in edges) and requested and not completed:
        status = 'UNKNOWN_BOUND'
    elif coverage['undecided']:
        status = 'CHECKED_WITH_OPEN_DIRECTIONS'
    elif len(vectors) < scenario_requested:
        status = 'UNKNOWN_BOUND'
    else:
        status = 'CHECKED'
    graph = {'nodes': [{'hypothesis_ref': h['hypothesis_ref'], 'client_id': h['client_id'], 'type_status': h['type_status']} for h in batch['hypotheses']],
             'relations': edges, 'hypotheses_merged': False}
    return {'schema': 'semantic-bridge-analysis/1', 'status': status, 'halt_reason': halt, 'graph': graph,
            'scenario_vectors': vectors, 'scenarios': payload['models'],
            'obligations': [{'hypothesis_ref': h['hypothesis_ref'], 'client_id': h['client_id'], 'items': h['obligations']} for h in batch['hypotheses']],
            'checks': {'formal_contrast_calls': sum(e['formal_contrast_calls'] for e in edges),
                       'model_enumerations': work.models, 'model_count_scope': 'UNIQUE_CLOSED_WORLDS_SHARED_ACROSS_ALL_PAIRS',
                       'enumeration_order': 'size 1 then 2; sorted sorts, predicates, tuples; False before True',
                       'total_steps': work.counter.steps, 'requested_pairs': len(edges),
                       'completed_pairs': sum(e['summary']['undecided'] == 0 for e in edges),
                       'prepared_pairs': sum(e['proof_phase_completed'] for e in edges),
                       'directional_coverage': coverage,
                       'requested_scenario_cells': scenario_requested, 'completed_scenario_cells': len(vectors),
                       'kernel_binding': binding(), 'semantic_adjudication': 'NOT_EVALUATED', 'LLM_calls': 0,
                       'network_calls': 0, 'execution_permission': False},
            'source_alignment_status': 'PROPOSED', 'LLM_calls': 0, 'execution_permission': False}


def dispatch(packet):
    action=packet['operation'];payload=packet['payload']
    if action=='register':return register(payload)
    if action=='analyze':return analyze(payload)
    raise ValueError('INVALID_CONTEXTUAL_OPERATION')
