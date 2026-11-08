#!/usr/bin/env python3
"""Independent diagnostic reference for frozen numerical CAT -> UDAV.

Reconstructs the published native C++ transition (white_star.cpp), not a replacement
for the production kernel. No LLM, MCP or network. Synthetic CAT coordinates only.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
from math import atan2, fmod, gcd, pi
import json
import random
import sys

SRC_IDS = list(range(1, 9))
EXPECTED = {
    (21, 8): [1,37,11,102,56,48,94,33,68,24,7,36,0,39,79,88,12,59,22,91,89,26,39,90],
    (22, 8): [106,55,93,76,73,80,110,89,109,85,69,26,32,9,70,39,5,44,104,87,95,34,31,78],
    (21, 3): [1,37,11,102,56,105,39,101,68,24,7,25,0,17,35,66,23,48,22,102,67,15,39,90],
    (22, 3): [106,55,93,76,73,80,110,56,8,96,69,15,21,88,59,17,5,55,104,87,73,91,9,78],
}


def atlas(coordinates: list[tuple[int,int]]) -> list[dict]:
    # Original CAD: every noncollinear ordered concept pair; then J rotation.
    old = []
    for i, (a,b) in enumerate(coordinates):
        for j, (c,d) in enumerate(coordinates):
            if i != j and a*d-b*c != 0:
                old.append(((a,b,c,d), (i,j)))
    charts, seen = [], set()
    for orientation in ("I", "J"):
        for m, pair in old:
            mat = m if orientation == "I" else (m[1],-m[0],m[3],-m[2])
            if mat not in seen:
                seen.add(mat)
                charts.append({"view":len(charts),"matrix":mat,"pair":tuple(sorted(pair)),"orientation":orientation})
    return charts


def signature(matrix, w):
    a,b,c,d=matrix
    x,y=a*w[0]+b*w[1],c*w[0]+d*w[1]
    aa,bb=abs(x),abs(y)
    dep,odd=0,0
    while bb:
        q,r=divmod(aa,bb)
        odd+=q&1;dep+=1
        aa,bb=bb,r
    theta=atan2(y,x) if (x or y) else 0.
    u=fmod(theta/(pi/2),1.)
    if u<0: u+=1.
    u=min(max(u,1e-12),1.-1e-12)
    phase=min(int(u*8),7)
    sx=(x>0)-(x<0);sy=(y>0)-(y<0)
    return (min(dep,6),odd%3,min(aa,3),sx,sy,phase)


def witness_sequence(seed, steps):
    layer,pos=0,0
    stride=2*(seed%19)+1
    out=[]
    for t in range(steps):
        m=layer+1
        a=(pos*stride+seed%m)%m
        b=layer-a
        out.append((a,b))
        pos+=1
        if pos==m:
            layer+=1
            pos=0
            stride=2*(seed%19)+1
            while gcd(stride,layer+1)!=1:stride+=2
    return out


def candidate_schedule(seed,k,ncharts,steps):
    ra=seed&255;rb=(seed*73+37)&255
    stride=11
    while gcd(stride,ncharts)!=1:stride+=1
    out=[]
    for t in range(steps):
        rb_next=ra^(((rb<<1)^(rb>>3))&127)
        ra,rb=rb,rb_next
        first=(rb+((t+1)%ncharts)*7+seed%ncharts)%ncharts
        out.append([(first+j*stride)%ncharts for j in range(k)])
    return out


def native_reference(seed,k,charts,steps=24):
    w=witness_sequence(seed,steps)
    schedule=candidate_schedule(seed,k,len(charts),steps)
    seen=Counter();phases=Counter();used=Counter();edges=set()
    prev=None;selected=[];events=[]
    for t in range(steps):
        pool=[]
        for v in schedule[t]:
            sg=signature(charts[v]["matrix"],w[t])
            nv=int(seen[sg]==0)
            edge=frozenset((prev,sg))
            ne=int(prev is not None and prev!=sg and edge not in edges)
            cyc=int(ne and not nv)
            nov=min(13,6*nv+3*ne+4*cyc)
            score=(nov,-seen[sg],-phases[sg[-1]],-used[v])
            pool.append((v,sg,score))
        best=max(range(k),key=lambda i:pool[i][2])
        v,sg,score=pool[best]
        if prev is not None and prev!=sg:edges.add(frozenset((prev,sg)))
        prev=sg;seen[sg]+=1;phases[sg[-1]]+=1;used[v]+=1
        selected.append(v)
        events.append({"step":t,"witness":list(w[t]),"views":schedule[t],"chosen":v,"signature":list(sg),"scores":[list(x[2]) for x in pool]})
    return {"seed":seed,"k":k,"ncharts":len(charts),"selected":selected,"events":events,
            "unique_selected":len(set(selected)),"unique_proposed":len({x for xs in schedule for x in xs})}


def pair_coverage(events,charts,mode="native",random_seed=0):
    seen_pairs=set();used_views=set();chosen=[]
    rng=random.Random(random_seed)
    for event in events:
        pool=event["views"]
        if mode=="native": v=event["chosen"]
        elif mode=="random":v=rng.choice(pool)
        elif mode=="pair_greedy":
            v=next((x for x in pool if charts[x]["pair"] not in seen_pairs),None)
            if v is None:v=next((x for x in pool if x not in used_views),pool[0])
        else:raise ValueError(mode)
        chosen.append(v)
        seen_pairs.add(charts[v]["pair"])
        used_views.add(v)
    return {"pairs":len(seen_pairs),"views":len(used_views),"selected":chosen}


def collision_audit(run,charts):
    # Count all CAT views with the same 6-field coarse signature at each witness;
    # this is not a claim of semantic equivalence.
    summaries=[]
    for event in run["events"]:
        w=event["witness"]
        classes={}
        for chart in charts:
            s=signature(chart["matrix"],w)
            classes.setdefault(s,[]).append(chart["view"])
        summaries.append({"step":event["step"],"witness":w,
                          "all_views":len(charts),"distinct_signatures":len(classes),
                          "largest_collision":max(map(len,classes.values()))})
    return summaries


def main():
    orig=atlas([(i,i*i) for i in SRC_IDS])
    assert len(orig)==112
    data={"schema":"udav-cat-seam-independent/1","atlas_size":len(orig),"possible_unordered_pairs":len({x['pair'] for x in orig}),"runs":{},"tests":[],"collisions":{}}
    for seed in [21,22]:
        for k in [3,8]:
            sim=native_reference(seed,k,orig)
            expect=EXPECTED[seed,k]
            same=sim["selected"]==expect
            assert same, (seed,k,[(i,x,y)for i,(x,y)in enumerate(zip(sim['selected'],expect))if x!=y])
            native=pair_coverage(sim["events"],orig,"native")
            greedy=pair_coverage(sim["events"],orig,"pair_greedy")
            draws=[pair_coverage(sim["events"],orig,"random",i)["pairs"]for i in range(1000)]
            name=f"k{k}_seed{seed}"
            avoid=0;known=set()
            for ev in sim["events"]:
                pair=orig[ev["chosen"]]["pair"]
                if pair in known and any(orig[v]["pair"] not in known for v in ev["views"]):avoid+=1
                known.add(pair)
            data["runs"][name]={"selected_native_matches_live_MCP":same,"native_unique_pairs":native["pairs"],
                                  "greedy_unique_pairs":greedy["pairs"],"random_mean":sum(draws)/len(draws),
                                  "random_range":[min(draws),max(draws)],"avoidable_pair_repeats":avoid,
                                  "unique_proposed_views":sim["unique_proposed"],"unique_selected_views":sim["unique_selected"],
                                  "native_selection":native["selected"],"greedy_selection":greedy["selected"],
                                  "candidate_views":[e["views"]for e in sim["events"]]}
            data["tests"].append(f"PASS exact native selection seed={seed} k={k}, 24/24")
            if k==8:data["collisions"][name]=collision_audit(sim,orig)
        # Future candidates do not react to different selected historical views:
        k3=candidate_schedule(seed,3,len(orig),24)
        k8=candidate_schedule(seed,8,len(orig),24)
        assert all(a==b[:3] for a,b in zip(k3,k8))
        data["tests"].append(f"PASS independent proposal schedule seed={seed} k3 subset k8, 24/24")
        # Changed CAT coordinates but same atlas size -> candidate indices same.
        for variant,coords in [("cubic",[(i,i**3)for i in SRC_IDS]),
                               ("reversed-quadratic",[(i,(9-i)**2)for i in SRC_IDS])]:
            alt=atlas(coords)
            assert len(alt)==112
            same=candidate_schedule(seed,8,len(alt),24)==candidate_schedule(seed,8,len(orig),24)
            assert same
            data["tests"].append(f"PASS candidate schedule blind to CAT {variant}, seed={seed}, 24/24")
    scale3=atlas([(3*i,3*i*i)for i in SRC_IDS]);scale7=atlas([(7*i,7*i*i)for i in SRC_IDS]);assert len(scale3)==len(scale7)==112
    for seed in [21,22]:
        a=native_reference(seed,8,scale3)
        b=native_reference(seed,8,scale7)
        assert a["selected"]==b["selected"]
        assert all(x["signature"]==y["signature"] for x,y in zip(a["events"],b["events"]))
        data["tests"].append(f"PASS scale-3 vs scale-7 same selected signatures and views, seed={seed}, 24/24")
    print(json.dumps(data,ensure_ascii=False,indent=2))

if __name__=="__main__":main()
