"""Independent raw execution and exhaustive finite oracle; no core/port imports."""
from fractions import Fraction
from itertools import combinations
import json


def unpack(history: dict,query: dict) -> tuple:
    rows={'event:'+str(e['id']):json.loads(e['content']) for e in history['tables']['events']}
    return rows[query['root_ref']]['source_spec'],{r:d['word'] for r,d in rows.items() if 'word' in d}


def raw_run(word: list, p: dict, suffix: list, observer: dict) -> dict:
    v=p['initial'][: ] if isinstance(p['initial'],list) else p['initial'];history=[];flags=[];defined=True
    def balance():
        result=0
        for token in history:
            i=p['actions'].index(token)
            if i==0:result+=1
            if i==1:result-=1
            if i==2:result=0
        return result
    for at,a in enumerate(word+suffix):
        role=p['actions'].index(a);allowed=True
        if p['family']=='rewrite':allowed=(role!=0 or len(v)>0) and (role!=1 or len(v)<p['max_word'])
        if p['family']=='history':allowed=(role!=0 or balance()<p['capacity']) and (role!=1 or balance()>0)
        if at>=len(word):flags.append(allowed)
        if not allowed:
            if at<len(word):raise ValueError('Oracle invalid initial source')
            defined=False;break
        if p['family']=='register':v=[(v[0]+role*v[1])%p['modulus'],(v[1]+role)%p['modulus']]
        elif p['family']=='rewrite':
            if role==0:v=v[1:]
            elif role==1:v=v+[p['letters'][0]]
            else:
                for i in range(len(v)-1):
                    if v[i:i+2]==p['letters']:
                        v=v[:i+1]+v[i+2:];break
        elif p['family']=='permutation':
            old=v[:];v=[p['permutations'][role][x] for x in old]
        elif p['family']=='history':
            if role==2:v=0
            elif role==3:v=balance()
            else:v=(v+1)%p['display_mod']
        history.append(a)
    if not defined:o=None
    elif p['family']=='rewrite':o=v[0] if v else 'EMPTY'
    else:
        o=v[0] if p['family'] in {'register','permutation'} else v
        if observer['mod'] is not None:o%=observer['mod']
    return {'defined':defined,'observation':o,'admissibility':flags}


def signatures(history: dict,query: dict) -> dict:
    spec,words=unpack(history,query)
    return {r:{t['id']:raw_run(words[r],spec['parameters'],t['suffix'],spec['observer']) for t in spec['tests']} for r in spec['histories']}


def pairs(history: dict,query: dict) -> list:
    spec,words=unpack(history,query);table=signatures(history,query);result=[]
    for l,r in combinations(spec['histories'],2):
        current=[raw_run(words[ref],spec['parameters'],[],spec['observer'])['observation'] for ref in (l,r)]
        differences=[t['id'] for t in spec['tests'] if table[l][t['id']]!=table[r][t['id']]]
        result.append({'left':l,'right':r,'current':current,'hidden':current[0]==current[1] and bool(differences),'different_tests':differences,
                       'Sig_left':table[l],'Sig_right':table[r]})
    return result


def attention(history: dict,query: dict,receipt=None) -> dict:
    spec,words=unpack(history,query);table=signatures(history,query)
    status={h['id']:'ACTIVE' for h in spec['hypotheses']}
    for h in spec['hypotheses']:
        if h['question']=='current' and raw_run(words[h['ref']],spec['parameters'],[],spec['observer'])['observation']!=spec['current_observation']:
            status[h['id']]='OUTSIDE_CURRENT_OBSERVATION'
        if receipt and h['predictive'] and status[h['id']]=='ACTIVE' and table[h['ref']][receipt['test_id']]!=receipt['readout']:
            status[h['id']]='EXCLUDED_BY_OBSERVATION'
    if receipt:
        for _ in range(len(status)):
            for h in spec['hypotheses']:
                if status[h['id']]=='ACTIVE' and any(status[d]!='ACTIVE' for d in h['depends_on']):status[h['id']]='EXCLUDED_DEPENDENCY'
    active=[h for h in spec['hypotheses'] if h['predictive'] and h['question']=='current' and status[h['id']]=='ACTIVE']
    ranks=[]
    for t in spec['tests']:
        if len(active)<2:continue
        vals=[table[h['ref']][t['id']] for h in active]
        if not all(v['defined'] and all(v['admissibility']) for v in vals) or all(v==vals[0] for v in vals):continue
        total=sum(h['weight'] for h in active)
        remaining=sum(Fraction(h['weight'])*sum(table[h['ref']][t['id']]==table[k['ref']][t['id']] for k in active) for h in active)/total
        loss=t['cost']+Fraction(7,3)*remaining
        ranks.append({'test_id':t['id'],'suffix':t['suffix'],'cost':t['cost'],'ordinal':t['ordinal'],'loss':str(loss),'expected_remaining':str(remaining)})
    ranks.sort(key=lambda x:(Fraction(x['loss']),x['cost'],x['ordinal']))
    return {'status':'ATTENTION_PROPOSED' if ranks else 'NO_INFORMATIVE_TEST',
            'selected_test_id':ranks[0]['test_id'] if ranks else None,'ranking':ranks,'statuses':status,
            'ties':[r['test_id'] for r in ranks if r['loss']==ranks[0]['loss']] if ranks else []}
