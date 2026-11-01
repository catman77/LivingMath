"""Independent grammatical source proxy. Never imports proposer or target evaluator."""
import re
from .contract import RawPacket


def source_audit(h: dict,packet: RawPacket) -> dict:
    errors=[];catalog={s.id:s for s in packet.spans+packet.context}
    if (h.get('packet_id'),h.get('document_id'),h.get('document_sha256'),h.get('edition'))!=(
        packet.id,packet.document_id,packet.document_sha256,packet.edition):errors.append('SOURCE_HASH_EDITION_OR_PACKET_DRIFT')
    evidence=h.get('quoted_evidence',[])
    if set(h.get('source_spans',[]))!={e.get('span_id') for e in evidence}:errors.append('SOURCE_REFERENCE_LIST_DISAGREES_WITH_QUOTES')
    for e in evidence:
        span=catalog.get(e.get('span_id'))
        if span is None:errors.append('FOREIGN_OR_HIDDEN_SOURCE_REFERENCE');continue
        if e.get('quote')!=span.text or (e.get('start'),e.get('end'))!=(span.start,span.end):errors.append('FAKE_QUOTE_OR_ADDRESS')
    for role in h.get('roles',[]):
        span=catalog.get(role.get('span_id'))
        start=role.get('start',-1);end=role.get('end',-1)
        if span is None or start<span.start or end>span.end or end<=start or span.text.encode()[start-span.start:end-span.start]!=str(role.get('name','')).encode():
            errors.append('ROLE_NOT_RETURNED_TO_QUOTED_EVENT')
    if not evidence or len(h.get('roles',[]))<2:errors.append('INSUFFICIENT_SOURCE_ANCHORS')
    if errors:return {'status':'REJECTED_SOURCE','quotes_valid':False,'reasons':sorted(set(errors)),
                       'semantic_review':'SEMANTIC_NOT_EXTERNALLY_REVIEWED','proof_status':'unverified'}
    text='\n'.join(e['quote'] for e in evidence);claim=h['proposed_relation']['claim']
    supported=False;reason='READING_NOT_JUSTIFIED_BY_BOUNDED_SOURCE_PROXY'
    if claim=='textual_order':
        supported=h['roles'][0]['start']<h['roles'][1]['start'];reason='EXACT_PRINTED_EVENT_ORDER_ONLY'
    elif claim=='process_order':
        reason='PRINTED_ORDER_IS_NOT_A_PROCESS_ORDER_WITNESS'
    elif claim in {'explicit_conditional','unconditional_outcome'}:
        conditional=bool(re.search(r'^\s*(?:if|если)\s+.+,.+',text,re.I))
        supported=conditional if claim=='explicit_conditional' else not conditional
        reason='EXPLICIT_TWO_CLAUSE_CONDITIONAL_IS_NOT_UNCONDITIONAL_OUTCOME'
    elif claim in {'negation_present','affirmation_only'}:
        negative=bool(re.search(r'\b(?:not|no|none|without|never|не|ни|нет)\b',text,re.I))
        supported=negative if claim=='negation_present' else not negative
        reason='POLARITY_CHECKED_IN_ADDRESSABLE_CLAUSES_NOT_WORLD_TRUTH'
    elif claim in {'joint_predication','necessary_implication'}:
        coordinated=bool(re.search(r'\b(?:and|also|и|также)\b',text,re.I)) and len({e['span_id'] for e in evidence})>=2
        conditional=bool(re.search(r'\b(?:if|unless|если)\b',text,re.I))
        supported=coordinated if claim=='joint_predication' else conditional
        reason='COORDINATION_SUPPORTS_COASSERTION_NOT_NECESSITY' if not conditional else 'EXPLICIT_CONDITIONAL_CUE_REQUIRES_ROLE_SCOPE_REVIEW'
    elif claim in {'subject_form_changes','same_subject_form'}:
        left,right=[r['name'] for r in h['roles'][:2]]
        changed=bool(re.match(r'^Ты\b',left,re.I) and re.search(r'^И\s+\w+.*\bтебя\b',right,re.I))
        supported=changed if claim=='subject_form_changes' else not changed
        reason='GRAMMATICAL_SUBJECT_OBJECT_FORM_CHECK_NOT_METAPHOR_COREFERENCE'
    elif claim in {'parallel_word_frames','identical_referents'}:
        left,right=[r['name'].casefold().split() for r in h['roles'][:2]]
        anchors=[i for i,(a,b) in enumerate(zip(left,right)) if a.strip(',.;:')==b.strip(',.;:')]
        supported=claim=='parallel_word_frames' and len(anchors)>=2 and left!=right
        reason='POSITIONAL_WORD_FRAME_ANALOGY_IS_NOT_REFERENT_IDENTITY'
    return {'status':'PROXY_SUPPORTED' if supported else 'REQUIRES_REVIEW','quotes_valid':True,
            'reasons':[reason],'claim':claim,'source_spans':h['source_spans'],
            'semantic_review':'SEMANTIC_NOT_EXTERNALLY_REVIEWED','scope':'Bounded grammatical proxy, not expert adjudication or causal truth.',
            'grade':'B_PROXY','proof_status':'unverified','execution_permission':{'allowed':False}}
