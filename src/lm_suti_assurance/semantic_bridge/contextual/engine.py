"""Pure deterministic contextual checks. No model generation, network or semantics."""
from pathlib import Path
from ...core import digest,byte_digest
from ...formal_bridge import fol
from ...formal_bridge.ir import Bound
from .contracts import source_bindings
from .relations import Work,pair,scenario


def binding():
    root=Path(__file__).parent;formal=root.parents[1]/'formal_bridge'
    return digest({'contextual':{n:byte_digest((root/n).read_bytes()) for n in ['contracts.py','alpha.py','checker.py','relations.py','engine.py']},'formal':{n:byte_digest((formal/n).read_bytes()) for n in ['fol.py','ir.py']}})


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
    batch=payload['batch'];signature=batch['target_signature'];budget=payload.get('budget',{});work=Work(budget);lookup={h['hypothesis_ref']:h for h in batch['hypotheses']};edges=[];vectors=[];halt=None
    try:
        for left,right in payload['pairs']:
            work.tick();edges.append(pair(lookup[left],lookup[right],signature,budget,work))
        for model in payload['models']:
            fol.check_model(model['model'],signature)
            for h in batch['hypotheses']:
                work.tick();vectors.append({'model_ref':model['model_ref'],'model_sha256':digest(model['model']),'scenario_origin':model['origin'],**scenario(h,signature,model['model'],work)})
    except Bound as e:halt=str(e)
    graph={'nodes':[{'hypothesis_ref':h['hypothesis_ref'],'client_id':h['client_id'],'type_status':h['type_status']} for h in batch['hypotheses']],'relations':edges,'hypotheses_merged':False}
    return {'schema':'semantic-bridge-analysis/1','status':'UNKNOWN_BOUND' if halt else 'CHECKED','halt_reason':halt,'graph':graph,'scenario_vectors':vectors,'scenarios':payload['models'],'obligations':[{'hypothesis_ref':h['hypothesis_ref'],'client_id':h['client_id'],'items':h['obligations']} for h in batch['hypotheses']],'checks':{'formal_contrast_calls':sum(x['formal_contrast_calls'] for x in edges),'model_enumerations':work.models,'total_steps':work.counter.steps,'requested_pairs':len(payload['pairs']),'completed_pairs':len(edges),'requested_scenario_cells':len(payload['models'])*len(batch['hypotheses']),'completed_scenario_cells':len(vectors),'kernel_binding':binding(),'semantic_adjudication':'NOT_EVALUATED','LLM_calls':0,'network_calls':0,'execution_permission':False},'source_alignment_status':'PROPOSED','LLM_calls':0,'execution_permission':False}


def dispatch(packet):
    action=packet['operation'];payload=packet['payload']
    if action=='register':return register(payload)
    if action=='analyze':return analyze(payload)
    raise ValueError('INVALID_CONTEXTUAL_OPERATION')
