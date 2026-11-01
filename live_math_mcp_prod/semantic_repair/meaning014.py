"""Bounded source-interpretation families; no semantic oracle or new operations."""
import hashlib
from copy import deepcopy

from davcore.adapters import Adapter, AdapterSpec
from davcore.ast import digest, eq, implication
from davcore.finite import Meter, witness
from davcore.models import Budget

from .inference011 import canonical_packet
from .meaning014_contract import SourceProposals014, SourceReview014


def semantic_signature(reading: dict) -> str:
    """Ignore IDs/labels, retain actual source coordinates and asserted relations."""
    r=deepcopy(reading)
    names={s['id']:'s'+str(i) for i,s in enumerate(r['states'])}
    names.update({s['id']:'r'+str(i) for i,s in enumerate(r['relations'])})
    observers={p['id']:'o'+str(i) for i,p in enumerate(r['observers'])}
    for s in r['states']:s['id']=names[s['id']];s.pop('label',None)
    for relation in r['relations']:
        relation['id']=names[relation['id']]
        relation['src']=names.get(relation['src'],relation['src']);relation['dst']=names.get(relation['dst'],relation['dst'])
        relation.pop('interpretation_note',None)
        c=relation['source_claim'];c['observer_id']=observers.get(c['observer_id'],c['observer_id'])
    for p in r['observers']:
        p['id']=observers[p['id']]
        for s in p['samples']:s['state_id']=names[s['state_id']]
    r['initial_state_ids']=[names[x] for x in r['initial_state_ids']];r.pop('id');r.pop('unknowns',None)
    return digest(r)


def source_list_witnesses(packet: dict) -> list[dict]:
    """Literal comma-list projections from source bytes, never world predicates.

    Adjacent comma-bearing lines form one list. No dictionary, case/task IDs or
    semantic labels are used. Case/punctuation normalization is explicit.
    """
    groups=[];current: list[dict]=[]
    for span in packet['spans']:
        text=span['text']
        if ',' not in text:
            if current:groups.append(current);current=[]
            continue
        offset=0
        for part in text.split(','):
            stripped=part.strip().strip('.;:!?—– ')
            if stripped:
                index=text.find(stripped,offset);lo=span['start']+len(text[:index].encode())
                current.append({'value':stripped.casefold(),'quote':stripped,'ref':span['id'],
                    'byte_ranges':[[lo,lo+len(stripped.encode())]],'normalization':'UNICODE_CASEFOLD_AND_EDGE_PUNCTUATION_ONLY'})
            offset+=len(part)+1
    if current:groups.append(current)
    out=[]
    for i,left in enumerate(groups):
        for right in groups[i+1:]:
            x=[a['value'] for a in left];y=[a['value'] for a in right];shared=sorted(set(x)&set(y))
            if len(shared)<2:continue
            a=Adapter(AdapterSpec(kind='gate6'));formula=implication('P','One','Q','One')
            marking=int(bool(shared))+2*int(x==y)
            checked=witness(a,formula,marking,Meter(Budget()))
            out.append({'left':left,'right':right,'shared_literal_features':shared,'sequence_equal':x==y,
                'added_literal_features':sorted(set(y)-set(x)), 'scope':'ACTUAL_ADDRESSED_LITERAL_COMMA_LISTS_ONLY; NOT_WORLD_IDENTITY_OR_CAUSALITY',
                'discriminator':'Does equality on these shared literal features imply equality of the full ordered listings?',
                'conditional_counterexample':{'marking':marking,'formula':formula.canonical_ast(),'actual_relation':checked['actual_relation']},
                'source_basis_ablations':[{'withdrawn_source_list':side,'countermodel':{'unobserved_listing_can_equal_the_other':True,'completion_is_not_a_source_assignment':True},'effect':'SEQUENCE_NONIDENTITY_NO_LONGER_FORCED_BY_OBSERVED_LISTS'} for side in ['left','right']],
                'source_verified':False,'world_truth':'UNKNOWN','independent_semantic_validation':False})
    return out


def family(packet: dict, proposals: dict, review: dict | None = None) -> dict:
    p=SourceProposals014.model_validate(proposals).model_dump()
    r=SourceReview014.model_validate(review).model_dump() if review else None
    canonical,mapping=canonical_packet(packet);spans={s['id']:s for s in canonical['spans']+canonical['context']}
    readings={h['id']:h for h in p['readings']};audits={x['contrast_id']:x for x in r['contrasts']} if r else {}
    if len(audits)!=(len(r['contrasts']) if r else 0) or set(audits)-{c['id'] for c in p['contrasts']}:raise ValueError('FOREIGN_OR_DUPLICATE_CONTRAST_REVIEW')
    if r and any(x['reading_id'] not in readings for x in r['issues']):raise ValueError('FOREIGN_SOURCE_REPAIR_ISSUE')
    def exact(c):return c['ref'] in spans and bool(c['quote']) and c['quote'] in spans[c['ref']]['text']
    def address(c):
        s=spans[c['ref']];start=0;ranges=[]
        while (pos:=s['text'].find(c['quote'],start))>=0:
            lo=s['start']+len(s['text'][:pos].encode());ranges.append([lo,lo+len(c['quote'].encode())]);start=pos+1
        return {'ref':mapping[c['ref']],'quote':c['quote'],'byte_ranges':ranges,'quote_sha256':hashlib.sha256(c['quote'].encode()).hexdigest(),'ambiguous_occurrence':len(ranges)!=1}
    questions=[];losses=[];finite=[];ablations=[]
    for c in p['contrasts']:
        if c['left_prediction']==c['right_prediction'] or semantic_signature(readings[c['left_reading']])==semantic_signature(readings[c['right_reading']]):
            losses.append({'contrast_id':c['id'],'reason':'NON_DISCRIMINATING_OR_COSMETIC_FAMILY'});continue
        if not all(exact(x) for x in c['evidence']):losses.append({'contrast_id':c['id'],'reason':'NOT_SUPPORTED_QUOTE'});continue
        audit=audits.get(c['id']);audited=bool(audit and audit['evidence'] and all(exact(x) for x in audit['evidence']))
        status=audit['status'] if audit is not None and audited else 'SEMANTIC_DISPUTED'
        if status=='NOT_SUPPORTED':losses.append({'contrast_id':c['id'],'reason':'SOURCE_CRITIC_REJECTED_CONTRAST','source_critic':audit});continue
        addresses=[address(x) for x in c['evidence']]
        q={'id':'q_'+digest([packet['document_sha256'],c])[:24],'contrast_id':c['id'],'dimension':c['dimension'],
            'question':c['observable'],'readings':[c['left_reading'],c['right_reading']],
            'predictions':[c['left_prediction'],c['right_prediction']], 'differing_assumption':c['differing_assumption'],
            'source_addresses':addresses,'witness_needed':c['witness_needed'],'quote_status':'EXACT_SPAN',
            'semantic_status':status,'evaluator_origin':'SAME_FAMILY_SOURCE_CRITIC' if audited else 'SOURCE_PROPOSER_ONLY',
            'source_review':audit,'source_verified':False,'world_truth':'UNKNOWN','validation_scope':'RECONSTRUCTION_ONLY; SOURCE_KNOWN_BEFORE_COMMIT',
            'gain_status':'DECLARED_FORECAST_DIFFERENCE_NOT_A_NEW_SOURCE_DISCOVERY','actual_source_winner':None}
        questions.append(q)
        # This is a forecast encoding, not a source-theorem: no Q inserted in a
        # Network, and no source adjudication inferred from a successful vector.
        if 'UNKNOWN' not in q['predictions']:
            a=Adapter(AdapterSpec(kind='gate6'));formula=eq('P','One');meter=Meter(Budget());rows=[]
            for h,v in zip(q['readings'],q['predictions']):
                marking=int(v=='TRUE');checked=witness(a,formula,marking,meter)
                if checked['actual_relation']!=(marking==1):raise ValueError('FORECAST_FINITE_REFERENCE_DISAGREEMENT')
                rows.append({'reading':h,'marking':marking,'actual_relation':checked['actual_relation']})
            finite.append({'question_id':q['id'],'formula':formula.canonical_ast(),'rows':rows,
                'scope':'DECLARED_H_FORECAST_ENCODING_ONLY; NOT_INDEPENDENT_SOURCE_VALIDATION','novel_source_claim':False})
        for a in addresses:
            ablations.append({'question_id':q['id'],'withdrawn_source_address':a,
                'before':'SOURCE_REVIEW_RELIANCE_ON_CITED_BASIS','after':'BASIS_WITHDRAWN; BOTH_INTERPRETATIONS_REMAIN_POSSIBLE',
                'countermodel':{'adopt_withdrawn_source_claim':False,'alternative_reading_possible':True},
                'scope':'Epistemic withdrawal of cited support, not deletion of original source bytes or independent semantic proof',
                'necessity_status':'NOT_INDEPENDENTLY_ESTABLISHED'})
    claim_ledger=[]
    assessed={(x['reading_id'],x['relation_id']):x for x in (r['assessments'] if r else [])}
    for h in p['readings']:
        for relation in h['relations']:
            assessment=assessed.get((h['id'],relation['id']))
            claim_ledger.append({'reading':h['id'],'relation':relation['id'],'claim':relation,
                'claim_status':'HYPOTHESIS' if assessment and assessment['status']=='HYPOTHESIS' else 'UNKNOWN',
                'review_status':assessment['status'] if assessment else 'UNKNOWN',
                'semantic_status':'SEMANTIC_DISPUTED' if assessment and assessment['status']=='CONFLICT' else 'SOURCE_READING_NOT_VERIFIED',
                'status_origin':'FALLIBLE_SOURCE_LLM_REVIEW; NOT_WORLD_REFUTATION',
                'quote_status':'EXACT_SPAN' if all(exact(x) for x in relation['evidence']) else 'NOT_SUPPORTED',
                'source_verified':False})
    return {'version':'meaning014/1','source_sha256':packet['document_sha256'],'baseline_A0':p['readable_model'],
        'baseline_A0_sha256':digest(p['readable_model']),'source_claim_ledger':claim_ledger,'forbidden_inferences':['REPORT_TO_WORLD_FACT','EQUALITY_TO_RETURN','PROJECTION_TO_FULL_IDENTITY','TEXT_ORDER_TO_CAUSALITY','NO_OBSERVATION_TO_NEGATIVE'],
        'hypothesis_family':p['readings'],'family_sha256':digest(p),
        'status':'UNRESOLVED_WITH_DISCRIMINATOR' if questions else 'FAIL_NON_DISCRIMINATING_FAMILY',
        'literal_source_witnesses':source_list_witnesses(packet),'questions':questions,'formal_witnesses':finite,'source_premise_ablations':ablations,'losses':losses,
        'source_grounding':'SOURCE_GROUNDING_NOT_ESTABLISHED','source_verified':False,'proof_status':'unverified',
        'execution_permission':{'allowed':False},'independent_source_validations':0,
        'semantic_delta_vs_A_B':'UNMEASURED_WITHOUT_INDEPENDENT_GOLD','recommended_primary_workflow':'B_PLUS','experimental':True}


def render(product: dict) -> list[str]:
    lines=['# Полная исходная формализация A0',product['baseline_A0'],'',
        '# Экспериментальная проверка альтернатив',product['status'],
        'A0 сохранена без исправлений. SOURCE_GROUNDING_NOT_ESTABLISHED; world truth UNKNOWN; разрешения нет.']
    if product.get('primary_B_plus'):
        primary=product['primary_B_plus']
        lines.append('Основная независимая проверка B+: '+primary['status']+'; source truth не устанавливается.')
        for model in primary.get('finite_models',[]):
            for t in model['actual_fired_cycles']:lines.append('B+: условная симуляция объявленных отображений: '+str(len(t['steps']))+' fired steps; хронология и разрешённость источником не утверждаются; physical execution UNKNOWN.')
        for q in primary.get('observation_checks',[]):lines.append('B+: наблюдатель '+q['observer']+': '+q['verdict']+'; только адресованные записи.')
    if product.get('C_delta'):lines.append('Изменения кандидата: '+str(product['C_delta']))
    for w in product.get('literal_source_witnesses',[]):
        lines += ['Адресованные общие лексические признаки: '+', '.join(w['shared_literal_features']),
            'Равенство полных порядков: '+str(w['sequence_equal'])+'; новые детали: '+', '.join(w['added_literal_features']),
            'Это буквальная проекция перечислений; тождество мира и исполнение из неё не следуют.']
    for q in product['questions']:
        lines += [q['question'],'Прогнозы '+str(dict(zip(q['readings'],q['predictions']))),
            'Различающее допущение: '+q['differing_assumption'],'Нужное свидетельство: '+q['witness_needed'],
            'Проверка цитат: '+q['quote_status']+'; смысловая оценка: '+q['semantic_status']+' ('+q['evaluator_origin']+').']
    return lines
