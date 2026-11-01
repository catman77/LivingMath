"""One bounded meaning investigation in the existing artifact Journal/lifecycle."""
from copy import deepcopy
from datetime import UTC, datetime

from davcore.ast import digest
from semantic_repair.inference011 import canonical_packet
from semantic_repair.meaning014 import family, render
from semantic_repair.meaning014_contract import review013, source013
from semantic_repair.meaning014_reference import check as baseline_check
from semantic_repair.observe011 import symbolic_fallback
from semantic_repair.observe013 import align


def filtered_review(original: dict, repaired: dict, review: dict) -> dict:
    """A repair cannot inherit source approval for changed claims or bindings."""
    r=deepcopy(review);old={h['id']:h for h in original['readings']};new={h['id']:h for h in repaired['readings']}
    def same(field,key,ident):
        h=key[0]
        if h not in old or h not in new:return False
        a=next((x for x in old[h][field] if x['id']==ident),None);b=next((x for x in new[h][field] if x['id']==ident),None)
        return a is not None and a==b and old[h]['states']==new[h]['states']
    r['assessments']=[a for a in r['assessments'] if same('relations',(a['reading_id'],),a['relation_id'])]
    r['observations']=[a for a in r['observations'] if same('observers',(a['reading_id'],),a['observer_id'])]
    unchanged={c['id'] for c in repaired['contrasts'] if c in original['contrasts']}
    r['contrasts']=[x for x in r['contrasts'] if x['contrast_id'] in unchanged]
    r['issues']=[x for x in r['issues'] if x['reading_id'] in new]
    r['losses']+=['Changed source mappings are not independently re-reviewed after the single repair.']
    return r


async def observe(controller, case: dict, state: dict, packet: dict, action: dict, context) -> dict:
    from .semantic011 import inference_call
    context.require(case['project'])
    if packet['document_sha256']!=context.public()['sha256']:raise ValueError('FOREIGN_MEANING_SOURCE')
    key=f"meaning014:{case['id']}:g{state['generation']}:view{state['source_reads']}"
    identity={'source':context.public(),'packet':packet,'coordinator_binding':controller.binding}
    existing=controller.service.store.repeated(case['project'],key+':checkpoint',identity)
    if existing:return existing
    def record(kind,suffix,payload):
        return controller.journal.append(case['project'],kind,key+':'+suffix,identity,
            {'case_id':case['id'],'generation':state['generation'],'source_context':context.public(),
                'coordinator_binding':controller.binding,'at_UTC':datetime.now(UTC).isoformat(),**payload})
    proposal=await inference_call(controller,case,state,'proposer014',packet,context)
    initial=proposal.get('output') if proposal['status']=='OK' else None
    readable=initial['readable_model'] if initial else proposal.get('preserved_readable_A0')
    baseline=record('artifact_baseline_A0','A0',{'readable_model':readable,'A0_sha256':digest(readable),
        'provider_binding':getattr(controller.semantic_provider,'fingerprint',None),'source_only_receipt':proposal,
        'backend_reason':proposal.get('reason'),
        'status':'A0_PRESERVED' if readable else 'COST_BOUND' if 'BOUND' in str(proposal.get('reason','')) else 'SOURCE_BACKEND_FAILED_NO_A0','A0_immutable':True})
    review=None;current=initial;product=None
    canonical,_=canonical_packet(packet)
    if initial:record('artifact_baseline_check','B-initial',{'arm':'B','check':baseline_check(initial,canonical)})
    if initial:
        commit=record('artifact_interpretation_commit','H-before-review',{'frozen_candidates':initial,'H_sha256':digest(initial),
            'baseline_A0_id':baseline['id'],'source_access':'OPEN_RECONSTRUCTION; whole source already visible',
            'selected_question_sent_to_critic':False,'H_frozen_before_question':True})
        product=family(packet,initial)
        record('artifact_discriminator','questions-before-review',{'H_commit_id':commit['id'],'questions':product['questions'],
            'source_access':'RECONSTRUCTION_ONLY','predictions_sealed_before_critic':True})
        critique=await inference_call(controller,case,state,'critic014',packet,context,proposals=initial)
        if critique['status']=='OK':
            review=critique['output'];record('artifact_source_adjudication','review',{'review':review,'commit_id':commit['id'],
                'evaluator_origin':'SAME_FAMILY_SOURCE_LLM_NOT_INDEPENDENT_GOLD'})
            try: family(packet,initial,review)
            except ValueError as exc:
                record('artifact_source_adjudication','rejected-review',{'status':'REJECTED_REVIEW_BINDING','reason':str(exc)[:1000]})
                review=None
            if review and review['issues']:
                repair=await inference_call(controller,case,state,'repair014',packet,context,proposals=initial,feedback={'issues':review['issues']})
                if repair['status']=='OK':
                    current=repair['output'];review=filtered_review(initial,current,review)
                    record('artifact_interpretation_revision','one-repair',{'previous_family_sha256':digest(initial),
                        'current_family_sha256':digest(current),'baseline_A0_id':baseline['id'],
                        'repaired_candidates':current,'source_review_of_unchanged_parts':review,
                        'changed_mappings_require_review':True,'old_A0_and_H_retained':True,'repair_count':1})
        assert current is not None
        primary=baseline_check(current,canonical,review)
        baseline_result=record('artifact_baseline_check','B-plus-final',{'arm':'B_PLUS','check':primary,'baseline_A0_id':baseline['id']})
        product=family(packet,current,review)
        product.update(primary_B_plus=primary,baseline_check_record_id=baseline_result['id'])
        # The original full A0 is immutable, even if a repair has a shorter account.
        product['C_delta']={'candidate_changed':digest(current)!=digest(initial), 'baseline_A0_rewritten':False,
            'mapping_repair_scope':'Only unchanged claims retain prior review; changed mappings remain unreviewed',
            'semantic_gain':'UNMEASURED; not inferred from finite tables'}
        product.update(baseline_A0=readable,baseline_A0_sha256=digest(readable),baseline_A0_record_id=baseline['id'])
        try:
            observed=align(packet,source013(current),review013(review) if review else None,
                assurance=getattr(controller.semantic_provider,'assurance','UNSPECIFIED_SOURCE_BACKEND'))
        except ValueError as exc:
            observed=symbolic_fallback(packet);observed['source_coverage_losses'].append({'reason':'MEANING_MAPPING_REQUIRES_REVIEW','detail':str(exc)[:1000]})
    else:
        observed=symbolic_fallback(packet)
    observed.update(observer='meaning014/1',meaning_product=product,baseline_A0_record_id=baseline['id'],
        model_provider_binding=getattr(controller.semantic_provider,'fingerprint',None),
        model_calls_contain_only_source=True,source_claim_verified=False)
    return record('artifact_checkpoint','checkpoint',{'action':'observe','result':observed})


def products(controller, project: str, case_id: int) -> list[dict]:
    rows=controller.journal.rows(('artifact_checkpoint',),project,case_id=case_id)
    return [r['payload']['result']['meaning_product'] for r in rows if r['payload']['result'].get('meaning_product')]


def summary(controller, case: dict) -> dict:
    baselines=controller.journal.rows(('artifact_baseline_A0',),case['project'],case_id=case['id'])
    ps=products(controller,case['project'],case['id'])
    return {'source_backend_statuses':[{'status':r['payload']['status'],'reason':r['payload'].get('backend_reason')} for r in baselines],
        'baseline_A0_refs':[{'record_id':r['id'],'sha256':r['payload']['A0_sha256'],'available':bool(r['payload']['readable_model'])} for r in baselines],
        'meaning_statuses':[p['status'] for p in ps],'source_grounding':'SOURCE_GROUNDING_NOT_ESTABLISHED',
        'primary_workflow':'B_PLUS','C_status':'EXPERIMENTAL','source_verified':False,'independent_source_validations':0}


def readable(controller, project: str, case_id: int) -> list[str]:
    ps=products(controller,project,case_id)
    if ps:return [line for p in ps for line in render(p)]
    rows=controller.journal.rows(('artifact_baseline_A0',),project,case_id=case_id)
    return ['# Полная исходная формализация A0',*[r['payload']['readable_model'] or r['payload']['status']+': '+str(r['payload'].get('backend_reason')) for r in rows],
        'Typed formalization unavailable; original readable A0 retained in append-only export.']
