"""Typed, source-aligned proposals and exact explicitly closed finite models."""

import hashlib
from itertools import product
from ..core import digest, canonical
from .ir import need, Budget, Bound


def check_source(s):
    need(isinstance(s,dict) and set(s)=={'text_utf8','sha256','spans','context_refs','rights'},'INVALID_TEXT_SOURCE')
    need(isinstance(s['text_utf8'],str) and len(s['text_utf8'].encode())<=48000 and hashlib.sha256(s['text_utf8'].encode()).hexdigest()==s['sha256'],'SOURCE_MISMATCH')
    need(isinstance(s['rights'],str) and bool(s['rights'].strip()) and len(s['rights'])<=2048,'RIGHTS_REQUIRED')
    need(isinstance(s['spans'],list) and len(s['spans'])<=128 and isinstance(s['context_refs'],list) and len(s['context_refs'])<=32 and all(isinstance(x,str) and len(x)==64 for x in s['context_refs']),'SOURCE_METADATA_BOUND')
    for link in s['spans']:check_link(s,link)
    return s


def check_link(source,link):
    need(isinstance(link,dict) and set(link)=={'byte_utf8','literal'},'INVALID_TOKEN_LINK')
    v=link['byte_utf8'];need(isinstance(v,list) and len(v)==2 and all(type(x) is int for x in v) and 0<=v[0]<=v[1]<=len(source['text_utf8'].encode()),'INVALID_SOURCE_SPAN')
    need(source['text_utf8'].encode()[v[0]:v[1]].decode()==link['literal'],'SOURCE_SPAN_TEXT_MISMATCH')


def signature(sig):
    need(isinstance(sig,dict) and set(sig)=={'sorts','predicates'} and isinstance(sig['sorts'],list) and 1<=len(sig['sorts'])<=4 and all(isinstance(s,str) and 0<len(s)<=128 for s in sig['sorts']) and len(set(sig['sorts']))==len(sig['sorts']),'INVALID_SIGNATURE')
    need(isinstance(sig['predicates'],dict) and len(sig['predicates'])<=4,'INVALID_PREDICATES')
    for k,args in sig['predicates'].items():need(isinstance(k,str) and 0<len(k)<=128 and isinstance(args,list) and 0<len(args)<=3 and all(s in sig['sorts'] for s in args),'INVALID_PREDICATE_SORTS')
    return sig


def typecheck(phi,sig):
    try:
        signature(sig);count=0
        def term(t,env):
            need(isinstance(t,dict) and set(t)=={'var'} and isinstance(t['var'],str) and t['var'] in env,'UNBOUND_OR_INVALID_VARIABLE')
            return env[t['var']]
        def go(p,env,depth):
            nonlocal count
            count+=1;need(count<=128 and depth<=16,'FORMULA_BOUND')
            need(isinstance(p,dict),'INVALID_FORMULA')
            if set(p)=={'pred','args'}:
                need(p['pred'] in sig['predicates'] and isinstance(p['args'],list),'UNKNOWN_PREDICATE')
                need([term(t,env) for t in p['args']]==sig['predicates'][p['pred']],'PREDICATE_SORT_MISMATCH')
            elif set(p)=={'eq'}:
                need(isinstance(p['eq'],list) and len(p['eq'])==2 and term(p['eq'][0],env)==term(p['eq'][1],env),'EQUALITY_SORT_MISMATCH')
            elif set(p)=={'not'}:go(p['not'],env,depth+1)
            elif set(p) in ({'and'},{'or'}):
                xs=p.get('and',p.get('or'));need(isinstance(xs,list) and 1<=len(xs)<=16,'INVALID_CONNECTIVE')
                for x in xs:go(x,env,depth+1)
            elif set(p)=={'quant','var','sort','body'}:
                need(p['quant'] in ('forall','exists') and p['sort'] in sig['sorts'] and isinstance(p['var'],str) and 0<len(p['var'])<=128 and p['var'] not in env,'INVALID_OR_SHADOWED_BINDER')
                go(p['body'],{**env,p['var']:p['sort']},depth+1)
            else:raise ValueError('INVALID_FORMULA_OPERATOR')
        go(phi,{},0);return {'status':'TYPED','nodes':count,'formula_sha256':digest(phi),'signature_sha256':digest(sig)}
    except (ValueError,TypeError,KeyError,RecursionError) as exc:return {'status':'TYPE_REJECTED','reason':str(exc)}


def check_model(model,sig):
    signature(sig)
    need(isinstance(model,dict) and set(model)=={'domains','relations','world'} and model['world'] in ('closed','open'),'INVALID_MODEL')
    need(isinstance(model['domains'],dict) and set(model['domains'])==set(sig['sorts']),'MODEL_SORT_MISMATCH')
    for sort,domain in model['domains'].items():need(isinstance(domain,list) and 1<=len(domain)<=4 and all(isinstance(x,str) and 0<len(x)<=128 for x in domain) and len(set(domain))==len(domain),'INVALID_FINITE_DOMAIN')
    need(isinstance(model['relations'],dict) and set(model['relations'])==set(sig['predicates']),'MODEL_PREDICATE_MISMATCH')
    for pred,tuples in model['relations'].items():
        need(isinstance(tuples,list) and len(tuples)<=64,'MODEL_RELATION_BOUND')
        sorts=sig['predicates'][pred]
        for row in tuples:need(isinstance(row,list) and len(row)==len(sorts) and all(v in model['domains'][s] for v,s in zip(row,sorts)),'MODEL_TUPLE_SORT_MISMATCH')
        need(len({canonical(x) for x in tuples})==len(tuples),'DUPLICATE_MODEL_TUPLE')
    return model


def evaluate(phi,sig,model,bounds):
    typed=typecheck(phi,sig)
    if typed['status']!='TYPED':return {'status':'ILL_TYPED','typecheck':typed,'truth':None,'execution_permission':False}
    check_model(model,sig)
    if model['world']!='closed':return {'status':'UNKNOWN','reason':'OPEN_WORLD_RELATIONS_NOT_COMPLETE','truth':None,'execution_permission':False}
    work=Budget(bounds);steps=0;relations={k:{tuple(x) for x in rows} for k,rows in model['relations'].items()}
    def go(p,env):
        nonlocal steps
        work.tick();steps+=1
        if 'pred' in p:return tuple(env[t['var']] for t in p['args']) in relations[p['pred']]
        if 'eq' in p:return env[p['eq'][0]['var']]==env[p['eq'][1]['var']]
        if 'not' in p:return not go(p['not'],env)
        if 'and' in p:return all(go(x,env) for x in p['and'])
        if 'or' in p:return any(go(x,env) for x in p['or'])
        xs=(go(p['body'],{**env,p['var']:v}) for v in model['domains'][p['sort']])
        return all(xs) if p['quant']=='forall' else any(xs)
    try:
        truth=go(phi,{})
        return {'status':'TRUE' if truth else 'FALSE','truth':truth,'proof_status':'FINITE_MODEL_CHECKED','formula_sha256':digest(phi),'model_sha256':digest(model),'signature_sha256':digest(sig),'evaluated_nodes':steps,'semantic_alignment_status':'PROPOSED','execution_permission':False}
    except Bound:return {'status':'UNKNOWN_BOUND','truth':None,'execution_permission':False}


def propose(source,provider,sig,proposals,source_ref=None):
    check_source(source);signature(sig)
    need(isinstance(provider,dict) and set(provider)=={'kind','provenance'} and provider['kind'] in ('human','imported','white_star','external_llm') and isinstance(provider['provenance'],dict) and bool(provider['provenance']),'INVALID_PROVIDER')
    need(isinstance(proposals,list) and 1<=len(proposals)<=16,'PROPOSAL_BOUND')
    candidates=[]
    for proposal in proposals:
        need(isinstance(proposal,dict) and set(proposal)=={'formula_ast','assumptions','token_role_links','construction_trace'},'INVALID_PROPOSAL')
        need(isinstance(proposal['assumptions'],list) and len(proposal['assumptions'])<=16 and isinstance(proposal['token_role_links'],list) and 1<=len(proposal['token_role_links'])<=128 and isinstance(proposal['construction_trace'],list) and 1<=len(proposal['construction_trace'])<=64,'PROPOSAL_PROVENANCE_REQUIRED')
        for link in proposal['token_role_links']:check_link(source,link)
        for assumption in proposal['assumptions']:
            need(typecheck(assumption,sig)['status']=='TYPED','ILL_TYPED_ASSUMPTION')
        typed=typecheck(proposal['formula_ast'],sig)
        derivation={'source_ref':source_ref or digest(source),'source_sha256':source['sha256'],'signature':sig,**proposal,'candidate_provider':provider}
        candidate={'schema':'formal-candidate/1',**derivation,'type_status':typed['status'],'typecheck':typed,'proof_status':'PROPOSED','semantic_alignment_status':'PROPOSED','alternative_parse_refs':[],'limitation_tags':['NO_GENERAL_NL_DECODER','NO_AUTHOR_INTENT_CLAIM','FINITE_MODELS_ONLY'],'execution_permission':False}
        candidate['derivation_hash']=digest(derivation);candidate['candidate_id']=digest([candidate['derivation_hash'],len(candidates)]);candidates.append(candidate)
    for c in candidates:c['alternative_parse_refs']=[x['candidate_id'] for x in candidates if x is not c]
    return {'schema':'formal-interpretations/1','status':'PROPOSED','source_ref':source_ref or digest(source),'candidates':candidates,'generation':'EXPLICIT_PROVIDER_PROPOSALS_NOT_AUTOMATIC_NLP','execution_permission':False}


def countermodels(candidates,bounds):
    need(2<=len(candidates)<=16 and all(c['type_status']=='TYPED' for c in candidates),'TYPED_CANDIDATES_REQUIRED')
    sig=candidates[0]['signature'];need(all(c['signature']==sig for c in candidates),'SIGNATURE_MISMATCH')
    signature(sig);work=Budget(bounds);checked=0
    try:
        for size in [1,2]:
            domains={s:[s+':'+str(i) for i in range(size)] for s in sig['sorts']}
            cells=[(p,list(row)) for p,sorts in sorted(sig['predicates'].items()) for row in product(*(domains[s] for s in sorts))]
            if len(cells)>16:raise Bound('RELATION_CELL_BOUND')
            for bits in product([False,True],repeat=len(cells)):
                work.tick()
                if checked>=bounds['max_models']:raise Bound('MODEL_BOUND')
                checked+=1;model={'domains':domains,'relations':{p:[] for p in sig['predicates']},'world':'closed'}
                for (p,row),bit in zip(cells,bits):
                    if bit:model['relations'][p].append(row)
                # Compare interpretations on their explicitly shared domain of
                # applicability; a violated assumption is not a countermodel.
                assumption_truths=[[evaluate(a,sig,model,bounds)['truth'] for a in c['assumptions']] for c in candidates]
                if any(v is None for xs in assumption_truths for v in xs):raise Bound('ASSUMPTION_EVALUATION_BOUND')
                if not all(all(xs) for xs in assumption_truths):continue
                values=[evaluate(c['formula_ast'],sig,model,bounds)['truth'] for c in candidates]
                if None in values:raise Bound('MODEL_EVALUATION_BOUND')
                if len(set(values))>1:return {'schema':'formal-contrast/1','status':'FINITE_COUNTERMODEL','model':model,'model_sha256':digest(model),'candidate_ids':[c['candidate_id'] for c in candidates],'truth_vector':values,'assumption_truth_vectors':assumption_truths,'comparison_scope':'ALL_CANDIDATE_ASSUMPTIONS_HOLD','models_checked':checked,'equivalence_claim':False,'execution_permission':False}
        return {'schema':'formal-contrast/1','status':'NO_COUNTERMODEL_WITHIN_BOUND','models_checked':checked,'equivalence_claim':False,'execution_permission':False}
    except Bound as exc:return {'schema':'formal-contrast/1','status':'UNKNOWN_BOUND','reason':str(exc),'models_checked':checked,'equivalence_claim':False,'execution_permission':False}
