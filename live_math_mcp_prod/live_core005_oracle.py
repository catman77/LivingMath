"""Independent exhaustive finite oracle. Never imported by the I/T module."""
from fractions import Fraction
from itertools import combinations
import json


def source_spec(history: dict, query: dict) -> dict:
    row=next(r for r in history['tables']['events'] if 'event:'+str(r['id'])==query['root_ref'])
    return json.loads(row['content'])['source_spec']


def execute(word: list[int]) -> tuple[int,int]:
    state=(0,1)
    for token in word:
        old=state
        state=((old[0]+token*old[1]) % 5, (old[1]+token) % 5)
    return state


def observation(state: tuple, spec: dict) -> int:
    if spec['observer']=='x':return state[0]
    if spec['observer']=='parity':return state[0] % 2
    if spec['observer']=='constant':return 0
    raise ValueError('Oracle observer outside registration')


def word(history: dict, ref: str) -> list:
    return json.loads(next(e for e in history['tables']['events'] if 'event:'+str(e['id'])==ref)['content'])['word']


def signature(history: dict, query: dict, ref: str) -> list:
    spec=source_spec(history,query);prefix=word(history,ref);result=[]
    for test in spec['tests']:
        state=execute(prefix+test['suffix'])
        admissible=spec['forbidden_y'] is None or state[1]!=spec['forbidden_y']
        result.append({'test_id':test['id'],'suffix':test['suffix'],
                       'readout':[observation(state,spec),admissible]})
    return result


def all_pairs(history: dict, query: dict) -> list:
    spec=source_spec(history,query);result=[]
    for left,right in combinations(spec['histories'],2):
        a,b=signature(history,query,left),signature(history,query,right)
        now=[observation(execute(word(history,r)),spec) for r in (left,right)]
        result.append({'left_ref':left,'right_ref':right,'current':now,'Sig_left':a,'Sig_right':b,
                       'hidden_distinction':now[0]==now[1] and a!=b})
    return result


def attention(history: dict, query: dict, excluded: list[str] = ()) -> dict:
    spec=source_spec(history,query)
    h=[h for h in spec['hypotheses'] if h['predictive'] and h['question']=='current' and h['id'] not in excluded]
    if len(h)<2:return {'status':'NO_INFORMATIVE_TEST','optimal_test_ids':[],'ranks':[]}
    total=sum(Fraction(x['weight']) for x in h);ranks=[]
    # Full independent word/suffix enumeration and pairwise survivor counting.
    table={x['id']:{r['test_id']:r['readout'] for r in signature(history,query,x['history_ref'])} for x in h}
    for test in spec['tests']:
        values=[table[x['id']][test['id']] for x in h]
        if all(v==values[0] for v in values):continue
        remaining=sum(Fraction(x['weight'])*sum(table[x['id']][test['id']]==table[y['id']][test['id']] for y in h) for x in h)/total
        loss=Fraction(test['cost'])+Fraction(7,3)*remaining
        ranks.append({'test_id':test['id'],'cost':test['cost'],'loss':str(loss),'expected_remaining':str(remaining)})
    if not ranks:return {'status':'NO_INFORMATIVE_TEST','optimal_test_ids':[],'ranks':[]}
    ranks.sort(key=lambda r:(Fraction(r['loss']),r['cost'],r['test_id']))
    best=Fraction(ranks[0]['loss'])
    return {'status':'ATTENTION_PROPOSED','optimal_test_ids':sorted(r['test_id'] for r in ranks if Fraction(r['loss'])==best),
            'selected_test_id':ranks[0]['test_id'],'ranks':ranks}


def feedback(history: dict, query: dict, receipt: dict) -> dict:
    spec=source_spec(history,query);out={h['id']:'ACTIVE' for h in spec['hypotheses']}
    for hyp in spec['hypotheses']:
        if hyp['predictive'] and hyp['question']=='current':
            prediction=next(r['readout'] for r in signature(history,query,hyp['history_ref']) if r['test_id']==receipt['test_id'])
            if prediction!=receipt['readout']:out[hyp['id']]='EXCLUDED_BY_OBSERVATION'
    for _ in range(len(out)):
        for hyp in spec['hypotheses']:
            if out[hyp['id']]=='ACTIVE' and any(out[d]!='ACTIVE' for d in hyp['depends_on']):out[hyp['id']]='EXCLUDED_DEPENDENCY'
    return out
