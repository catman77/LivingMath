"""Bounded raw grammatical proposer, not an LLM or a universal semantic parser.

No dataset IDs, source nouns, editor graphs, target formulas or evaluator imports.
"""
import re
from typing import Any
from davcore.ast import digest
from .contract import RawPacket


def _words(text):return re.findall(r"[\w]+",text.casefold())


def _quote(span):return {'span_id':span.id,'start':span.start,'end':span.end,'quote':span.text}


def _role(span,index):
    return {'id':'role_'+digest([span.id,index])[:20],'name':span.text.strip(),'kind':'event',
            'span_id':span.id,'start':span.start,'end':span.end}


def propose(packet: RawPacket,max_h: int=12) -> dict:
    if not 1<=max_h<=12:raise ValueError('HYPOTHESIS_BUDGET')
    rows=packet.spans;all_rows=packet.context+rows;out=[]
    def pair(family,a,b,kind,claim,alternative,features):
        roles=[_role(a,0),_role(b,1)];evidence=[_quote(a)] if a.id==b.id else [_quote(a),_quote(b)]
        base={'packet_id':packet.id,'document_id':packet.document_id,'document_sha256':packet.document_sha256,
            'edition':packet.edition,'source_spans':[e['span_id'] for e in evidence],'quoted_evidence':evidence,'roles':roles,
            'family':family,'argument':{'basis':features,'falsifier':'Different source wording/scope/agent or an explicit counterreading.'},
            'alternatives':[{'reading':alternative,'same_evidence':True}],
            'predicted_unseen_relation':None,'counterevidence':[],'confidence_status':'UNVERIFIED',
            'target_binding':None,'proposer':'NO_LLM_SEMANTIC_PROPOSER','grade':'B_HYPOTHESIS_NOT_F',
            'proof_status':'unverified','execution_permission':{'allowed':False}}
        for asserted in [claim,alternative]:
            h={**base,'proposed_relation':{'kind':kind,'src':roles[0]['id'],'dst':roles[1]['id'],'claim':asserted,
                 'scope':'SOURCE_TEXT_NOT_PHYSICAL_CAUSALITY'},'alternatives':[{'reading':alternative if asserted==claim else claim,'same_evidence':True}]}
            h['hypothesis_id']=digest(h);out.append(h)
    if len(rows)>=2:
        pair('order_condition',rows[0],rows[-1],'order','textual_order','process_order',
             ['Exact printed positions of two addressed events','Narrative succession alone need not establish process time'])
    for span in rows:
        match=re.match(r'^\s*(?:If|Если)\s+(.+?),\s*(.+?)[.!]?$',span.text,re.I)
        if not match:continue
        roles=[]
        for i in [1,2]:
            a,b=match.span(i);roles.append({'id':'role_'+digest([span.id,a,b])[:20],'name':span.text[a:b],
                'kind':'event','span_id':span.id,'start':span.start+len(span.text[:a].encode()),
                'end':span.start+len(span.text[:b].encode())})
        for claim in ['explicit_conditional','unconditional_outcome']:
            h={'packet_id':packet.id,'document_id':packet.document_id,'document_sha256':packet.document_sha256,
                'edition':packet.edition,'source_spans':[span.id],'quoted_evidence':[_quote(span)],'roles':roles,
                'family':'order_condition','proposed_relation':{'kind':'condition','src':roles[0]['id'],'dst':roles[1]['id'],
                    'claim':claim,'scope':'SOURCE_TEXT_NOT_PHYSICAL_CAUSALITY'},
                'argument':{'basis':['Conditional syntax with two independently addressed clauses'],
                            'falsifier':'Missing antecedent or changed conditional/subject scope'},
                'alternatives':[{'reading':'unconditional_outcome' if claim=='explicit_conditional' else 'explicit_conditional','same_evidence':True}],
                'predicted_unseen_relation':None,'counterevidence':[],'confidence_status':'UNVERIFIED','target_binding':None,
                'proposer':'NO_LLM_SEMANTIC_PROPOSER','grade':'B_HYPOTHESIS_NOT_F','proof_status':'unverified','execution_permission':{'allowed':False}}
            h['hypothesis_id']=digest(h);out.append(h)
    negatives=set(packet.grammar.get('negation',[])) or ({'not','no','none','without','never'} if packet.language=='en' else {'не','ни','нет'})
    neg=next((s for s in rows if negatives.intersection(_words(s.text))),None)
    if neg:
        other=next((s for s in rows if s.id!=neg.id),neg)
        pair('negation_subject',neg,other,'contrast','negation_present','affirmation_only',
             ['A negative grammatical marker is inside a cited clause','Its subject and polarity must not be promoted to a physical fact'])
    coordination=set(packet.grammar.get('coordination',[])) or ({'and','also'} if packet.language=='en' else {'и','также'})
    joint=next((s for s in rows if coordination.intersection(_words(s.text))),None)
    if joint:
        index=all_rows.index(joint);previous=all_rows[max(0,index-1)]
        if previous.id!=joint.id:
            pair('joint_analogy',previous,joint,'conjunction','joint_predication','necessary_implication',
                 ['A coordination marker joins two distinct quoted clauses','Co-assertion does not establish necessary implication'])
    # Pronoun/object case and an explicit noun phrase support an agency alternative, not coreference truth.
    if packet.language=='ru':
        actor=next((s for s in rows if re.match(r'^\s*И\s+\w+.*\bтебя\b',s.text,re.I)),None)
        if actor:
            previous=next((s for s in all_rows if re.match(r'^\s*Ты\b',s.text,re.I)),all_rows[0])
            pair('negation_subject',previous,actor,'role','subject_form_changes','same_subject_form',
                 ['Explicit subject-pronoun form in one clause','Noun phrase and object-pronoun form in another clause'])
    # Propose an analogy from two raw parallel clauses, without asserting referent identity.
    for span in rows:
        if ',' not in span.text:continue
        comma=span.text.index(',');ranges=[(0,comma),(comma+1,len(span.text))]
        if any(len(span.text[a:b].split())<3 for a,b in ranges):continue
        roles=[]
        for i,(a,b) in enumerate(ranges):
            while a<b and span.text[a].isspace():a+=1
            roles.append({'id':'role_'+digest([span.id,a,b])[:20],'name':span.text[a:b],'kind':'event',
                          'span_id':span.id,'start':span.start+len(span.text[:a].encode()),'end':span.start+len(span.text[:b].encode())})
        for claim in ['parallel_word_frames','identical_referents']:
            h={'packet_id':packet.id,'document_id':packet.document_id,'document_sha256':packet.document_sha256,
                'edition':packet.edition,'source_spans':[span.id],'quoted_evidence':[_quote(span)],'roles':roles,
                'family':'joint_analogy','proposed_relation':{'kind':'repeat','src':roles[0]['id'],'dst':roles[1]['id'],
                   'claim':claim,'scope':'SOURCE_TEXT_NOT_PHYSICAL_CAUSALITY'},
                'argument':{'basis':['Two separately addressed clauses may instantiate a common relational frame'],
                    'falsifier':'No shared positional anchors, or no independent justification for identifying referents'},
                'alternatives':[{'reading':'identical_referents' if claim=='parallel_word_frames' else 'parallel_word_frames','same_evidence':True}],
                'predicted_unseen_relation':None,'counterevidence':[],'confidence_status':'UNVERIFIED','target_binding':None,
                'proposer':'NO_LLM_SEMANTIC_PROPOSER','grade':'B_HYPOTHESIS_NOT_F','proof_status':'unverified','execution_permission':{'allowed':False}}
            h['hypothesis_id']=digest(h);out.append(h)
    unique: dict[str,dict[str,Any]]={}
    for h in out:
        key=digest({'spans':h['source_spans'],'relation':h['proposed_relation'],'roles':[r['name'] for r in h['roles']]})
        unique.setdefault(key,h)
    return {'hypotheses':list(unique.values())[:max_h],'search_status':'SEARCH_EXHAUSTED',
        'bounded_space':'Order/process, polarity, joint/necessity and subject-form alternatives in these raw clauses only.',
        'proposer_status':'NO_LLM_SEMANTIC_PROPOSER','semantic_review':'SEMANTIC_NOT_EXTERNALLY_REVIEWED',
        'generated_before_budget':len(unique),'budget':max_h,'editor_relations_received':False}
