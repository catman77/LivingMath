#!/usr/bin/env python3
"""Counterfactual native selectors over identical CAT / White Star witness candidates.

The candidate-generation schedule is unchanged by the selection history in the
published C++ kernel, so replaying it with different selectors is causal for
these finite synthetic metrics. No semantic meaning or generalization claimed.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from math import gcd
import json
import random
from independent_native_reference import atlas, candidate_schedule, witness_sequence, signature, native_reference

CHARTS=atlas([(i,i*i) for i in range(1,9)])


def projected_pair(view,w):
    c=CHARTS[view];a,b,d,e=c['matrix'];x,y=a*w[0]+b*w[1],d*w[0]+e*w[1]
    relation='ALIGN' if x*y>0 else 'TENSION' if x*y<0 else 'UNRESOLVED'
    dominance=0 if abs(x)>abs(y) else 1 if abs(y)>abs(x) else 2
    return (c['pair'],relation,dominance)


def run_policy(seed,k,mode='native',steps=24,random_seed=1):
    witnesses=witness_sequence(seed,steps);schedule=candidate_schedule(seed,k,len(CHARTS),steps)
    seen=Counter();phase=Counter();used=Counter();edges=set();prev=None
    pairs=set();signatures=set();views=set();qualitative=set();trajectory=[];rng=random.Random(random_seed)
    for t,(w,pool) in enumerate(zip(witnesses,schedule)):
        cand=[]
        for v in pool:
            sg=signature(CHARTS[v]['matrix'],w)
            nv=int(seen[sg]==0);edge=frozenset((prev,sg));ne=int(prev is not None and prev!=sg and edge not in edges);cyc=int(ne and not nv)
            nov=min(13,6*nv+3*ne+4*cyc)
            key=(nov,-seen[sg],-phase[sg[-1]],-used[v]);newpair=int(CHARTS[v]['pair'] not in pairs)
            if mode=='native':key2=key
            elif mode=='pair_first':key2=(newpair,*key)
            elif mode=='pair_after_novelty':key2=(key[0],newpair,*key[1:])
            elif mode=='pair_last':key2=(*key,newpair)
            elif mode=='det_first':
                m=CHARTS[v]['matrix'];key2=(abs(m[0]*m[3]-m[1]*m[2]),*key)
            elif mode=='random':key2=()
            else:raise ValueError(mode)
            cand.append((v,sg,key2))
        i=rng.randrange(len(cand)) if mode=='random' else max(range(len(cand)),key=lambda i:cand[i][2]);v,sg,_=cand[i]
        if prev is not None and prev!=sg:edges.add(frozenset((prev,sg)))
        prev=sg;seen[sg]+=1;phase[sg[-1]]+=1;used[v]+=1
        pairs.add(CHARTS[v]['pair']);signatures.add(sg);views.add(v);qualitative.add(projected_pair(v,w))
        trajectory.append(v)
    return dict(mode=mode,seed=seed,k=k,pairs=len(pairs),signatures=len(signatures),edges=len(edges),
                views=len(views),qualitative_states=len(qualitative),trajectory=trajectory)


def collision_audit(seed=22,steps=24):
    witnesses=witness_sequence(seed,steps)
    rows=[];examples=[]
    for t,w in enumerate(witnesses):
        classes=defaultdict(list)
        for v,c in enumerate(CHARTS):classes[signature(c['matrix'],w)].append(v)
        cross=[x for x in classes.values() if len({CHARTS[v]['pair'] for v in x})>1]
        item={'step':t,'witness':w,'available_views':len(CHARTS),'signature_classes':len(classes),
              'cross_pair_collision_classes':len(cross),'views_in_cross_pair_collisions':sum(map(len,cross)),
              'max_distinct_pairs_same_signature':max(len({CHARTS[v]['pair'] for v in group}) for group in classes.values())}
        rows.append(item)
        if t==3:
            group=max(classes.values(),key=lambda group:len({CHARTS[v]['pair'] for v in group}))
            examples=[{'view':v,'pair':CHARTS[v]['pair'],'matrix':CHARTS[v]['matrix'],
                       'signature':signature(CHARTS[v]['matrix'],w)} for v in group[:8]]
    return {'rows':rows,'example_t3':examples}


def main():
    out={'schema':'udav-frozen-cat-selector-counterfactual/1','scope':'synthetic 8-concept atlas, fixed candidate schedule, 24 steps',
         'policies':{},'collisions':collision_audit(),'tests':[]}
    for seed in [21,22]:
        for k in [3,8]:
            key=f'seed{seed}_k{k}'
            modes=['native','pair_first','pair_after_novelty','pair_last','det_first']
            res={mode:run_policy(seed,k,mode) for mode in modes}
            native=native_reference(seed,k,CHARTS)
            assert res['native']['trajectory']==native['selected']
            out['tests'].append('PASS native counterfactual matches exact replay '+key)
            rand=[run_policy(seed,k,'random',random_seed=i)['pairs'] for i in range(1000)]
            res['uniform_random_summary']={'replicates':1000,'mean_pair_coverage':sum(rand)/len(rand),
                                           'min':min(rand),'max':max(rand)}
            out['policies'][key]={mode:{k:v for k,v in item.items()if k!='trajectory'} for mode,item in res.items()}
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
