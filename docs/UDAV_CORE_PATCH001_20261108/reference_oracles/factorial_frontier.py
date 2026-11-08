#!/usr/bin/env python3
"""Counterfactual 2x2 SPLIT toy model; NO claims about running ReversibleUDAV.

Frozen arm-independent: transition semantics, 24 rounds * 3 applied proposals,
common exogenous RNG keyed by (seed,parent,local attempt), and blind selector.
Two independent interventions: parent scheduling and position uniqueness.
TARGET and alpha discovery are used ONLY after each action to score progress;
not available to choose parent, parameter or next child.
"""
from __future__ import annotations
import hashlib, json, random, statistics
from collections import deque

ROOT=tuple('abcabcab')
SEEDS=list(range(119,149))
ROUNDS=24
K=3
ATTEMPTS=ROUNDS*K

def stable_seed(*args):
    return int.from_bytes(hashlib.sha256(repr(args).encode()).digest()[:8], 'big')

def alpha(word):
    d={}
    return tuple(d.setdefault(x,len(d)) for x in word)

# For scoring only. Not passed to any controller.
TARGET={ROOT[i:j] for i in range(len(ROOT)+1) for j in range(i,len(ROOT)+1)}
CYCLE={tuple(x) for x in ('abca','bcab','cabc')}
assert len(TARGET)==22 and len({alpha(w) for w in CYCLE})==1

def simulate(seed,parent_mode,param_mode,root=ROOT):
    # The exact reachable set is used only for scoring AFTER each SPLIT apply.
    target={root[i:j] for i in range(len(root)+1) for j in range(i,len(root)+1)}
    groups={}
    for w in target:
        if len(w)==4:groups.setdefault(alpha(w),set()).add(w)
    possible=[g for g in groups.values() if len(g)>=2]
    cycle=min(possible,key=lambda g:sorted(g)) if possible else set()
    known={root}
    discovered=[root]
    current=root
    visit= {}
    used_positions={}
    round_robin=deque([root])
    in_queue={root}
    steps_since_growth=0
    total_duplicates=0
    n_empty_rounds=0
    n_empty_with_frontier=0
    first_cycle=None
    first_all=None
    interesting_at_budget=None
    expanded=set()
    parent_samples=[]
    for rnd in range(ROUNDS):
        if parent_mode=='sticky':
            parent=current
            # A bounded analogue of original stale-frontier fallback.
            # Without parameter information, do not pre-filter choices by unused k.
            if steps_since_growth>=8:
                candidates=[x for x in discovered if len(x)>=2 and x not in expanded]
                if candidates:
                    parent=candidates[0]
                    current=parent
                steps_since_growth=0
        elif parent_mode=='fair':
            # Round-robin among discovered states whose SPLIT can be non-trivial.
            # FIFO does NOT inspect parameter ledger; independent factors.
            if not round_robin:
                round_robin.append(root)
            parent=round_robin.popleft()
            round_robin.append(parent)
        else: raise ValueError(parent_mode)
        parent_samples.append(len(parent))
        if not parent:
            n_empty_rounds+=1
            if any(len(w)>=2 and w not in expanded for w in discovered):
                n_empty_with_frontier+=1
        expanded.add(parent)
        k_values=[]
        new_in_batch=[]
        for slot in range(K):
            a=visit.get(parent,0)
            visit[parent]=a+1
            if param_mode=='clock':
                # Exogenous per-parent stream, with replacement; stable across policies.
                k=stable_seed(seed,parent,a)%(len(parent)+1)
            elif param_mode=='untried':
                # The same random preference stream per parent; skips tried positions.
                order=list(range(len(parent)+1))
                order.sort(key=lambda pos:stable_seed(seed,parent,pos,'position-preference'))
                rem=[z for z in order if z not in used_positions.get(parent,set())]
                k=rem[0] if rem else stable_seed(seed,parent,a)%(len(parent)+1)
            else: raise ValueError(param_mode)
            used_positions.setdefault(parent,set()).add(k)
            k_values.append(k)
            prefix,suffix=parent[:k],parent[k:]
            created=[]
            for child in (prefix,suffix):
                if child not in known:
                    known.add(child)
                    discovered.append(child)
                    created.append(child)
                    if parent_mode=='fair' and len(child)>=2 and child not in in_queue:
                        round_robin.append(child);in_queue.add(child)
                else: total_duplicates+=1
            new_in_batch.append(created)
            number=rnd*K+slot+1
            if first_cycle is None and len(cycle & known)>=2: first_cycle=number
            if first_all is None and len(known)==len(target):first_all=number
        eligible=[j for j,a in enumerate(new_in_batch) if a]
        if parent_mode=='sticky':
            if eligible:
                # Common random local selection among new candidates, no target information.
                chosen=eligible[stable_seed(seed,'selection',rnd)%len(eligible)]
                current=new_in_batch[chosen][0] # Like first new output in production
            steps_since_growth=0 if eligible else steps_since_growth+1
        # For fairness mode parent scheduling does not depend on result success.
    assert all(w in target for w in known), 'SPLIT produced non-substring'
    return {'covered':len(known),'fraction':len(known)/len(target),'duplicate_child_outputs':total_duplicates,
        'first_cycle_at_apply':first_cycle,'first_all_at_apply':first_all,
        'cycle_found':int(len(cycle & known)>=2),'empty_rounds':n_empty_rounds,
        'empty_with_nontrivial_open':n_empty_with_frontier,
        'parent_visits':len(visit),'nontrivial_parents_visited':sum(1 for w in visit if len(w)>=2),
        'params_distinct':sum(len(s) for s in used_positions.values()),'attempts':ATTEMPTS,
        'rounds':ROUNDS,'final_length':len(current) if parent_mode=='sticky' else None,
        'seen_words_sorted':[''.join(x) for x in sorted(known)]}

def mean(data,key): return round(statistics.mean(x[key] for x in data),4)

def paired_ci(values, seed=9001, draws=4000):
    rng=random.Random(seed)
    n=len(values)
    draws_result=sorted(sum(values[rng.randrange(n)] for _ in range(n))/n for _ in range(draws))
    return [round(draws_result[int(.025*draws)],3),round(draws_result[int(.975*draws)],3)]

def main():
    modes={'SC':('sticky','clock'),'SU':('sticky','untried'),'FC':('fair','clock'),'FU':('fair','untried')}
    data={m:[simulate(s,*policy) for s in SEEDS] for m,policy in modes.items()}
    summaries={m:{'avg_coverage':mean(a,'covered'),'min_coverage':min(x['covered'] for x in a),
         'max_coverage':max(x['covered'] for x in a),'full_coverage_runs':sum(x['covered']==22 for x in a),
         'cycle_discovery_runs':sum(x['cycle_found'] for x in a),'avg_duplicate_children':mean(a,'duplicate_child_outputs'),
         'avg_distinct_params_attempted':mean(a,'params_distinct'),'avg_nontrivial_parents':mean(a,'nontrivial_parents_visited'),
         'avg_empty_rounds':mean(a,'empty_rounds')}
         for m,a in data.items()}
    contrasts={}
    for name,plus,minus in [('parent_at_clock','FC','SC'),('parent_at_untried','FU','SU'),
                            ('param_at_sticky','SU','SC'),('param_at_frontier','FU','FC')]:
        diffs=[a['covered']-b['covered'] for a,b in zip(data[plus],data[minus])]
        contrasts[name]={'mean_diff':round(statistics.mean(diffs),3),'paired_bootstrap_95pct':paired_ci(diffs),
                          'n_positive':sum(v>0 for v in diffs),'n_equal':sum(v==0 for v in diffs),'n_negative':sum(v<0 for v in diffs)}
    interaction=[fu['covered']-fc['covered']-su['covered']+sc['covered'] for sc,su,fc,fu in zip(data['SC'],data['SU'],data['FC'],data['FU'])]
    contrasts['interaction']={'mean':round(statistics.mean(interaction),3),'paired_bootstrap_95pct':paired_ci(interaction)}
    result={'schema':'udav-causal-2x2-independent-toy/1','word':''.join(ROOT),'exact_oracle_words':len(TARGET),
        'seeds':SEEDS,'nominal_budget':{'rounds':ROUNDS,'applies_per_round':K,'total_SPLIT_applies':ATTEMPTS},
        'policies':modes,'source':'independent tuple model, NOT native ReversibleUDAV',
        'summary':summaries,'paired_contrasts':contrasts,
        'per_seed':{str(s):{m:data[m][i] for m in modes} for i,s in enumerate(SEEDS)}}
    return result

if __name__=='__main__':
    print(json.dumps(main(),indent=2,ensure_ascii=False))
