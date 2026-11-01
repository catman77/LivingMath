"""014 attention: select an untested guarded consequence, never a synthetic hypothesis."""
from operational013 import TransportRefusal


def forecast(law, port, image, word):
    current=list(image);flags=[]
    try:
        for action in word:
            if not port.guard_image(current,action):
                return {'status':'GUARD_INSUFFICIENT','reason':'NATIVE_OR_SCOPED_GUARD','flags':flags+[False]}
            following=law.step(current,action)
            if not port.within_guard(following):
                return {'status':'GUARD_INSUFFICIENT','reason':'NEXT_STATE_OUTSIDE_G','flags':flags}
            current=following;flags.append(True)
        return {'status':'FORECAST','coordinate':current,'readout':{'defined':True,
                'observation':port.observe_image(current,law.binding['observer']),'admissibility':flags}}
    except TransportRefusal as error:
        return {'status':'GUARD_INSUFFICIENT','reason':str(error),'flags':flags}


def select_validation(law,port,image,context_word,domain,executed_words,covered_pairs=(),review_required=False):
    """Pure finite-domain attention; native calls restricted to G/A/O, never E."""
    if review_required:
        return {'status':'REQUIRES_REVIEW','reason':'A committed law counterexample remains unresolved.','execution_permission':{'allowed':False}}
    if law.status!='CANDIDATE_TRANSPORT':
        return {'status':'UNKNOWN_BOUNDED','reason':law.status,'execution_permission':{'allowed':False}}
    candidates=[];rejected=[];seen={tuple(w) for w in executed_words};covered=set(map(tuple,covered_pairs))
    for probe in domain:
        word=probe['word'];full=tuple(context_word+word)
        if full in seen:
            rejected.append({'id':probe['id'],'reason':'ALREADY_EXECUTED_SOURCE_CONTINUATION'});continue
        prediction=forecast(law,port,image,word)
        if prediction['status']!='FORECAST':
            rejected.append({'id':probe['id'],'reason':prediction['status'],'detail':prediction});continue
        new=len(set(zip(word,word[1:]))-covered)
        candidates.append({**probe,'prediction':prediction,'new_adjacent_pairs':new,
                           'score':[-new,-len(word),probe['cost'],probe['ordinal']]})
    candidates.sort(key=lambda p:p['score'])
    if not candidates:
        return {'status':'GUARD_INSUFFICIENT' if any(r['reason']=='GUARD_INSUFFICIENT' for r in rejected) else 'NO_UNTESTED_GUARDED_PROBE',
                'rejected':rejected,'execution_permission':{'allowed':False},'proof_status':'unverified'}
    return {'status':'ATTENTION_PROPOSED','purpose':'VALIDATE_TRANSFER','selected':candidates[0],
            'ranking':candidates,'rejected':rejected,'new_distinction_claimed':False,
            'execution_permission':{'allowed':False},'proof_status':'unverified'}


def dispatch(discrimination,law,port,image,context_word,domain,executed_words,covered_pairs=(),review_required=False):
    if review_required:
        return select_validation(law,port,image,context_word,domain,executed_words,covered_pairs,True)
    if discrimination['status']=='ATTENTION_PROPOSED':
        return {'status':'ATTENTION_PROPOSED','purpose':'DISCRIMINATE','discrimination':discrimination,
                'execution_permission':{'allowed':False},'proof_status':'unverified'}
    active=[h for h in discrimination.get('hypotheses',[]) if h['status']=='ACTIVE' and h['question']=='current' and h['predictive']]
    if len(active)!=1:
        return {'status':'UNKNOWN_BOUNDED','reason':'No unique current context after discrimination.','execution_permission':{'allowed':False}}
    return select_validation(law,port,image,context_word,domain,executed_words,covered_pairs)
