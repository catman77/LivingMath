"""Pure bounded operations behind the existing isolated worker action."""

from itertools import product
from ..core import digest
from ..observer_synthesis.data import validate_record
from .ir import limits, need, Budget, Bound, grammar, dfa
from .chart import parse
from .proof_checker import verify
from . import fol


def membership(ast,record,bounds):
    if ast['schema']=='formal-dfa-ir/1':
        from .dfa import run
        return run(ast,record,bounds)
    return parse(ast,record,bounds)


def contrast(candidates,bounds):
    need(2<=len(candidates)<=16,'CANDIDATE_COUNT')
    if all('formula_ast' in c for c in candidates):return fol.countermodels(candidates,bounds)
    need(all('ast' in c for c in candidates),'CANDIDATE_KIND_MISMATCH')
    alphabet=sorted({t for c in candidates for t in c['ast'].get('terminals',c['ast'].get('alphabet',[]))});work=Budget(bounds);tested=0
    import hashlib
    try:
        for n in range(bounds['max_length']+1):
            for word in product(alphabet,repeat=n):
                work.tick()
                if tested>=bounds['max_words']:raise Bound('WORD_BOUND')
                tested+=1;text=' '.join(word);record={'id':digest(list(word)),'tokens':list(word),'source':{'text':text,'sha256':hashlib.sha256(text.encode()).hexdigest(),'rights':'SYSTEM_GENERATED_CONTRAST','edition':'formal-contrast/1'}}
                values=[];proofs=[]
                for c in candidates:
                    p=membership(c['ast'],record,bounds);checked=verify(c['ast'],record,bounds,p)
                    if checked['status']!='CHECKED_INSTANCE':raise Bound('MEMBERSHIP_UNKNOWN')
                    values.append(checked['decision']);proofs.append(digest(p))
                if len(set(values))>1:return {'schema':'formal-contrast/1','status':'DISTINGUISHING_QUERY','query':record,'candidate_ids':[c['candidate_id'] for c in candidates],'prediction_vector':values,'proof_sha256':proofs,'words_checked':tested,'correct_label':None,'external_annotation_required':True,'equivalence_claim':False,'execution_permission':False}
        return {'schema':'formal-contrast/1','status':'NO_DIFFERENCE_WITHIN_BOUND','words_checked':tested,'equivalence_claim':False,'execution_permission':False}
    except Bound as exc:return {'schema':'formal-contrast/1','status':'UNKNOWN_BOUND','reason':str(exc),'words_checked':tested,'equivalence_claim':False,'execution_permission':False}


def synthesize(train,queries,constraints,bounds):
    need(isinstance(constraints,dict) and set(constraints)=={'kind'} and constraints['kind'] in ('cfg','dfa'),'INVALID_CONSTRAINTS')
    need(0<len(train)<=256 and len(queries)<=256,'DATASET_BOUND')
    for r in train:validate_record(r,'train')
    if constraints['kind']=='dfa':
        from .dfa import fit
        model=fit(train,bounds)
        for c in model['candidates']:
            for r in train:
                p=membership(c['ast'],r,bounds);checked=verify(c['ast'],r,bounds,p)
                need(checked['status']=='CHECKED_INSTANCE' and checked['decision']==r['accepted'],'INDEPENDENT_ADMISSION_FAILURE')
    else:
        from .search import fit
        model=fit(train,constraints,bounds)
    seal=digest(model);predictions=[]
    selected=next((c for c in model['candidates'] if c['candidate_id']==model['selected']),None)
    work=Budget(bounds)
    for r in queries:
        work.tick();validate_record(r,'queries')
        if selected is None:
            predictions.append({'record_ref':digest(r),'record_id':r['id'],'decision':None,'status':'UNKNOWN_NO_COMPATIBLE_MODEL','source_sha256':r['source']['sha256']});continue
        proof=membership(selected['ast'],r,bounds);checked=verify(selected['ast'],r,bounds,proof)
        need(checked['status']!='REJECTED_PROOF','PRODUCER_PROOF_REJECTED')
        predictions.append({'record_ref':digest(r),'record_id':r['id'],'source_sha256':r['source']['sha256'],'decision':checked['decision'],'status':checked['status'],'proof':proof,'verification':checked})
    need(digest(model)==seal,'HYPOTHESIS_MUTATED')
    return {'schema':'formal-synthesis-result/1','status':model['status'],'model':model,'model_sha256':seal,'predictions':predictions,'checks':{'hypothesis_frozen_before_queries':True,'holdout_labels_read':False,'LLM_calls':0,'execution_permission':False},'execution_permission':False}


def dispatch(packet):
    operation=packet['operation'];p=packet['payload'];b=limits(p.get('budget'))
    if operation=='store':
        kind=p['kind'];value=p['data']
        if kind=='source':fol.check_source(value)
        elif kind=='record':validate_record(value,'queries')
        elif kind=='grammar':grammar(value)
        elif kind=='dfa':dfa(value)
        elif kind=='model':need(isinstance(value,dict) and set(value)=={'domains','relations','world'},'INVALID_MODEL')
        elif kind=='proof':need(isinstance(value,dict) and value.get('schema')=='formal-membership-proof/1','INVALID_PROOF_SCHEMA')
        else:raise ValueError('INVALID_STORED_KIND')
        return {'status':'STORED','kind':kind,'value':value,'object_ref':digest(value),'origin':'IMPORTED_DATA_NOT_INDUCED','execution_permission':False}
    if operation=='synthesize':return synthesize(p['train'],p['queries'],p['constraints'],b)
    if operation=='verify':
        ast=p['candidate']['ast'];record=p['record'];validate_record(record,'train' if 'accepted' in record else 'queries')
        proof=p.get('proof')
        if proof is None:proof=membership(ast,record,b)
        return {'status':'CHECKED_INSTANCE' if (v:=verify(ast,record,b,proof))['status']=='CHECKED_INSTANCE' else v['status'],'verification':v,'proof':proof,'candidate_id':p['candidate']['candidate_id'],'execution_permission':False}
    if operation=='contrast':return contrast(p['candidates'],b)
    if operation=='interpret':return fol.propose(p['source'],p['candidate_provider'],p['target_signature'],p['proposals'],p.get('source_ref'))
    if operation=='model_check':
        c=p['candidate'];result=fol.evaluate(c['formula_ast'],c['signature'],p['model'],b)
        result['assumption_results']=[fol.evaluate(a,c['signature'],p['model'],b) for a in c['assumptions']]
        result['candidate_id']=c['candidate_id'];return result
    if operation=='replay':
        need(p['original']['action']=='observer_verify' and p['original']['formal_packet']['operation']!='replay','INVALID_REPLAY_PACKET')
        value=dispatch(p['original']['formal_packet']);actual=digest(value)
        return {'status':'REPLAY_MATCH' if actual==p['expected_sha256'] else 'REPLAY_MISMATCH','replayed_result_sha256':actual,'original_run_ref':p['original_run_ref'],'execution_permission':False}
    raise ValueError('INVALID_FORMAL_OPERATION')
