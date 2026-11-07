#!/usr/bin/env python3
"""Independent, inexpensive reference acceptance; prints results and writes JSON.

Validates explicit grammar semantics and proof data. Does NOT mean that the
current MCP *discovered* any of these grammars, and does NOT train an LLM.
"""
import copy
import itertools
import json
import sys
from pathlib import Path
from reference_kernel import (
  GRAMMARS, PARITY_DFA, INTERPRETATIONS, model, truth_vector, eval_fol,
  parse, verify_parse, shortest_distinguishing_word, distinguishing_countermodel,
  typecheck_fol, SIGNATURE, Q, A, source_bound_envelope, verify_source_bound_envelope, rename_terminals,
)


REPORT = {'kind':'REFERENCE_TESTS_ONLY_NOT_MCP_DISCOVERY','checks':[], 'models':[], 'distinguishers':[]}
def check(name: str, cond: bool, detail=None):
    REPORT['checks'].append({'name':name,'passed':bool(cond),'detail':detail})
    if not cond: raise AssertionError(name+' '+str(detail))

def enum_words(alphabet, n):return itertools.product(alphabet,repeat=n)

def oracle_dyck(w,pairs):
    st=[]
    for a in w:
        if a in pairs: st.append(a)
        elif a in pairs.values():
            if not st or pairs[st.pop()]!=a: return False
        else:return False
    return not st

def oracle_anbn(w,include_epsilon:bool):
    if len(w)%2:return False
    size=len(w)//2
    return (size>0 or include_epsilon) and w==('a',)*size+('b',)*size

def oracle_pal(w,allow_epsilon:bool):
    return (allow_epsilon or len(w)>0) and len(w)%2==0 and w==w[::-1]

def oracle_marked(w):
    if w.count('#')!=1:return False
    i=w.index('#')
    return i>0 and w[:i]==w[i+1:][::-1]

def batch(name, g, alpha, max_len, oracle):
    TP=TN=FP=FN=0
    for length in range(max_len+1):
        for w in enum_words(alpha,length):
            result=parse(g,w,limit=32)
            if result.status=='UNKNOWN_BOUND':raise AssertionError('unknown '+name+str(w))
            observed=bool(result.trees); expected=oracle(w)
            TP+=observed and expected
            TN+=(not observed) and (not expected)
            FP+=observed and (not expected)
            FN+=(not observed) and expected
            if result.trees:
                check('witness_verified_'+name+'_'+''.join(w), all(verify_parse(g,w,tr) for tr in result.trees))
    check('oracle_match_'+name, FP==0 and FN==0,{'TP':TP,'TN':TN,'FP':FP,'FN':FN,'max_len':max_len})
    return {'suite':name,'TP':TP,'TN':TN,'FP':FP,'FN':FN}


def main():
    suites=[]
    suites.append(batch('anbn_nonempty',GRAMMARS['anbn_nonempty'],('a','b'),8,lambda w:oracle_anbn(w,False)))
    suites.append(batch('anbn_nullable',GRAMMARS['anbn_nullable'],('a','b'),8,lambda w:oracle_anbn(w,True)))
    suites.append(batch('dyck1',GRAMMARS['dyck1'],('a','b'),8,lambda w:oracle_dyck(w,{'a':'b'})))
    suites.append(batch('dyck2',GRAMMARS['dyck2'],('S','P','A','B'),6,lambda w:oracle_dyck(w,{'S':'P','A':'B'})))
    suites.append(batch('dyck2_untyped',GRAMMARS['dyck2_untyped'],('S','P','A','B'),4,
                        lambda w:oracle_dyck(w,{'S':'P','A':'B'}) if False else weak_oracle(w)))
    suites.append(batch('even_palindrome',GRAMMARS['even_palindrome'],('a','b'),8,lambda w:oracle_pal(w,False)))
    suites.append(batch('even_palindrome_nullable',GRAMMARS['even_palindrome_nullable'],('a','b'),8,lambda w:oracle_pal(w,True)))
    suites.append(batch('marked_reverse',GRAMMARS['marked_reverse'],('a','b','#'),6,oracle_marked))
    check('epsilon_separation',
          not parse(GRAMMARS['anbn_nonempty'],()).trees and bool(parse(GRAMMARS['anbn_nullable'],()).trees))

    # Representation covariance under simultaneous renaming of tokens and grammar roles.
    relabel={'S':'X','P':'Y','A':'U','B':'V'}
    D2_renamed=rename_terminals(GRAMMARS['dyck2'],relabel)
    for length in range(0,7):
        for word in enum_words(('S','P','A','B'),length):
            orig=parse(GRAMMARS['dyck2'],word)
            image=parse(D2_renamed,tuple(relabel[z] for z in word))
            if bool(orig.trees)!=bool(image.trees):
                raise AssertionError('role renaming invariance '+str(word))
    check('simultaneous_role_terminal_rename',True,{'domain_max_len':6,'tokens':4,
          'count':sum(4**i for i in range(7))})

    # Two alternative parse trees of the same surface string must be retained.
    amb=parse(GRAMMARS['ambiguous_concat'],('a','a','a'),limit=20)
    uniq={json.dumps(tree,sort_keys=True) for tree in amb.trees}
    check('ambiguity_keeps_distinct_proofs',len(uniq)>=2,
          {'n_derivations':len(uniq),'example':'aaa'})
    tr=copy.deepcopy(amb.trees[0])
    tr['rule']=999
    check('forged_rule_rejected',not verify_parse(GRAMMARS['ambiguous_concat'],('a','a','a'),tr))
    tr=copy.deepcopy(amb.trees[0]);tr['span'][1]=4
    check('forged_span_rejected',not verify_parse(GRAMMARS['ambiguous_concat'],('a','a','a'),tr))
    tr=copy.deepcopy(amb.trees[0]);
    def mutate_terminal(node):
        for c in node['children']:
            if 'terminal' in c:
                c['terminal']='fake';return True
            if mutate_terminal(c):return True
        return False
    assert mutate_terminal(tr)
    check('forged_terminal_rejected',not verify_parse(GRAMMARS['ambiguous_concat'],('a','a','a'),tr))

    proof_word=('S','A','B','P')
    proof_env=source_bound_envelope(GRAMMARS['dyck2'],' '.join(proof_word),
                                    parse(GRAMMARS['dyck2'],proof_word).trees[0])
    check('source_bound_proof_verified',verify_source_bound_envelope(GRAMMARS['dyck2'],proof_env))
    bad=copy.deepcopy(proof_env);bad['source_text']='S A P B'
    check('source_sha_forgery_rejected',not verify_source_bound_envelope(GRAMMARS['dyck2'],bad))
    bad=copy.deepcopy(proof_env);bad['token_byte_spans'][1][0]+=1
    check('source_span_forgery_rejected',not verify_source_bound_envelope(GRAMMARS['dyck2'],bad))
    bad=copy.deepcopy(proof_env);bad['grammar_sha256']='0'*64
    check('grammar_sha_forgery_rejected',not verify_source_bound_envelope(GRAMMARS['dyck2'],bad))
    bad=copy.deepcopy(proof_env);bad['tree']['children'][0]['terminal']='A'
    check('terminal_role_forgery_rejected',not verify_source_bound_envelope(GRAMMARS['dyck2'],bad))

    # DFA checker and parity over all strings up to length 9.
    for length in range(10):
        for w in enum_words(('a','b'),length):
            decision,trace=PARITY_DFA.run(w)
            expect=sum(t=='a' for t in w)%2==0
            if not (decision==expect and PARITY_DFA.verify(w,decision,trace)):
                raise AssertionError('DFA '+str(w))
    check('DFA_parity_up_to_9',True,{'exhaustive_total':sum(2**i for i in range(10))})
    decision,trace=PARITY_DFA.run(('a','b','a'))
    corrupted=copy.deepcopy(trace);corrupted[0]['next']='even'
    check('DFA_fake_trace_rejected',not PARITY_DFA.verify(('a','b','a'),decision,corrupted))

    # Structural typing is separate from truth and from source-language interpretation.
    for name, phi in INTERPRETATIONS.items():
        check('FOL_well_typed_'+name, typecheck_fol(phi,SIGNATURE,{'researcher','hypothesis'}))
    swapped=Q('forall','h','hypothesis',Q('exists','r','researcher',A('h','r')))
    check('FOL_swapped_sorts_rejected',not typecheck_fol(swapped,SIGNATURE,{'researcher','hypothesis'}))
    check('FOL_free_vars_rejected',not typecheck_fol(A('r','h'),SIGNATURE,{'researcher','hypothesis'}))

    # Finite countermodels demonstrate genuine differences in quantifier scope.
    m_different=model(('r1','r2'),('h1','h2'),(('r1','h1'),('r2','h2')))
    m_common_not_exact=model(('r1','r2'),('h1','h2'),(('r1','h1'),('r1','h2'),('r2','h1')))
    v1=truth_vector(m_different)
    v2=truth_vector(m_common_not_exact)
    check('interpretations_different_hypotheses',v1=={'I1_each_at_least_one':True,'I2_one_common':False,'I3_each_exactly_one':True},v1)
    check('interpretations_exactly_one',v2=={'I1_each_at_least_one':True,'I2_one_common':True,'I3_each_exactly_one':False},v2)
    REPORT['models']=[{'name':'different_hypotheses','model':m_different,'truth':v1},
                      {'name':'common_but_not_exactly_one','model':m_common_not_exact,'truth':v2}]
    for a,b in [('I1_each_at_least_one','I2_one_common'),('I1_each_at_least_one','I3_each_exactly_one'),('I2_one_common','I3_each_exactly_one')]:
        cm=distinguishing_countermodel(INTERPRETATIONS[a],INTERPRETATIONS[b])
        check('countermodel_'+a+'_'+b,cm is not None,cm)
        REPORT['distinguishers'].append({'pair':[a,b],'countermodel':cm})

    for a,b,alpha,expected in [
       ('anbn_nonempty','anbn_nullable',('a','b'),()),
       ('anbn_nullable','dyck1',('a','b'),('a','b','a','b')),
       ('dyck2','dyck2_untyped',('S','P','A','B'),('S','B')),
       ('even_palindrome','even_palindrome_nullable',('a','b'),()),
    ]:
        x=shortest_distinguishing_word(GRAMMARS[a],GRAMMARS[b],alpha,6)
        check('active_query_'+a+'_'+b,x['status']=='DISTINGUISHING_WORD' and tuple(x['word'])==expected,x)
        REPORT['distinguishers'].append({'pair':[a,b],'active_query':x})

    # Atomic negative for provenance: trust comes from SHA and source spans, not
    # from plausible-looking source text or an unverified AST.
    import hashlib
    source='Каждый исследователь проверил одну гипотезу.'
    metadata={'text':source,'sha256':hashlib.sha256(source.encode('utf-8')).hexdigest(),
              'spans':[{'text':'Каждый','start':0,'end':len('Каждый')}]}
    check('correct_source_sha',metadata['sha256']==hashlib.sha256(metadata['text'].encode()).hexdigest())
    check('correct_source_span',all(metadata['text'][s['start']:s['end']]==s['text'] for s in metadata['spans']))
    bad=copy.deepcopy(metadata);bad['spans'][0]['end']+=1
    check('forged_source_span_rejected',not all(bad['text'][s['start']:s['end']]==s['text'] for s in bad['spans']))
    REPORT['summary']={'passed':sum(c['passed'] for c in REPORT['checks']),
                       'failed':sum(not c['passed'] for c in REPORT['checks']),
                       'suites':suites,'MCP_modified':False,
                       'NL_to_FOL_discovery_implemented':False,
                       'proof_claim':'finite checked examples only'}
    out=Path(__file__).resolve().parent.parent/'results'/'reference_acceptance.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(REPORT,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf8')
    print(json.dumps(REPORT['summary'],ensure_ascii=False,indent=2))


def weak_oracle(w):
    st=[]
    for x in w:
        if x in ('S','A'):st.append(x)
        elif x in ('P','B'):
            if not st:return False
            st.pop()
        else:return False
    return not st


if __name__=='__main__':main()
