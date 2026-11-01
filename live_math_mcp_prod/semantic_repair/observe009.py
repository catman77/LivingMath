"""Versioned service projection, extending the registered archaic conditional grammar.

Known public-domain calibration is declared in release009 source selection.
No task IDs, desired answers or physical interpretation are consumed.
"""
import copy
import re

from artifact_genesis.contract import RawPacket
from davcore.ast import digest
from .observe import norm
from .observe008 import observe as base


def observe(packet: RawPacket, *, strategy: str='artifact009/1') -> dict:
    if strategy not in {'artifact009/1','artifact009-middle/1'}:raise ValueError('UNREGISTERED_ARTIFACT_OBSERVER')
    old=base(packet,strategy='typed008-middle/1' if strategy=='artifact009-middle/1' else 'typed008/1')
    old.update(base_observer=old['observer'],observer=strategy,observer_implementation_version='artifact-observer009/1')
    spans=sorted(packet.spans+packet.context,key=lambda s:s.start)
    text='\n'.join(s.text for s in spans)
    old['source_coverage_losses']=[{'reason':'QUOTE_CROSSES_SOURCE_WINDOW','source_refs':[s.id for s in spans]}] if text.count('«')!=text.count('»') else []
    by={s.id:s for s in spans}
    for slice_ in old['slices']:
        if slice_['kind']!='TEXTUAL_PROGRESSION':continue
        revised=[]
        for p in slice_['premises']:
            if p['realization']['kind']!='PRESCRIPTION' or len(p['source_refs'])<2 or any('«' in by[r].text or '»' in by[r].text for r in p['source_refs']):
                revised.append(p);continue
            groups=[];group=[]
            for ref in p['source_refs']:
                group.append(ref)
                if re.search(r'[.!?]\s*$',by[ref].text):groups.append(group);group=[]
            if group:groups.append(group)
            if len(groups)==1:revised.append(p);continue
            for refs in groups:
                item=copy.deepcopy(p);label=' '.join(by[r].text for r in refs)
                unit=digest([strategy,refs,label,'addressed-prescription'])
                item.update(id='u_'+unit[:24],premise_unit=unit,source_refs=refs)
                for role in (item['src'],item['dst']):role.update(predicate='p_'+digest(norm(label))[:24],mention_ref=refs[0])
                item['realization'].update(occurrence_id='occ_'+unit[:24],source_order=by[refs[0]].start,label=label)
                revised.append(item)
        slice_['premises']=revised
    for a,b in zip(spans,spans[1:]):
        guard=re.fullmatch(r'(?:For )?when (.+?)[,;.]?',a.text.strip(),re.I)
        transform=re.fullmatch(r'Then into (\w+) the (\w+) shall (?:turned|conuerted|converted) be[,;.]?',b.text.strip(),re.I)
        if not guard or not transform:continue
        section=a.source_address.get('section',packet.document_id)
        scope='s_'+digest([packet.document_sha256,packet.edition,section])[:24]
        g=norm(guard.group(1));refs=[a.id,b.id];roles=[]
        for label in (transform.group(2),transform.group(1)):
            roles.append({'predicate':'p_'+digest(norm(label))[:24],'mention_ref':b.id+':'+norm(label),'scope':scope,
                'stage':g,'modality':'TEXTUAL_CLAIM','domain':'local_domain_'+scope[2:22],'quantifier':'ALL',
                'polarity':'POSITIVE','participant':'scoped_argument','time':'CONDITIONAL_SCHEMA'})
        unit=digest([strategy,refs,roles,g]);p={'id':'u_'+unit[:24],'src':roles[0],'dst':roles[1],
            'relation':'condition','source_refs':refs,'premise_unit':unit,'source_hash':packet.document_sha256,
            'observer_version':'discourse005/1','semantics':'CONDITIONAL','assumptions':['Only under stated textual guard: '+g],
            'realization':{'version':'typed008/1','kind':'GUARDED_TRANSFORMATION','source_order':a.start,
                'occurrence_id':'occ_'+unit[:24],'label':norm(transform.group(2))+' → '+norm(transform.group(1)),
                'guards':[{'id':'guard_'+digest([unit,g])[:20],'text':g,'source_refs':[a.id]}]}}
        old['slices'].append({'kind':'GUARDED_TRANSFORMATION','premises':[p],'dimensions':[
            {'id':'update_mode','values':['ACCUMULATE','REPLACE'],'kind':'interpretation'},
            {'id':'middle_policy','values':['SEPARATE_OCCURRENCES','LINK_LOCAL_ROLE'] if strategy=='artifact009-middle/1'
             else ['SEPARATE_OCCURRENCES'],'kind':'conditional_role_binding'}]})
        old['unparsed_refs']=[r for r in old['unparsed_refs'] if r not in refs]
    return old
