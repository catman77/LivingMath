"""Ground value/mask/binding metadata against the immutable source window."""
import hashlib
from copy import deepcopy

from davcore.ast import digest

from .inference011 import canonical_packet
from .observe012 import align as align012
from .observer013_contract import ObserverInference
from .relations013 import SourceProposals013, SourceReview013, legacy


def align(packet,proposals,review,*,assurance='REAL_LLM_SOURCE_PROPOSER'):
    proposed=SourceProposals013.model_validate(proposals)
    reviewed=SourceReview013.model_validate(review) if review else None
    old=legacy(proposed)
    old_review={'version':'source-critic012/1','assessments':[a.model_dump() for a in reviewed.assessments],'losses':reviewed.losses} if reviewed else None
    result=align012(packet,old,old_review,assurance=assurance)
    canonical,mapping=canonical_packet(packet);spans={s['id']:s for s in canonical['spans']+canonical['context']}
    audits={(a.reading_id,a.observer_id):a for a in reviewed.observations} if reviewed else {}
    if reviewed and len(audits)!=len(reviewed.observations):raise ValueError('DUPLICATE_OBSERVATION_REVIEW')
    known={(h.id,p.id) for h in proposed.readings for p in h.observers}
    if set(audits)-known:raise ValueError('FOREIGN_OBSERVER_REVIEW')
    def exact(cs):return bool(cs) and all(c.ref in spans and c.quote in spans[c.ref]['text'] for c in cs)
    def addresses(cs):
        out=[]
        for c in cs:
            if not exact([c]):continue
            text=spans[c.ref]['text'];start=0;positions=[]
            while (i:=text.find(c.quote,start))>=0:
                a=spans[c.ref]['start']+len(text[:i].encode());positions.append([a,a+len(c.quote.encode())]);start=i+1
            out.append({'ref':mapping[c.ref],'quote_sha256':hashlib.sha256(c.quote.encode()).hexdigest(),
                'byte_ranges':positions,'ambiguous_occurrence':len(positions)!=1})
        return out
    by_reading={h.id:h for h in proposed.readings}
    for sl in result['slices']:
        if sl['kind']!='STATE_TRANSITION' or not sl['premises']:continue
        ps=sl['premises'];first=ps[0]['realization']['transition'];reading_id=next(h.id for h in proposed.readings if first['source']['key'].startswith(h.id+':'))
        h=by_reading[reading_id];profiles=[]
        for p in h.observers:
            audit=audits.get((h.id,p.id));ground=bool(audit and audit.status in {'HYPOTHESIS','CONFLICT'} and audit.explicit_values_checked and audit.binding_time_scope_checked and exact(audit.evidence) and exact(p.evidence))
            samples=[]
            for sample in p.samples:
                values={}
                for v in sample.values:
                    supported=ground and (all(exact(c.evidence) for c in v.conflicts) if v.status=='CONFLICT' else v.status=='UNKNOWN' or (audit.status=='HYPOTHESIS' and exact(v.evidence)))
                    status=v.status if supported else 'UNKNOWN'
                    values[v.feature]={'status':status,'value':v.value if status in {'KNOWN','EXPLICIT_NEGATIVE'} else None,
                        'addresses':addresses(v.evidence),'conflicts':[{'value':c.value,'negative':c.negative,'addresses':addresses(c.evidence)} for c in v.conflicts] if status=='CONFLICT' else []}
                    if not supported and v.status!='UNKNOWN':result['source_coverage_losses'].append({'reason':'UNCONFIRMED_OBSERVATION013','observer':p.id,'feature':v.feature,'addresses':addresses(v.evidence)})
                bound=ground and exact(sample.binding_evidence)
                samples.append({'state_key':h.id+':'+sample.state_id,'values':{f:values.get(f,{'status':'UNKNOWN','value':None,'conflicts':[],'addresses':[]}) for f in p.features},
                    'scope':sample.scope if bound else None,'time':sample.time if bound else None,'referent':sample.referent if bound else None,
                    'binding_addresses':addresses(sample.binding_evidence)})
            profiles.append({'id':h.id+':'+p.id,'owner':p.owner,'features':p.features,'criterion':p.criterion,
                'source_status':audit.status if ground else 'UNKNOWN','addresses':addresses(p.evidence),'samples':samples})
        kept={p['realization']['transition']['source_claim']['id']:p['realization']['transition'] for p in ps}
        reports=[]
        old_h=next(x for x in old['readings'] if x['id']==h.id)
        for original,r in zip(h.relations,old_h['relations']):
            key='claim_'+digest([packet['document_sha256'],h.id,r])[:24]
            if key not in kept:continue
            d=kept[key];c=original.source_claim
            reports.append({'id':key,'observer_id':d['source_claim']['observer_id'],'speaker':c.speaker,'source':d['source']['key'],'target':d['target']['key'],
                'comparison':c.comparison,'reported_value':c.reported_value if d['critic_status']=='HYPOTHESIS' else 'UNKNOWN',
                'scope':c.comparison_scope,'time':c.comparison_time,'addresses':d['source_claim']['addresses']})
        info=ObserverInference.model_validate({'version':'observer-inference013/1','source_sha256':packet['document_sha256'],'profiles':profiles,'reports':reports}).model_dump()
        first['inference']=info
        refs={a['ref'] for p in profiles for a in p['addresses']}
        for p in profiles:
            for s in p['samples']:
                refs.update(a['ref'] for a in s['binding_addresses'])
                for v in s['values'].values():
                    refs.update(a['ref'] for a in v['addresses'])
                    refs.update(a['ref'] for c in v['conflicts'] for a in c['addresses'])
        ps[0]['source_refs']=sorted(set(ps[0]['source_refs'])|refs)
        for p in ps:
            body=deepcopy(p);body.pop('id',None);body.pop('premise_unit',None);unit=digest(body);p.update(id='u_'+unit[:24],premise_unit=unit)
    result.update(observer='observer013/1',source_proposals=proposals,source_critic=review,source_semantics='ADDRESSED_CONDITIONAL_OBSERVER_INFERENCE_NOT_WORLD_TRUTH')
    return result
