"""Canonical finite-state table search from prefix constraints, never a scalar feature."""

from itertools import product
from ..core import digest
from .ir import dfa, header, Budget, Bound


def run(ast,record,bounds):
    dfa(ast);out={**header(ast,record,bounds),"start_state":ast["start"]}
    if len(record["tokens"])>bounds["max_tokens"] or len(ast["states"])>bounds["max_states"] or any(t not in ast["alphabet"] for t in record["tokens"]):return {**out,"status":"UNKNOWN_BOUND","decision":None,"reason":"DOMAIN_BOUND"}
    q=ast["start"];trace=[];table={(e["from"],e["token"]):e["to"] for e in ast["delta"]}
    for i,t in enumerate(record["tokens"]):
        to=table[q,t];trace.append({"from":q,"token":t,"index":i,"source_span":out["token_spans"][i],"target":to});q=to
    decision=q in ast["accepting"]
    return {**out,"status":"ACCEPT_WITH_WITNESS" if decision else "REJECT_COMPLETE","decision":decision,"trace":trace,"final_state":q}


def fit(records,bounds):
    if not records or len(records)>256 or any(type(r.get('accepted')) is not bool for r in records):raise ValueError('TRAIN_BOUND_OR_LABEL')
    work=Budget(bounds);alphabet=sorted({t for r in records for t in r['tokens']});labels={};edges=set();prefixes={()}
    for r in records:
        word=tuple(r['tokens'])
        if word in labels and labels[word]!=r['accepted']:return {'status':'CONTRADICTORY_TRAIN','candidates':[],'selected':None,'execution_permission':False}
        labels[word]=r['accepted']
        for i,t in enumerate(word):prefixes.add(word[:i+1]);edges.add((word[:i],t))
    ordered=sorted(edges,key=lambda x:(len(x[0]),x[0],x[1]));candidates=[];seen=set();considered=[];visited=0;state_level=0;reason='NO_COMPATIBLE_IN_DECLARED_CATALOG'
    def table(n,delta,accept):
        # Canonical state names are first-visit BFS in fixed alphabet order.
        mapping={0:0};queue=[0]
        for q in queue:
            for token in alphabet:
                target=delta[q,token]
                if target not in mapping:mapping[target]=len(mapping);queue.append(target)
        if len(mapping)!=n:return
        ast=dfa({'schema':'formal-dfa-ir/1','states':list(range(n)),'alphabet':alphabet,'start':0,'accepting':sorted(mapping[q] for q,y in accept.items() if y),'delta':[{'from':mapping[q],'token':t,'to':mapping[delta[q,t]]} for q in queue for t in alphabet]})
        ident=digest(ast)
        if ident in seen:return
        seen.add(ident)
        if len(considered)>=bounds['max_candidates']:raise Bound('CANDIDATE_BOUND')
        # Prefix constraints are checked again against the completed table.
        counter=None
        for r in records:
            work.tick();p=run(ast,r,bounds)
            if p['decision']!=r['accepted']:counter={'record_ref':digest(r),'expected':r['accepted'],'observed':p['decision']};break
        considered.append({'ast_sha256':ident,'ast':ast,'status':'TRAIN_COMPATIBLE' if counter is None else 'REJECTED_BY_TRAIN','counterexample':counter})
        if counter is None:candidates.append({'candidate_id':ident,'ast':ast,'origin':'CANONICAL_PREFIX_CONSTRAINT_SEARCH','status':'TRAIN_COMPATIBLE','type_status':'TYPED'})
    def solve(n,index,assigned,delta,accept,highest):
        nonlocal visited
        stack=[(index,assigned,delta,accept,highest)]
        while stack:
            index,assigned,delta,accept,highest=stack.pop()
            work.tick();visited+=1
            if index==len(ordered):
                missing=[(q,t) for q in range(n) for t in alphabet if (q,t) not in delta]
                for targets in product(range(n),repeat=len(missing)):
                    work.tick();full={**delta,**dict(zip(missing,targets))};free=[q for q in range(n) if q not in accept]
                    for bits in product([False,True],repeat=len(free)):table(n,full,{**accept,**dict(zip(free,bits))})
                continue
            prefix,token=ordered[index];q=assigned[prefix];key=q,token
            choices=[delta[key]] if key in delta else list(range(min(highest+1,n-1)+1))
            for target in reversed(choices):
                child=prefix+(token,);expected=labels.get(child)
                if expected is not None and target in accept and accept[target]!=expected:continue
                stack.append((index+1,{**assigned,child:target},{**delta,key:target},{**accept,**({target:expected} if expected is not None else {})},max(highest,target)))
    try:
        for n in range(1,bounds['max_states']+1):
            state_level=n;solve(n,0,{():0},{},{0:labels[()]} if () in labels else {},0)
            if candidates:reason='FIRST_COMPATIBLE_STATE_LEVEL_CHECKED';break
    except Bound as exc:reason='UNKNOWN_BOUND:'+str(exc)
    result={'schema':'formal-synthesis-model/1','kind':'DFA','status':'TRAIN_COMPATIBLE' if candidates else reason,'candidates':sorted(candidates,key=lambda c:c['candidate_id']),'selected':None,'considered':considered,'bounds':bounds,'catalog':{'search':'prefix trie constraints; complete transition/accepting tables; BFS renaming canonicalization','max_states':bounds['max_states'],'explored_through_states':state_level,'prefix_nodes':len(prefixes),'partial_nodes_visited':visited,'untried_state_levels':list(range(state_level+1,bounds['max_states']+1)),'minimality_claim':False},'search_status':reason,'train_sha256':digest(records),'family_status':'UNDERDETERMINED','execution_permission':False,'UNIVERSAL_INVARIANT':False}
    result['selected']=result['candidates'][0]['candidate_id'] if result['candidates'] else None;result['hypothesis_sha256']=digest(result);return result
