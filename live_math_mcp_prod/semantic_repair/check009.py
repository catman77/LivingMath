"""Bounded server checker; existing DAV AST/reference and trace semantics only."""
from .compiler import compile_model
from .realization import PROFILE
from .trace008 import certify, evaluate, questions, study_model, trace


def check_model(premises: list[dict], binding: dict, model: dict, context) -> dict:
    context.require(binding['project'],premises)
    if compile_model(premises,binding,profile=PROFILE,context=context)!=model:
        raise ValueError('STALE_ARTIFACT_MODEL_CONTRACT')
    if model['observer']['kind'] == 'SOURCE_SEMANTICS012':
        from .check012 import check_semantics
        return check_semantics(premises, binding, model, context)
    analysis=study_model(model);qs=questions(model)
    general = model['observer']['kind'] == 'SOURCE_TRANSITION'
    if general:
        from .check011 import analyze
        analysis.update(analyze(model))
    selected=[q for q in qs if q['kind']=='PERSISTENCE'][:2]
    for kind in ('ORDER','ROUND_TRIP_EQUALITY_ONLY'):
        selected+=next(([q] for q in qs if q['kind']==kind),[])
    checked=[]
    for q in selected:
        contract=certify(premises,binding,model,q,context=context)
        result=evaluate(premises,binding,model,contract,context=context)
        result['dav'].pop('evaluation_trace',None)
        # Reference truth vector is already exhaustively compared; keep the
        # concrete first counterexample and exact count, not repeated vectors.
        xs=result['independent'].pop('counterexample_states')
        result['independent'].update(counterexample_count=len(xs),first_counterexample=xs[0] if xs else None)
        checked.append({'contract':contract,'result':result})
    deletions=[];good=next((t for t in analysis['traces'] if t['all_steps_fired']),None)
    if good:
        for p in premises:
            deleted=compile_model(premises,binding,profile=PROFILE,context=context,disabled=(p['id'],))
            neg=trace(deleted,good['initial_state'],model['premise_ids'])
            deletions.append({'kind':'SOURCE_UNIT_DELETION','source_operation_id':p['id'],'source_refs':p['source_refs'],
                'trace':neg,'changed':neg['final_state']!=good['final_state'] and not neg['all_steps_fired']})
        for g in model['guards']:
            neg=trace(model,good['initial_state']&~(1<<g['coordinate']),model['premise_ids'])
            deletions.append({'kind':'GUARD_ABSENT','guard':g,'trace':neg,'changed':not neg['all_steps_fired']})
    if general:
        from .check011 import ablations
        deletions = ablations(premises, binding, model, context)
    return {'model_hash':model['compiled_hash'],'analysis':analysis,'checked':checked,'deletions':deletions,
        'query_count':len(qs),'query_generation':'AFTER_MODEL_FREEZE','source_status':'HYPOTHESIS',
        'source_claim_verified':False,'proof_status':'unverified','execution_permission':{'allowed':False}}
