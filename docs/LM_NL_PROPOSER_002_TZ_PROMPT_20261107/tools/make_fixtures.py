#!/usr/bin/env python3
"""Dev fixtures only. NEVER import this oracle into a production NL proposer."""
import hashlib, json, pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
q='Каждый исследователь проверил одну гипотезу.'
lex=['Каждый студент прочитал одну книгу.','Каждый студент потерял одну книгу.']

def sha(s): return hashlib.sha256(s.encode('utf-8')).hexdigest()
def span(s,term):
    start=len(s[:s.index(term)].encode('utf-8'))
    return {'byte_utf8':[start,start+len(term.encode('utf-8'))], 'literal':term}

def var(x):return {'var':x}
def atom(a='r',b='h'):return {'pred':'Checked','args':[var(a),var(b)]}
def qua(kind,v,sort,body):return {'quant':kind,'var':v,'sort':sort,'body':body}
I1=qua('forall','r','researcher',qua('exists','h','hypothesis',atom()))
I2=qua('exists','h','hypothesis',qua('forall','r','researcher',atom()))
I3=qua('forall','r','researcher',qua('exists','h','hypothesis',{'and':[atom(),qua('forall','h2','hypothesis',{'or':[{'not':atom('r','h2')},{'eq':[var('h2'),var('h')]}]})]}))
I4=qua('forall','r','researcher',qua('forall','h','hypothesis',atom()))
model1={'domains':{'researcher':['r1','r2'],'hypothesis':['h1','h2']},'relations':{'Checked':[['r1','h1'],['r2','h2']]},'world':'closed'}
model2={'domains':{'researcher':['r1','r2'],'hypothesis':['h1','h2']},'relations':{'Checked':[['r1','h1'],['r1','h2'],['r2','h1']]},'world':'closed'}
fixture={'schema':'lm-nl-proposer-dev-fixtures/1','status':'HAND_AUTHORED_DEVELOPMENT_REFERENCE_NOT_BLIND','primary_source':{'text_utf8':q,'sha256':sha(q),'rights':'synthetic-original','spans':[span(q,k) for k in ['Каждый','исследователь','проверил','одну','гипотезу']]},'target_signature':{'sorts':['researcher','hypothesis'],'predicates':{'Checked':['researcher','hypothesis']}},'formal_candidates':[{'id':n,'source':'human-dev-reference','formula_ast':f,'token_role_links':[span(q,'Каждый'),span(q,'одну')],'assumptions':[],'expected_status':'PROPOSED_AND_TYPED_NOT_SEMANTICALLY_PROVED'} for n,f in [('I1_each_at_least_one',I1),('I2_shared_one',I2),('I3_each_exactly_one',I3),('I4_overstrong_adversarial',I4)]],'finite_models':[{'id':'M1_distinct','model':model1,'expected_truth_vector':{'I1_each_at_least_one':True,'I2_shared_one':False,'I3_each_exactly_one':True,'I4_overstrong_adversarial':False}},{'id':'M2_common_multiple','model':model2,'expected_truth_vector':{'I1_each_at_least_one':True,'I2_shared_one':True,'I3_each_exactly_one':False,'I4_overstrong_adversarial':False}}], 'alpha_pair':[{'text_utf8':x,'sha256':sha(x),'tokens':x.split(),'alpha_pattern':list(range(len(x.split()))),'disclaimer':'alpha-equivalence does not imply predicate/semantic equivalence'} for x in lex],'negative_provenance':{'provider_kind':'white_star','fake_run_id':'0'*64,'fake_frame_id':'F99','expected_in_new_verified_path':'UNBACKED_ORIGIN','expected_old_formal_interpret':'DECLARATION_ACCEPTED_AS_PROPOSED'},'negative_span':{'claimed_literal':'Каждый','incorrect_byte_utf8':span(q,'исследователь')['byte_utf8'],'existing_checker_status':'SOURCE_SPAN_TEXT_MISMATCH'}}
(ROOT/'fixtures'/'DEV_SOURCE_AND_FOL.json').write_text(json.dumps(fixture,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('fixture',ROOT/'fixtures'/'DEV_SOURCE_AND_FOL.json')
