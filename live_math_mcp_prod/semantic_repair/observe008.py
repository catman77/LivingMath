"""Addressed projections of the existing raw observer; no task, question or verdict input.

These registered grammars were developed on known texts. Reading order is not
physical causation, and candidate coreference remains a conditional assumption.
"""
import copy
import re

from artifact_genesis.contract import RawPacket
from davcore.ast import digest
from .observe import norm
from .observe005 import observe as clauses
from .alignment import observe as frames

STRATEGIES = ('typed008/1', 'typed008-middle/1')


def observe(packet: RawPacket, *, strategy: str = STRATEGIES[0]) -> dict:
    if strategy not in STRATEGIES:
        raise ValueError('UNREGISTERED_TYPED_OBSERVER')
    old = clauses(packet, strategy='discourse005/1')
    spans = sorted(packet.spans + packet.context, key=lambda s:s.start)
    by = {s.id:s for s in spans}
    section = spans[0].source_address.get('section',packet.document_id) if spans else packet.document_id
    scope = 's_' + digest([packet.document_sha256,packet.edition,section])[:24]

    def event(label, refs, kind, *, base=None, role=None, direction=None, sign=None, actor=None):
        order = min(by[r].start for r in refs)
        r = role or {'predicate':'p_'+digest(norm(label))[:24], 'mention_ref':refs[0],
            'scope':scope,'stage':'SCHEMATIC','modality':'LYRICAL_CLAIM' if sign else 'PRESCRIPTION',
            'domain':'local_domain_'+scope[2:22],'quantifier':'NAMED_CASE','polarity':sign or 'POSITIVE',
            'participant':actor or 'UNRESOLVED_LOCAL_PARTICIPANT','time':'TEXTUAL_OCCURRENCE'}
        p = copy.deepcopy(base) if base else {'relation':'condition','source_hash':packet.document_sha256,
            'observer_version':'discourse005/1','semantics':'UNKNOWN','assumptions':[]}
        p.update(src=copy.deepcopy(r),dst=copy.deepcopy(r),source_refs=refs)
        p['realization']={'version':'typed008/1','kind':kind,'guards':[], 'source_order':order,
            'occurrence_id':'occ_'+digest([packet.document_sha256,refs,kind,label])[:24],
            'label':label,'direction':direction,'sign':sign,'actor':actor}
        p['id']='u_'+digest([base and base['id'],p['realization'],refs])[:24]
        p['premise_unit']=digest([p['id'],refs]);return p

    slices=[]; guarded=[]; narrative=[]; limitations=[]
    for p in old['premises']:
        if p['semantics']=='CONDITIONAL' and p['src']['stage']!='SCHEMATIC':
            item=copy.deepcopy(p);text=p['src']['stage']
            refs=[r for r in p['source_refs'] if norm(text) in norm(by[r].text)]
            # Guard references remain addressed even if normalization is partial.
            refs=refs or list(p['source_refs'])
            item['realization']={'version':'typed008/1','kind':'GUARDED_TRANSFORMATION',
                'source_order':min(by[r].start for r in p['source_refs']),
                'occurrence_id':'occ_'+digest([p['id'],'typed008'])[:24],
                'label':old['labels'][p['src']['predicate']]+' → '+old['labels'][p['dst']['predicate']],
                'guards':[{'id':'guard_'+digest([p['id'],text,refs])[:20],'text':text,'source_refs':refs}]}
            guarded.append(item)
        elif p['semantics']=='NARRATIVE_SEQUENCE':
            refs=sorted(p['source_refs'],key=lambda r:by[r].start)
            for key,ref in zip(('src','dst'),refs):
                narrative.append(event(old['labels'][p[key]['predicate']],[ref],
                    'NARRATIVE_OCCURRENCE',base=p,role=p[key]))
    if guarded:
        slices.append({'kind':'GUARDED_TRANSFORMATION','premises':guarded,'dimensions':[
            {'id':'update_mode','values':['ACCUMULATE','REPLACE'],'kind':'interpretation'},
            {'id':'middle_policy','values':['SEPARATE_OCCURRENCES','LINK_LOCAL_ROLE'] if strategy==STRATEGIES[1]
             else ['SEPARATE_OCCURRENCES'],'kind':'conditional_role_binding'}]})

    # Finite registered imperative vocabulary, over source spans rather than a
    # named poem. Consecutive imperative lines form one addressed utterance.
    commands=[]
    imperative=r'\b(?:восстань|виждь|внемли|исполнись|жги|повели|скажи|иди|слушай|must|command)\b'
    group=[]; quoted_command=False
    for s in spans:
        if re.search(imperative,s.text,re.I) or quoted_command:
            group.append(s)
            quoted_command=(quoted_command or '«' in s.text) and '»' not in s.text
            if '»' in s.text:
                commands.append(group);group=[]
        elif group:
            commands.append(group);group=[]
    if group:commands.append(group)
    for group in commands:
        narrative.append(event(' '.join(s.text.strip() for s in group),[s.id for s in group],'PRESCRIPTION'))
    if narrative:
        slices.append({'kind':'TEXTUAL_PROGRESSION','premises':sorted(narrative,key=lambda p:p['realization']['source_order']),
            'dimensions':[{'id':'narrative_referent','values':['CONTINUED_SUBJECT','OTHER_PARTICIPANT'],'kind':'referent'},
                {'id':'story_time','values':['NARRATED_ORDER','PHYSICAL_TIME_UNKNOWN'],'kind':'time'}]})

    aligned=frames(packet,strategy='alignment-context007/1')
    forward=[f for f in aligned['frames'] if f['direction']=='FORWARD']
    back=[f for f in aligned['frames'] if f['direction']=='BACK_TO_ADDRESSEE']
    for f in forward:
        # One local stimulus branch per slice. Other list members are separate
        # slices, never silently discarded or identified with this one.
        refs=f['source_refs'];ordered=sorted(refs,key=lambda r:by[r].start)
        ps=[event(f['stimulus'],ordered,'SIGNED_ASSERTION',direction='INCOMING',sign=f['input_polarity'],actor=f['stimulus_actor']),
            event(f['output'],ordered,'SIGNED_ASSERTION',direction='FORWARD',sign=f['polarity'],actor=f['actor'])]
        for b in back:
            if b['scope']==f['scope'] and b['actor']==f['actor']:
                ps.append(event(b['output'],b['source_refs'],'SIGNED_ASSERTION',direction=b['direction'],sign=b['polarity'],actor=b['actor']))
        slices.append({'kind':'SIGNED_RESPONSE','premises':ps,'frame':f,'dimensions':[
            {'id':'response_subject','values':['CONTINUED_SUBJECT','OTHER_PARTICIPANT'],'kind':'conditional_coreference'}]})
    if not slices:limitations.append('NO_TYPED_REALIZATION_IN_REGISTERED_GRAMMAR; legacy observations retained.')
    return {'observer':strategy,'source_packet':packet.model_dump(),'legacy_observation':old,
        'slices':slices,'labels':old['labels'],'analogy_boundaries':aligned['analogy_boundaries'],
        'unparsed_refs':sorted(set(by)-{r for s in slices for p in s['premises'] for r in p['source_refs']}),
        'losses':limitations+['Reading cursor denotes source presentation, not material or physiological state.',
            'Coreference, update interpretation and cross-guard role binding remain HYPOTHESES.',
            'No global invariant follows by joining separate slices.'],
        'query_received':False,'model_proof_received':False,'authorship':'CODE_AGENT_KNOWN_SOURCE_ENGINEERING'}
