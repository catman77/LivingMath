"""Fixed generic projection of actual typed source graphs; no game-specific taxonomy."""
from collections import Counter
import hashlib
import json
import re

DIMENSIONS=512
VERSION='livingmath-source-graph-basis/1'


def _norm(value):
    return re.sub(r'\s+',' ',str(value).strip().lower())[:240]


def _tokens(state: dict) -> list[str]:
    result=['label='+_norm(state.get('label',''))]
    coordinates=state.get('source_coordinates',state)
    for key in ['level','polarity','modality','tense','quantifier','participant','referent']:
        value=state.get(key,coordinates.get(key))
        if value is not None:result.append(key+'='+_norm(value))
    for feature in state.get('features',[]):
        result.append('feature='+_norm(feature['feature'] if isinstance(feature,dict) else feature))
    return sorted(result)


def graph_counts(states: list[dict], edges: list[dict]) -> dict[str,float]:
    nodes={s.get('key',s.get('id')):_tokens(s) for s in states}
    result=Counter();outgoing={}
    for key,tokens in nodes.items():
        for token in tokens:result['node:'+token]+=1
        result['node_signature:'+json.dumps(tokens,ensure_ascii=False)]+=1
    for edge in edges:
        src=edge.get('src');dst=edge.get('dst')
        if isinstance(edge.get('source'),dict):src=edge['source']['key'];dst=edge['target']['key']
        kind=edge.get('relation_kind',edge.get('kind','UNKNOWN'))
        signature=[kind,*[str(edge.get(k,'UNKNOWN')) for k in ['polarity','modality','order_kind','critic_status']]]
        source=nodes.get(src,[]);target=nodes.get(dst,[])
        for key in signature:result['edge_attribute:'+key]+=1
        result['edge:'+json.dumps([source,signature,target],ensure_ascii=False)]+=1
        outgoing.setdefault(src,[]).append((dst,signature))
    for src,items in outgoing.items():
        for middle,first in items:
            for dst,second in outgoing.get(middle,[]):
                result['path2:'+json.dumps([nodes.get(src,[]),first,nodes.get(middle,[]),second,nodes.get(dst,[])],ensure_ascii=False)]+=1
    result['count.nodes']=len(nodes);result['count.edges']=len(edges)
    result['count.branching_nodes']=sum(len(v)>1 for v in outgoing.values())
    result['count.self_loops']=sum(dst==src for src,items in outgoing.items() for dst,_ in items)
    return dict(result)


def semantic_features(observations: list[dict]) -> tuple[dict,bool]:
    output=Counter();readings_count=0
    for observation in observations:
        proposals=observation.get('source_proposals',{})
        review=observation.get('source_critic') or {}
        statuses={(a['reading_id'],a['relation_id']):a['status'] for a in review.get('assessments',[])}
        for reading in proposals.get('readings',[]):
            edges=[{**e,'critic_status':statuses.get((reading['id'],e['id']),'UNKNOWN')} for e in reading['relations']]
            output.update(graph_counts(reading['states'],edges));readings_count+=1
    if readings_count:
        return {k:v/readings_count for k,v in output.items()},True
    return {'MISSING_SEMANTIC_GRAPH':1.},False


def formal_features(results: list[dict]) -> tuple[dict,bool]:
    output=Counter();count=0
    for result in results:
        model=result.get('model',{});check=result.get('check',{});analysis=check.get('analysis',{})
        if model.get('compiled_hash')!=check.get('model_hash'):continue
        if not (analysis.get('meta_transport_checked') or analysis.get('all_operations_independently_replayed')):continue
        observer=model.get('observer',{})
        if observer.get('kind')!='SOURCE_SEMANTICS012':continue
        output.update(graph_counts(observer.get('states',[]),observer.get('source_annotations',[])))
        output['formal_status:'+str(model.get('status'))]+=1
        output['formal_target:'+str(model.get('target_model'))]+=1
        output['formal_states']=output.get('formal_states',0)+float(analysis.get('full_state_count',0))
        output['formal_observers']=output.get('formal_observers',0)+len(observer.get('observers',[]))
        for key,value in analysis.get('invariants',{}).items():
            if isinstance(value,bool):output['invariant:'+key+':'+str(value)]+=1
        transition=analysis.get('source_transition_analysis',{})
        for key in ['cycle_status','outcome']:
            if key in transition:output['formal_transition:'+key+':'+str(transition[key])]+=1
        output['formal_cycles']+=len(transition.get('full_state_cycles',[]))
        output['formal_observed_returns']+=len(transition.get('observed_returns',[]))
        output['formal_obligations']+=len(analysis.get('source_meta_obligations',[]))
        count+=1
    if count:return {k:v/count for k,v in output.items()},True
    return {'MISSING_FORMAL_MODEL':1.},False


def fixed_projection(values: dict[str,float], dimensions: int=DIMENSIONS) -> list[float]:
    vector=[0.]*dimensions
    for token,value in sorted(values.items()):
        code=hashlib.sha256(token.encode()).digest();index=int.from_bytes(code[:8],'big')%dimensions
        vector[index]+=float(value)*(1 if code[8]&1 else -1)
    norm=sum(v*v for v in vector)**.5
    return [v/norm for v in vector] if norm else vector


def raw_semantic_views(records: list[dict]) -> list[dict]:
    """Keep the LLM control even when formal alignment rejects a critic response."""
    proposals=[];critics=[]
    for row in records:
        if row.get('kind')!='artifact_semantic_call':continue
        payload=row['payload'];value=payload.get('result',{})
        if value.get('status')!='OK':continue
        if payload.get('role')=='proposer012':proposals.append(value['output'])
        elif payload.get('role')=='critic012':critics.append(value['output'])
    return [{'source_proposals':p,'source_critic':critics[i] if i<len(critics) else None} for i,p in enumerate(proposals)]
