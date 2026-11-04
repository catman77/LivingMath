"""Complete public affine class, exact observable quotient; no selected truth."""
import hashlib
import json
import math
from collections import Counter,deque
from functools import lru_cache
from itertools import product


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


OPERATIONS=tuple((r0,r1,0) for r0 in range(1,4) for r1 in range(1,4) if r0!=r1)+((1,3,1),(3,2,2))
MODELS=tuple(product(range(8),range(8),range(1,4)))
ACTIONS=('a','b','read')


def operation_id(index):return 'operation:'+str(index)
def policy(model):
    a,b,s=model
    return {'kind':'affine_memory','a_operation':operation_id(a),'b_operation':operation_id(b),
            'sensor_mask':[bool(s&1),bool(s&2)]}


def as_model(value):
    if value['kind']!='affine_memory':raise ValueError('NOT_AFFINE_POLICY')
    a,b=(int(value[k].removeprefix('operation:')) for k in ['a_operation','b_operation'])
    mask=value['sensor_mask'];mask=int(mask) if isinstance(mask,int) else int(mask[0])+2*int(mask[1]);m=(a,b,mask)
    if m not in MODELS:raise ValueError('POLICY_OUTSIDE_PUBLIC_CLASS')
    return m


def public_class():
    return {'kind':'complete_affine_memory_class/1','memory_registers':['x','y'],
        'initialization':'x=context_bit; y=false, at every reset',
        'operations':[{'id':operation_id(i),'row_x':[bool(r0&1),bool(r0&2)],
            'row_y':[bool(r1&1),bool(r1&2)],'offset':[bool(off&1),bool(off&2)]}
            for i,(r0,r1,off) in enumerate(OPERATIONS)],
        'transition_contract':'Independently choose one listed operation for a and one for b, fixed across resets. Each output bit is XOR of selected old register bits and offset. read is identity.',
        'observation_contract':'One fixed unknown nonzero linear sensor mask: x, y, or x XOR y. Outputs are bits. This declares all alternatives, not the selected law.',
        'raw_model_count':192,'prior':'Uniform over EXACT distinguishable source-and-declared-transfer behaviors, not duplicate internal realizations.',
        'transfer':'Swap the two coefficients of the sensor; keep the two transition maps and initialization. Identity observation decoder. This is a changed physical readout channel, not an alpha-rename.',
        'private_selected_operations_provided':False}


def step(model,state,action):
    if action not in ACTIONS:raise ValueError('ACTION_NAMESPACE')
    if action=='read':return state
    r0,r1,off=OPERATIONS[model[0 if action=='a' else 1]]
    return (((state&r0).bit_count()&1)|(((state&r1).bit_count()&1)<<1))^off


def observe(model,state,transfer=False):
    mask=model[2]
    if transfer:mask=((mask&1)<<1)|((mask&2)>>1)
    return (state&mask).bit_count()&1


def trace(model,context,actions,transfer=False):
    state=int(context);out=[observe(model,state,transfer)]
    for action in actions:state=step(model,state,action);out.append(observe(model,state,transfer))
    return out


@lru_cache(maxsize=None)
def compiled(model,transfer=False):
    """Independent boolean compiler: never calls step/observe/direct trace."""
    a,b,s=model;maps=[]
    for oi in [a,b]:
        r0,r1,off=OPERATIONS[oi];table=[]
        for encoded in range(4):
            x=bool(encoded&1);y=bool(encoded&2)
            nx=((x and bool(r0&1))!=(y and bool(r0&2)))!=bool(off&1)
            ny=((x and bool(r1&1))!=(y and bool(r1&2)))!=bool(off&2)
            table.append(int(nx)+2*int(ny))
        maps.append(tuple(table))
    sx,sy=bool(s&1),bool(s&2)
    if transfer:sx,sy=sy,sx
    sensor=tuple(int((bool(q&1) and sx)!=(bool(q&2) and sy)) for q in range(4))
    return tuple(maps+[tuple(range(4))]),sensor


def vm_trace(model,context,actions,transfer=False):
    tables,sensor=compiled(tuple(model),transfer);q=int(context);out=[sensor[q]]
    for action in actions:q=tables[ACTIONS.index(action)][q];out.append(sensor[q])
    return out


def words(maximum,alphabet=ACTIONS,include_empty=False):
    return [p for n in range(0 if include_empty else 1,maximum+1) for p in product(alphabet,repeat=n)]


@lru_cache(maxsize=None)
def behavior(model):
    """Canonical reachable minimized Moore machine for BOTH sensor channels."""
    reachable={0,1};pending=[0,1]
    while pending:
        q=pending.pop()
        for a in ACTIONS:
            n=step(model,q,a)
            if n not in reachable:reachable.add(n);pending.append(n)
    states=sorted(reachable);blocks={q:(observe(model,q),observe(model,q,True)) for q in states}
    def normalize(keys):
        ids={};return {q:ids.setdefault(keys[q],len(ids)) for q in states}
    blocks=normalize(blocks)
    while True:
        refined=normalize({q:(blocks[q],tuple(blocks[step(model,q,a)] for a in ACTIONS)) for q in states})
        if all((blocks[x]==blocks[y])==(refined[x]==refined[y]) for x in states for y in states):blocks=refined;break
        blocks=refined
    reps={b:q for q,b in blocks.items()};ids={};queue=deque()
    def intern(b):
        if b not in ids:ids[b]=len(ids);queue.append(b)
        return ids[b]
    roots=[intern(blocks[q]) for q in [0,1]];rows=[]
    while queue:
        b=queue.popleft();q=reps[b]
        rows.append([observe(model,q),observe(model,q,True),*[intern(blocks[step(model,q,a)]) for a in ACTIONS]])
    return canonical([roots,rows])


def posterior(data):
    groups={};raw=0
    for m in MODELS:
        if all(trace(m,d['context'],d['actions'],d.get('transfer',False))==d['observations'] for d in data):
            raw+=1;groups.setdefault(behavior(m),m)
    if not groups:raise ValueError('INCONSISTENT_PUBLIC_OBSERVATIONS')
    return tuple(groups.values()),raw


def distribution(models,question,transfer=False):
    return Counter(tuple(trace(m,question['context'],question['actions'],transfer)) for m in models)


def risk(models,questions):
    return sum(1-max(distribution(models,q).values())/len(models) for q in questions)/len(questions)


def experiment(models,context,actions,questions):
    buckets={}
    for m in models:buckets.setdefault(tuple(trace(m,context,actions)),[]).append(m)
    n=len(models);ig=math.log2(n)-sum(len(b)/n*math.log2(len(b)) for b in buckets.values())
    after_risk=sum(len(b)/n*risk(b,questions) for b in buckets.values())
    return {'IG':ig,'risk_before':risk(models,questions),'expected_risk_after':after_risk,
        'probe_risk_reduction':risk(models,questions)-after_risk,
        'outcomes':[{'observations':list(o),'posterior_behavior_count':len(b),
            'probability':len(b)/n,'holdout_distributions':[
                [{'trace':list(t),'count':count} for t,count in sorted(distribution(b,q).items())] for q in questions]}
            for o,b in sorted(buckets.items())]}


def probe_law(data,questions):
    models,raw=posterior(data);entries=[]
    for c in [0,1]:
        for word in words(3):entries.append({'context':c,'actions':list(word),**experiment(models,c,word,questions)})
    return {'raw_models':raw,'behavior_classes':len(models),'IG_star':max(x['IG'] for x in entries),
        'best_risk_reduction':max(x['probe_risk_reduction'] for x in entries),'experiments':entries}


def optimal_public_probe(law, objective='target_risk'):
    """QA/reference ranking. NEVER include result in model-facing packets.

    Only uses the full public behavior class, no selected transition law.
    Deterministic tie ordering makes the protocol reproducible.
    """
    if objective not in {'entropy','target_risk'}:raise ValueError('UNKNOWN_PROBE_OBJECTIVE')
    entries=law['experiments']
    if not entries:raise ValueError('EMPTY_PUBLIC_EXPERIMENT_CLASS')
    primary,secondary=('probe_risk_reduction','IG') if objective=='target_risk' else ('IG','probe_risk_reduction')
    first=max(r[primary] for r in entries);tied=[r for r in entries if first-r[primary]<=1e-10]
    second=max(r[secondary] for r in tied);tied=[r for r in tied if second-r[secondary]<=1e-10]
    return min(tied,key=lambda r:(len(r['actions']),r['context'],tuple(r['actions'])))


def public_probe_objective_gap(law, probe):
    """Expected target-loss regret of a probe, never a realized success claim."""
    gap=law['best_risk_reduction']-probe['probe_risk_reduction']
    if gap < -1e-10:raise ValueError('RISK_EXCEEDS_PUBLIC_OPTIMUM')
    return max(0.,gap)

def make_history(model,context,actions,transfer=False):
    obs=trace(model,context,actions,transfer)
    features={'context':bool(context),'current_sensor':bool(obs[-1]),'last_is_a':bool(actions and actions[-1]=='a'),
        'last_is_b':bool(actions and actions[-1]=='b'),'count_a_odd':bool(actions.count('a')%2),
        'count_b_odd':bool(actions.count('b')%2),'length_odd':bool(len(actions)%2)}
    return {'context':context,'actions':list(actions),'observations':obs,'features':features,
        'events':[{'is_a':a=='a','is_b':a=='b','sensor':bool(o)} for a,o in zip(actions,obs[1:])]}


def history_domain(model,negative=False,transfer=False):
    return [make_history(model,c,list(w),transfer) for c in [0,1]
        for w in words(4,('read',) if negative else ('a','b'),True)]


def future(model,h,actions,transfer=False):
    full=trace(model,h['context'],h['actions']+list(actions),transfer)
    return full[len(h['actions']):]
