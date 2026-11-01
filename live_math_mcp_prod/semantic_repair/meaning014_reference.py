"""Independent stdlib B/B+ checker; same source/A0/critic data, no LivingMath imports."""
import json
from copy import deepcopy


def check(proposal: dict, source: dict, review: dict | None = None) -> dict:
    spans={s['id']:s['text'] for s in source['spans']+source.get('context',[])}
    def exact(cs):return bool(cs) and all(c['ref'] in spans and c['quote'] and c['quote'] in spans[c['ref']] for c in cs)
    issues=[];qs=[];forecasts=[]
    readings={h['id']:h for h in proposal.get('readings',[])}
    audits={x['contrast_id']:x for x in (review or {}).get('contrasts',[])}
    def signature(h):
        h=deepcopy(h);nodes={s['id']:'s'+str(i) for i,s in enumerate(h['states'])};nodes.update({s['id']:'r'+str(i) for i,s in enumerate(h['relations'])});obs={x['id']:'o'+str(i) for i,x in enumerate(h['observers'])}
        h.pop('id');h.pop('unknowns',None)
        for s in h['states']:s['id']=nodes[s['id']];s.pop('label',None)
        for r in h['relations']:
            r['id']=nodes[r['id']];r['src']=nodes.get(r['src'],r['src']);r['dst']=nodes.get(r['dst'],r['dst']);r.pop('interpretation_note',None);c=r['source_claim'];c['observer_id']=obs.get(c['observer_id'],c['observer_id'])
        for p in h['observers']:
            p['id']=obs[p['id']]
            for s in p['samples']:s['state_id']=nodes[s['state_id']]
        h['initial_state_ids']=[nodes[x] for x in h['initial_state_ids']]
        return json.dumps(h,sort_keys=True,separators=(',',':'))
    for h in readings.values():
        for r in h['relations']:
            if not exact(r['evidence']+r['source_claim']['evidence']):issues.append({'kind':'UNADDRESSED_SOURCE_RELATION','reading':h['id'],'relation':r['id']})
    for c in proposal.get('contrasts',[]):
        if c['left_reading'] not in readings or c['right_reading'] not in readings:issues.append({'kind':'FOREIGN_H'});continue
        if c['left_prediction']==c['right_prediction'] or signature(readings[c['left_reading']])==signature(readings[c['right_reading']]):continue
        if not exact(c['evidence']):issues.append({'kind':'NOT_SUPPORTED_QUOTE','id':c['id']});continue
        audit=audits.get(c['id'])
        if audit and exact(audit['evidence']) and audit['status']=='NOT_SUPPORTED':continue
        qs.append({'question':c['observable'],'dimension':c['dimension'],'readings':[c['left_reading'],c['right_reading']],
            'predictions':[c['left_prediction'],c['right_prediction']],'witness_needed':c['witness_needed'],'actual_source_winner':None,
            'source_grounding':'SOURCE_GROUNDING_NOT_ESTABLISHED','semantic_accuracy':None})
        if 'UNKNOWN' not in [c['left_prediction'],c['right_prediction']]:
            values=[c['left_prediction']=='TRUE',c['right_prediction']=='TRUE']
            forecasts.append({'contrast':c['id'],'truth_vector':values,'different':values[0]!=values[1],
                'scope':'Declared forecasts only, no source oracle'})
    return {'status':'INDEPENDENT_STDLIB_CHECKED','questions':qs,'forecast_tables':forecasts,'issues':issues,
        'source_verified':False,'execution_grant':False,'semantic_accuracy':None,
        'literal_source_witnesses':literal_lists(source),'finite_models':finite_models(proposal,review),'observation_checks':observation_checks(proposal,source)}


def literal_lists(source: dict) -> list[dict]:
    """Independent literal source-list projection; no subject/world interpretation."""
    groups=[];group: list[str]=[]
    for s in source['spans']:
        if ',' in s['text']:
            group.extend(v.strip().strip('.;:!?—– ').casefold() for v in s['text'].split(',') if v.strip().strip('.;:!?—– '))
        elif group:groups.append(group);group=[]
    if group:groups.append(group)
    results=[]
    for i,a in enumerate(groups):
        for b in groups[i+1:]:
            shared=sorted(set(a)&set(b))
            if len(shared)>=2:results.append({'shared_literal_features':shared,'sequence_equal':a==b,'added_literal_features':sorted(set(b)-set(a)),'scope':'Literal comma-list projection only, not world identity'})
    return results


def finite_models(proposal: dict, review: dict | None = None) -> list[dict]:
    """Ordinary bounded transition-table baseline on declared source mappings."""
    audit={(x['reading_id'],x['relation_id']):x for x in (review or {}).get('assessments',[])};models=[]
    for h in proposal.get('readings',[]):
        worlds=[s['id'] for s in h['states'] if s['level']=='WORLD_STATE'];edges=[]
        for r in h['relations']:
            c=r['source_claim'];a=audit.get((h['id'],r['id']))
            eligible=(r['kind']=='TRANSITION' and r['polarity']=='POSITIVE' and c['mode'] in {'DIRECT','NARRATION'} and c['stance']=='ASSERTS' and 'CONDITIONAL_EXECUTABLE_CHANGE' in r['interpretation_assumptions'] and r['src'] in worlds and r['dst'] in worlds and r['src']!=r['dst'])
            if review is not None:eligible=eligible and bool(a and a['status']=='HYPOTHESIS' and a['attribution_checked'] and a['executable_assumption_supported'])
            if eligible:edges.append((worlds.index(r['src']),worlds.index(r['dst'])))
        tables=[]
        for a,b in edges:
            table=[]
            for state in range(1<<len(worlds)):
                table.append(state-(1<<a)+(1<<b) if state&(1<<a) and not state&(1<<b) else state)
            tables.append(table)
        initials=[1<<worlds.index(s) for s in h['initial_state_ids'] if s in worlds]
        declared_initials=bool(initials)
        if edges and not initials:initials=[1<<edges[0][0]]
        reached=set(initials);pending=list(initials);cycles=[]
        while pending:
            state=pending.pop()
            for table in tables:
                after=table[state]
                if after not in reached:reached.add(after);pending.append(after)
        for start in initials:
            queue: list[tuple[int,list[dict]]]=[(start,[])];seen={start}
            while queue:
                state,path=queue.pop(0)
                for i,table in enumerate(tables):
                    after=table[state]
                    if after==state:continue
                    step={'operation':i,'before':state,'after':after,'fired':True};trace=path+[step]
                    if after==start and len(trace)>=2:cycles.append({'initial':start,'steps':trace});queue=[];break
                    if after not in seen:seen.add(after);queue.append((after,trace))
                if cycles and cycles[-1]['initial']==start:break
        models.append({'reading':h['id'],'target':'FINITE_CONDITIONAL' if edges else 'META_ONLY','transition_tables':tables,'initials':initials,'reachable':sorted(reached),'actual_fired_cycles':cycles,'source_verified':False,'execution_grant':False,
            'operator_scope':'Conditional simulation of declared mappings; source event chronology not inferred',
            'initial_source':'DECLARED_IN_SOURCE_READING' if declared_initials else 'CHOSEN_FOR_CONDITIONAL_SIMULATION'})
    return models


def observation_checks(proposal: dict, source: dict, limit: int = 4096) -> list[dict]:
    """Finite record completions, separate from world and from missing bindings."""
    from itertools import combinations, product
    spans={s['id']:s['text'] for s in source['spans']+source.get('context',[])}
    def exact(cs):return bool(cs) and all(c['ref'] in spans and c['quote'] in spans[c['ref']] for c in cs)
    out=[]
    for h in proposal.get('readings',[]):
        for p in h['observers']:
            for a,b in combinations(p['samples'],2):
                row={'reading':h['id'],'observer':p['id'],'states':[a['state_id'],b['state_id']],'source_verified':False,'scope':'ADOPT_ADDRESSED_OBSERVATION_RECORDS; NOT_WORLD_TRUTH'}
                bound=all(a[k] is not None and a[k]==b[k] for k in ['time','scope']) and a['referent'] is not None and b['referent'] is not None and exact(a['binding_evidence']) and exact(b['binding_evidence'])
                cells={(s['state_id'],v['feature']):v for s in [a,b] for v in s['values']}
                if any(v['status']=='CONFLICT' for v in cells.values()):out.append({**row,'verdict':'CONFLICTING_REPORTS'});continue
                if not bound:out.append({**row,'verdict':'UNKNOWN_INSUFFICIENT_OBSERVATION','reason':'MISSING_RECORD_TIME_SCOPE_OR_REFERENT'});continue
                keys=[(s['state_id'],f) for s in [a,b] for f in p['features']];domains=[]
                for state,f in keys:
                    known={v['value'] for (_,g),v in cells.items() if g==f and v['value'] is not None}
                    values=[('source',v) for v in sorted(known)]+[('other',0),('other',1)];cell=cells.get((state,f),{'status':'UNKNOWN','value':None,'evidence':[]})
                    if exact(cell['evidence']):
                        if cell['status']=='KNOWN':values=[('source',cell['value'])]
                        if cell['status']=='EXPLICIT_NEGATIVE':values=[v for v in values if v!=('source',cell['value'])]
                    domains.append(values)
                count=1
                for v in domains:count*=len(v)
                if count>limit:out.append({**row,'verdict':'RESOURCE_BOUND','world_count':count});continue
                truths=[]
                for xs in product(*domains):
                    w=dict(zip(keys,xs));truths.append(bool(p['features']) and all(w[a['state_id'],f]==w[b['state_id'],f] for f in p['features']))
                verdict='UNKNOWN_INSUFFICIENT_OBSERVATION' if any(truths) and not all(truths) else 'ENTAILED_UNDER_ASSUMPTIONS' if all(truths) else 'REFUTED_UNDER_ASSUMPTIONS'
                out.append({**row,'verdict':verdict,'world_count':count})
    return out
