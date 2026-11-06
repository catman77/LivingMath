#!/usr/bin/env python3
"""Independent, bounded proof-of-concept interpreter for a *proposed* LivingMath AST promotion.
NOT a server patch, NOT an installed MCP implementation, NOT a general proof checker.
Only typed, audited existing operations. No eval, DSL, external I/O, mutable state.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import hashlib, json

SCHEMA = 'lm-typed-composition-certificate/1'
AST_PAL = {
    'composition': 'iterate_on_inner_fragment', 'trim_left': 1, 'trim_right': 1,
    'fragment_operations': ['SPLIT','SPLIT'],
    'relation': {'composition':'aligned_token_equality','base_max_tokens':1,
      'left_operations':['SPLIT'], 'right_operations':['REVERSE','SPLIT'],
      'offset':0,'expected_equal': True}}
AST_COPY = {
    'composition':'compare_fragments',
    'cut': {'operator':'SPLIT','position': 'MIDPOINT_EXACT_EVEN'},
    'comparison': 'literal_word_equality', 'expected_equal': True}

class NotProved(ValueError): pass
class Rejected(ValueError): pass


def canonical(o: Any) -> bytes:
    return json.dumps(o, sort_keys=True, ensure_ascii=False, separators=(',',':')).encode('utf-8')

def digest(o: Any) -> str:
    return hashlib.sha256(canonical(o)).hexdigest()

def token_source(tokens: tuple[str, ...]) -> dict:
    # Exact UTF-8 spans; no loss of original token identity
    text = ' '.join(tokens)
    source = text.encode('utf-8')
    start=0; spans=[]
    for token in tokens:
        tb=token.encode('utf-8')
        pos=source.find(tb, start)
        assert pos>=0
        spans.append([pos,pos+len(tb)])
        start=pos+len(tb)
    return {'text':text,'sha256':hashlib.sha256(source).hexdigest(), 'spans':spans}

def _require_ast(ast: dict):
    if ast==AST_PAL or ast==AST_COPY: return
    raise Rejected('AST_NOT_IN_TYPED_ALLOWLIST (reference supports two concrete AST shapes only)')

def evaluate(ast: dict, tokens: tuple[str, ...], max_tokens: int) -> tuple[bool, list[dict]]:
    """Return result and trace, with invariant-preserving primitive steps."""
    _require_ast(ast)
    if len(tokens)>max_tokens:
        raise NotProved('OUT_OF_DECLARED_SCOPE')
    tr=[]
    if ast==AST_PAL:
        current=tokens
        while len(current)>1:
            left=(current[0],)
            right=(current[-1],)
            reversed_word=tuple(reversed(current))
            # REVERSE then SPLIT at one token; left = original first
            tr.append({'op':'REVERSE','input':list(current),'output':list(reversed_word)})
            tr.append({'op':'SPLIT','input':list(current),'position':1,
                       'outputs':[list(left),list(current[1:])]})
            tr.append({'op':'SPLIT','input':list(reversed_word),'position':1,
                       'outputs':[list(right),list(reversed_word[1:])]})
            match=left==right
            tr.append({'op':'literal_word_equality','left':list(left),'right':list(right),
                       'equal':match})
            if not match:return False,tr
            # Second real SPLIT isolates the inner fragment from the trailing atom.
            # Together with the initial SPLIT this implements fragment_operations=[SPLIT,SPLIT].
            remainder=current[1:]
            new_current=remainder[:-1]
            tr.append({'op':'SPLIT','input':list(remainder),'position':len(remainder)-1,
                       'outputs':[list(new_current),list(remainder[-1:])]})
            current=new_current
        return True,tr
    # Midpoint cut and word equality, no scalar feature as classifier
    if len(tokens)%2:
        tr.append({'op':'CHECK_EVEN_LENGTH','result':False})
        return False,tr
    mid=len(tokens)//2
    left,right=tokens[:mid],tokens[mid:]
    tr.append({'op':'SPLIT','input':list(tokens),'position':mid,
               'outputs':[list(left),list(right)]})
    match=left==right
    tr.append({'op':'literal_word_equality','left':list(left),'right':list(right),'equal':match})
    return match,tr


def issue(ast:dict, words:list[tuple[str,...]], max_tokens:int)->dict:
    _require_ast(ast)
    witnesses=[]
    for tokens in words:
        value,trace=evaluate(ast,tokens,max_tokens)
        witnesses.append({'tokens':list(tokens),'source':token_source(tokens),'value':value,'trace':trace})
    return {'schema':SCHEMA,'ast':ast,'ast_digest':digest(ast),'max_tokens':max_tokens,
      'claim_status':'CHECKED_FINITE_INSTANCE','universal_invariant':False,
      'witnesses':witnesses,'witness_set_digest':digest(witnesses),
      'proof_boundary':'exact evaluator on listed witnesses; not grammar uniqueness, no general theorem'}


def verify(cert:dict, expected_words:list[tuple[str,...]]|None=None)->dict:
    """Independent re-execution of the typed AST; never trust recorded traces or values."""
    if cert.get('schema')!=SCHEMA:raise Rejected('WRONG_SCHEMA')
    ast=cert.get('ast')
    _require_ast(ast)
    if digest(ast)!=cert.get('ast_digest'):raise Rejected('AST_HASH_MISMATCH')
    limit=cert.get('max_tokens')
    if not isinstance(limit,int) or limit<1 or limit>512:raise Rejected('INVALID_BOUND')
    if cert.get('universal_invariant') is not False:raise Rejected('FALSE_UNIVERSAL_CLAIM')
    if cert.get('claim_status')!='CHECKED_FINITE_INSTANCE':raise Rejected('FALSE_CLAIM_STATUS')
    witnesses=cert.get('witnesses')
    if not isinstance(witnesses,list):raise Rejected('NO_WITNESSES')
    if expected_words is not None and [w.get('tokens') for w in witnesses]!=[list(t) for t in expected_words]:
        raise Rejected('WITNESS_MISSING_OR_EXTRA')
    if digest(witnesses)!=cert.get('witness_set_digest'):raise Rejected('WITNESS_DIGEST_MISMATCH')
    from independent_checker import execute_checked, TraceReject
    for i,w in enumerate(witnesses):
        tokens=w.get('tokens')
        if not isinstance(tokens,list) or any(not isinstance(z,str) or not z for z in tokens):
            raise Rejected(f'INVALID_TOKENS_{i}')
        tt=tuple(tokens)
        if w.get('source')!=token_source(tt):raise Rejected(f'UTF8_SOURCE_SPAN_OR_HASH_MISMATCH_{i}')
        try:v=execute_checked(ast,tt,w.get('trace'),limit)
        except TraceReject as err:
            if str(err)=='OUT_OF_SCOPE':raise Rejected(f'OUT_OF_SCOPE_{i}')
            raise Rejected(f'OPERATOR_REPLAY_MISMATCH_{i}: {err}')
        if w.get('value')!=v:raise Rejected(f'OPERATOR_REPLAY_MISMATCH_{i}')
    return {'status':'CHECKED_FINITE_INSTANCE','verified_witnesses':len(witnesses),
      'ast_digest':digest(ast), 'universal_invariant':False}


def pal_oracle(w):return w==w[::-1]
def copy_oracle(w):return len(w)%2==0 and w[:len(w)//2]==w[len(w)//2:]

def words_of_length(n:int)->list[tuple[str,...]]:
    return [tuple('S' if (mask >> (n-1-i))&1==0 else 'P' for i in range(n)) for mask in range(1<<n)]

if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument('--rule', choices=['PAL','COPY'],default='PAL')
    ap.add_argument('--length',type=int,default=6)
    ap.add_argument('--limit',type=int,default=8)
    a=ap.parse_args()
    ast=AST_PAL if a.rule=='PAL' else AST_COPY
    words=words_of_length(a.length)
    cert=issue(ast,words,a.limit)
    check=verify(cert,words)
    oracle=pal_oracle if a.rule=='PAL' else copy_oracle
    tp=tn=fp=fn=0
    for w,z in zip(words,cert['witnesses']):
        y=oracle(w);g=z['value']
        if y and g:tp+=1
        elif not y and not g:tn+=1
        elif not y and g:fp+=1
        else:fn+=1
    print(json.dumps({'rule':a.rule,'length':a.length,'num':len(words),'confusion':{'TP':tp,'TN':tn,'FP':fp,'FN':fn},'check':check},ensure_ascii=False))
