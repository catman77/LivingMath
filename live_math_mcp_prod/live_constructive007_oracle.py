"""Independent raw replay; no constructor, certificate validator or native imports."""
from itertools import combinations
from fractions import Fraction
import json


def unpack(history,q):
    rows={'event:'+str(e['id']):json.loads(e['content']) for e in history['tables']['events']}
    return rows[q['root_ref']]['source_spec'],{r:p['word'] for r,p in rows.items() if 'word' in p}


def run(word,suffix,p,observer):
    state=p['initial'][:];history=[];flags=[];defined=True
    for i,a in enumerate(word+suffix):
        role=p['actions'].index(a)
        ok=not (p['family']=='boundary' and history and p['actions'].index(history[0])==1 and role==len(p['actions'])-1)
        if i>=len(word):flags.append(ok)
        if not ok:
            if i<len(word):raise ValueError('Invalid source prefix')
            defined=False;break
        if p['family']=='affine':
            k=p['coefficients'][role];old=state[:];state=[(old[0]+k*old[1])%p['modulus'],(old[1]+k)%p['modulus']]
        elif p['family']=='permutation':
            old=state[:];state=[old[j] for j in p['permutations'][role]]
        elif p['family']=='erasure':state=state[p['cuts'][role]:]
        history.append(a)
    if not defined:value=None
    elif p['family']=='opaque':
        roles=[p['actions'].index(a) for a in history]
        value=roles[0]%2 if len(roles)>=3 and sum(roles[-2:])==2*(len(p['actions'])-1) else 0
    elif p['family']=='boundary':value=0
    else:
        value=state[0] if state else 'EMPTY'
        if observer['mod'] is not None:value%=observer['mod']
    return {'defined':defined,'observation':value,'admissibility':flags}


def signature(history,q):
    spec,words=unpack(history,q)
    return {r:{t['id']:run(words[r],t['suffix'],spec['parameters'],spec['observer']) for t in spec['tests']} for r in spec['histories']}


def pairs(history,q):
    spec,words=unpack(history,q);table=signature(history,q);out=[]
    for l,r in combinations(spec['histories'],2):
        now=[run(words[ref],[],spec['parameters'],spec['observer'])['observation'] for ref in (l,r)]
        diff=[t['id'] for t in spec['tests'] if table[l][t['id']]!=table[r][t['id']]]
        out.append({'left':l,'right':r,'current':now,'hidden':now[0]==now[1] and bool(diff),'different_tests':diff,
                    'Sig_left':table[l],'Sig_right':table[r]})
    return out


def attention(history,q,receipt=None):
    spec,words=unpack(history,q);table=signature(history,q);statuses={h['id']:'ACTIVE' for h in spec['hypotheses']}
    for h in spec['hypotheses']:
        if h['question']=='current' and run(words[h['ref']],[],spec['parameters'],spec['observer'])['observation']!=spec['current_observation']:
            statuses[h['id']]='OUTSIDE_CURRENT_OBSERVATION'
        if receipt and h['predictive'] and statuses[h['id']]=='ACTIVE' and table[h['ref']][receipt['test_id']]!=receipt['readout']:statuses[h['id']]='EXCLUDED_BY_OBSERVATION'
    if receipt:
        for _ in statuses:
            for h in spec['hypotheses']:
                if statuses[h['id']]=='ACTIVE' and any(statuses[x]!='ACTIVE' for x in h['depends_on']):statuses[h['id']]='EXCLUDED_DEPENDENCY'
    hs=[h for h in spec['hypotheses'] if h['predictive'] and h['question']=='current' and statuses[h['id']]=='ACTIVE'];ranks=[]
    for t in spec['tests']:
        vals=[table[h['ref']][t['id']] for h in hs]
        if len(hs)<2 or not all(v['defined'] and all(v['admissibility']) for v in vals) or all(v==vals[0] for v in vals):continue
        total=sum(h['weight'] for h in hs)
        remaining=sum(Fraction(h['weight'])*sum(vals[i]==v for v in vals) for i,h in enumerate(hs))/total
        loss=t['cost']+Fraction(7,3)*remaining
        ranks.append({'test_id':t['id'],'suffix':t['suffix'],'cost':t['cost'],'ordinal':t['ordinal'],'loss':str(loss),'expected_remaining':str(remaining)})
    ranks.sort(key=lambda r:(Fraction(r['loss']),r['cost'],r['ordinal']))
    return {'status':'ATTENTION_PROPOSED' if ranks else 'NO_INFORMATIVE_TEST','selected_test_id':ranks[0]['test_id'] if ranks else None,
            'ranking':ranks,'statuses':statuses,'ties':[r['test_id'] for r in ranks if r['loss']==ranks[0]['loss']] if ranks else []}
