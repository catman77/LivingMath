"""Independent compiled-Boolean quotient and exact rational target-risk audit."""
from collections import Counter,deque
from fractions import Fraction
import math
from finite_semantics import MODELS,ACTIONS,compiled,vm_trace,words,canonical


def vm_behavior(model):
    transitions,source=compiled(model,False);_,target=compiled(model,True)
    reachable={0,1};pending=[0,1]
    while pending:
        state=pending.pop()
        for t in transitions:
            n=t[state]
            if n not in reachable:reachable.add(n);pending.append(n)
    states=sorted(reachable)
    separate={tuple(sorted((a,b))) for a in states for b in states if (source[a],target[a])!=(source[b],target[b])}
    changed=True
    while changed:
        changed=False
        for a in states:
            for b in states:
                key=tuple(sorted((a,b)))
                if a==b or key in separate:continue
                if any(tuple(sorted((t[a],t[b]))) in separate for t in transitions):separate.add(key);changed=True
    groups=[];owner={}
    for a in states:
        if a in owner:continue
        group=[b for b in states if tuple(sorted((a,b))) not in separate];groups.append(group)
        for b in group:owner[b]=len(groups)-1
    ids={};todo=deque()
    def intern(group):
        if group not in ids:ids[group]=len(ids);todo.append(group)
        return ids[group]
    roots=[intern(owner[0]),intern(owner[1])];rows=[]
    while todo:
        group=todo.popleft();state=groups[group][0]
        rows.append([source[state],target[state],*[intern(owner[t[state]]) for t in transitions]])
    return canonical([roots,rows])


def vm_public_law(data,questions):
    admitted={};raw=0
    for model in MODELS:
        if all(vm_trace(model,d['context'],d['actions'],d.get('transfer',False))==d['observations'] for d in data):
            raw+=1;admitted.setdefault(vm_behavior(model),model)
    models=list(admitted.values());n=len(models)
    if not n:raise ValueError('EMPTY_COMPILED_POSTERIOR')
    before=[Counter(tuple(vm_trace(m,q['context'],q['actions'])) for m in models) for q in questions]
    base_correct=sum(max(c.values()) for c in before);base_risk=Fraction(2*n-base_correct,2*n);entries=[]
    for context in [0,1]:
        for actions in words(3):
            buckets={}
            for m in models:buckets.setdefault(tuple(vm_trace(m,context,actions)),[]).append(m)
            correct=sum(max(Counter(tuple(vm_trace(m,q['context'],q['actions'])) for m in bucket).values())
                for bucket in buckets.values() for q in questions)
            reduction=Fraction(correct-base_correct,2*n)
            information=math.log2(n)-sum(len(b)/n*math.log2(len(b)) for b in buckets.values())
            entries.append({'context':context,'actions':list(actions),'IG':information,
                'probe_risk_reduction':float(reduction),'exact_reduction':[reduction.numerator,reduction.denominator]})
    return {'raw_models':raw,'behavior_classes':n,'risk_before':float(base_risk),'experiments':entries,
        'best_risk_reduction':max(e['probe_risk_reduction'] for e in entries),'IG_star':max(e['IG'] for e in entries)}
