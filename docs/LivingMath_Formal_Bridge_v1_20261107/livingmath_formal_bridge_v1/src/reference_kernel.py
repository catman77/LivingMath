#!/usr/bin/env python3
"""Small, independently executable reference for formal-language/semantic acceptance.

NOT the LivingMath server, NOT a production grammar inducer, NOT an NL parser.
No third-party dependencies. Finite proof-checking and finite-model semantics only.
"""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
from itertools import product
from typing import Any, Mapping
import json
import hashlib
import re


@dataclass(frozen=True)
class Grammar:
    name: str
    start: str
    rules: dict[str, tuple[tuple[str, ...], ...]]
    # Each rhs symbol is 't:<token>' or 'n:<nonterminal>'. Empty tuple is EPS.

    def __post_init__(self):
        assert self.start in self.rules
        for nt, productions in self.rules.items():
            assert productions
            for rhs in productions:
                for symbol in rhs:
                    assert symbol.startswith(('n:', 't:'))
                    if symbol.startswith('n:'):
                        assert symbol[2:] in self.rules
                    else:
                        assert len(symbol[2:]) > 0


def t(x: str) -> str: return 't:' + x

def n(x: str) -> str: return 'n:' + x


GRAMMARS = {
    'anbn_nonempty': Grammar('anbn_nonempty', 'S', {'S': ((t('a'), t('b')), (t('a'), n('S'), t('b')))}),
    'anbn_nullable': Grammar('anbn_nullable', 'S', {'S': ((), (t('a'), n('S'), t('b')))}),
    'dyck1': Grammar('dyck1', 'D', {'D': ((), (t('a'), n('D'), t('b'), n('D')))}),
    'dyck2': Grammar('dyck2', 'D', {'D': ((), (t('S'), n('D'), t('P'), n('D')), (t('A'), n('D'), t('B'), n('D')))}),
    'dyck2_untyped': Grammar('dyck2_untyped', 'D', {'D': ((), *((t(o), n('D'), t(c), n('D')) for o in 'SA' for c in 'PB'))}),
    'even_palindrome': Grammar('even_palindrome', 'P', {'P': ((t('a'),t('a')), (t('b'),t('b')), (t('a'), n('P'), t('a')), (t('b'), n('P'), t('b')))}),
    'even_palindrome_nullable': Grammar('even_palindrome_nullable','P', {'P': ((), (t('a'),n('P'),t('a')), (t('b'),n('P'),t('b')))}),
    'marked_reverse': Grammar('marked_reverse', 'S', {'S': ((t('a'),t('#'),t('a')), (t('b'),t('#'),t('b')), (t('a'), n('S'), t('a')), (t('b'), n('S'), t('b')))}),
    'ambiguous_concat': Grammar('ambiguous_concat', 'S', {'S': ((n('S'), n('S')), (t('a'),))}),
}


@dataclass
class ParseResult:
    status: str
    trees: list[dict[str, Any]]
    cycle_seen: bool
    truncated: bool


def parse(grammar: Grammar, tokens: tuple[str, ...] | list[str], limit: int=32,
          budget: int=30000) -> ParseResult:
    """Bounded explicit proof search; no evidence of absence after cycle/budget.

    The nonterminal-span recursion is well founded for intended benchmark grammars.
    Recursion via same span conservatively sets cycle_seen. The independent proof
    verifier below does NOT rely on this search procedure.
    """
    toks = tuple(tokens)
    cache: dict[tuple[str, int, int], list[dict[str, Any]]] = {}
    active: set[tuple[str, int, int]] = set()
    cycle = False
    truncated = False
    calls = 0

    def ntparse(nt: str, i: int, j: int) -> list[dict[str, Any]]:
        nonlocal cycle, truncated, calls
        calls += 1
        if calls > budget:
            truncated = True
            return []
        key = nt, i, j
        if key in cache: return cache[key]
        if key in active:
            cycle = True
            return []
        active.add(key)
        out: list[dict[str, Any]] = []
        for p_idx, rhs in enumerate(grammar.rules[nt]):
            def expand(k: int, pos: int, children: tuple[dict[str, Any], ...]):
                nonlocal truncated
                if len(out) >= limit or truncated:
                    if len(out) >= limit: truncated = True
                    return
                if k == len(rhs):
                    if pos == j:
                        out.append({'nt': nt, 'rule': p_idx, 'span': [i, j],
                                    'children': list(children)})
                    return
                symbol = rhs[k]
                if symbol.startswith('t:'):
                    atom = symbol[2:]
                    if pos < j and toks[pos] == atom:
                        expand(k+1, pos+1, children+({'terminal': atom,'span': [pos,pos+1]},))
                else:
                    child_nt = symbol[2:]
                    for end in range(pos, j+1):
                        for child in ntparse(child_nt, pos, end):
                            expand(k+1, end, children+(child,))
            expand(0, i, ())
        active.remove(key)
        cache[key] = out
        return out

    trees = ntparse(grammar.start, 0, len(toks))
    if trees: status = 'ACCEPT_WITNESSED'
    elif cycle or truncated: status = 'UNKNOWN_BOUND'
    else: status = 'REJECTED_WITHIN_COMPLETE_LOCAL_SEARCH'
    return ParseResult(status, trees, cycle, truncated)


def verify_parse(grammar: Grammar, tokens: tuple[str, ...] | list[str],
                 tree: Mapping[str, Any]) -> bool:
    """Independent checker; rejects invalid rules, spans, children and tokens.
    This is an exact finite derivation proof, not a universal language theorem.
    """
    toks = tuple(tokens)
    try:
        def check(node: Mapping[str,Any], expected_nt: str, i: int, j: int) -> None:
            if node['nt'] != expected_nt or node['span'] != [i, j]: raise ValueError('node mismatch')
            p_idx = node['rule']
            if not isinstance(p_idx,int) or isinstance(p_idx,bool): raise ValueError('rule type')
            rhs = grammar.rules[expected_nt][p_idx]
            children = node['children']
            if len(children) != len(rhs): raise ValueError('arity')
            cur = i
            for sym, child in zip(rhs, children):
                span = child['span']
                if span[0] != cur or not isinstance(span[1], int) or span[1] > j:
                    raise ValueError('span mismatch')
                if sym.startswith('t:'):
                    if set(child) != {'terminal','span'}: raise ValueError('wrong child kind')
                    if span[1] != cur+1 or cur >= len(toks) or child['terminal'] != sym[2:] or toks[cur] != sym[2:]:
                        raise ValueError('terminal mismatch')
                else:
                    if set(child) != {'nt','rule','span','children'}: raise ValueError('wrong child kind')
                    check(child, sym[2:], cur, span[1])
                cur = span[1]
            if cur != j: raise ValueError('trailing span')
        if set(tree) != {'nt','rule','span','children'}: return False
        check(tree, grammar.start, 0, len(toks))
        return True
    except (KeyError, TypeError, ValueError, IndexError, RecursionError):
        return False





def rename_terminals(grammar: Grammar, rename: Mapping[str,str]) -> Grammar:
    """Alpha-rename terminals AND their role occurrences in grammar productions.
    This is not a theorem that arbitrary source-only renaming preserves a model.
    """
    image=set(rename.values())
    if len(image)!=len(rename):raise ValueError('renaming not injective')
    r={}
    for nt,prods in grammar.rules.items():
        r[nt]=tuple(tuple(t(rename.get(sym[2:],sym[2:])) if sym.startswith('t:') else sym
                        for sym in rhs) for rhs in prods)
    return Grammar(grammar.name+'_renamed',grammar.start,r)


def grammar_digest(grammar: Grammar) -> str:
    payload={'start':grammar.start,'rules':{k:[list(v) for v in rhs] for k,rhs in grammar.rules.items()}}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def source_bound_envelope(grammar: Grammar, text: str, tree: dict) -> dict:
    """Fixture construction. The verification routine does NOT trust this helper."""
    tokens=[]; spans=[]
    for hit in re.finditer(r'\S+',text):
        before=text[:hit.start()].encode('utf8')
        end=text[:hit.end()].encode('utf8')
        tokens.append(hit.group())
        spans.append([len(before),len(end)])
    return {'source_text':text, 'source_sha256':hashlib.sha256(text.encode()).hexdigest(),
            'tokens':tokens,'token_byte_spans':spans,'grammar_sha256':grammar_digest(grammar),
            'tree':tree}


def verify_source_bound_envelope(grammar: Grammar, env: dict) -> bool:
    """Independent source/grammar/parse wrapper checking cryptographic lineage.
    This is an exact finite witness check; no claim about true text semantics.
    """
    try:
        text=env['source_text']; raw=text.encode('utf8')
        if hashlib.sha256(raw).hexdigest()!=env['source_sha256']:return False
        if grammar_digest(grammar)!=env['grammar_sha256']:return False
        tokens=[]; spans=[]
        for hit in re.finditer(r'\S+',text):
            tokens.append(hit.group())
            spans.append([len(text[:hit.start()].encode('utf8')),len(text[:hit.end()].encode('utf8'))])
        if env['tokens']!=tokens or env['token_byte_spans']!=spans:return False
        for tok,span in zip(tokens,spans):
            if raw[span[0]:span[1]].decode('utf8')!=tok:return False
        return verify_parse(grammar,tokens,env['tree'])
    except (TypeError,ValueError,KeyError,IndexError,UnicodeError,AttributeError):
        return False



@dataclass(frozen=True)
class DFA:
    start: str
    accepting: frozenset[str]
    transitions: Mapping[tuple[str,str], str]

    def run(self, word: tuple[str,...] | list[str]) -> tuple[bool,list[dict[str,str]]]:
        q = self.start; trace=[]
        for atom in word:
            next_q = self.transitions[(q,atom)]
            trace.append({'state':q,'token':atom,'next':next_q})
            q = next_q
        return q in self.accepting, trace

    def verify(self, word: tuple[str,...], accepted: bool, trace: list[dict[str,str]]) -> bool:
        try:
            q=self.start
            if len(word)!=len(trace):return False
            for atom, step in zip(word, trace):
                if step != {'state':q,'token':atom,'next':self.transitions[(q,atom)]}:
                    return False
                q=step['next']
            return (q in self.accepting)==accepted
        except (KeyError,TypeError): return False


PARITY_DFA = DFA('even', frozenset({'even'}), {
    ('even','a'):'odd', ('even','b'):'even',
    ('odd','a'):'even', ('odd','b'):'odd',
})


def model(researchers: tuple[str,...], hypotheses: tuple[str,...],
          checked: tuple[tuple[str,str], ...]) -> dict[str,Any]:
    assert researchers and hypotheses
    return {'domains': {'researcher':list(researchers), 'hypothesis':list(hypotheses)},
            'relations': {'Checked':[list(p) for p in checked]}}

# Typed FOL AST. The three candidates are hypothetical readings of the same
# Russian sentence; they have NOT been induced by the existing MCP runtime.

def V(var:str) -> dict: return {'var':var}

def A(a:str,b:str) -> dict: return {'pred':'Checked','args':[V(a),V(b)]}

def Q(quant:str,var:str,sort:str,body:dict) -> dict:
    return {'quant':quant,'var':var,'sort':sort,'body':body}


def atom_eq(a:str,b:str) -> dict: return {'eq':[V(a),V(b)]}


def AND(*v:dict) -> dict: return {'and':list(v)}


def OR(*v:dict) -> dict: return {'or':list(v)}


def NEG(v:dict) -> dict: return {'not':v}


INTERPRETATIONS = {
 'I1_each_at_least_one': Q('forall','r','researcher', Q('exists','h','hypothesis',A('r','h'))),
 'I2_one_common': Q('exists','h','hypothesis', Q('forall','r','researcher',A('r','h'))),
 'I3_each_exactly_one': Q('forall','r','researcher',Q('exists','h','hypothesis',
     AND(A('r','h'),Q('forall','h2','hypothesis',OR(NEG(A('r','h2')),atom_eq('h2','h')))))),
}



SIGNATURE = {'Checked':('researcher','hypothesis')}


def typecheck_fol(phi: dict, signature: dict[str, tuple[str,...]],
                  sorts: set[str], env: dict[str,str] | None=None) -> bool:
    """Separate structural FOL type check; no interpreting of natural-language meaning.

    Checks every predicate argument is bound and has its declared sort; equality
    compares terms of the same sort; quantification binds a known sort.
    """
    env = {} if env is None else dict(env)
    if not isinstance(phi, dict):return False
    if 'quant' in phi:
        var=phi.get('var'); sort=phi.get('sort'); quant=phi.get('quant')
        if not isinstance(var,str) or sort not in sorts or quant not in ('forall','exists'):return False
        return typecheck_fol(phi.get('body'),signature,sorts,{**env,var:sort})
    if 'pred' in phi:
        pred=phi.get('pred'); args=phi.get('args',[])
        if pred not in signature or len(args)!=len(signature[pred]):return False
        return all(isinstance(term,dict) and set(term)=={'var'} and
                   env.get(term['var'])==sort for term,sort in zip(args,signature[pred]))
    if 'eq' in phi:
        terms=phi['eq']
        return isinstance(terms,list) and len(terms)==2 and all(
            isinstance(x,dict) and set(x)=={'var'} and x['var'] in env for x in terms
        ) and env[terms[0]['var']]==env[terms[1]['var']]
    if 'not' in phi: return typecheck_fol(phi['not'],signature,sorts,env)
    if 'and' in phi:return isinstance(phi['and'],list) and all(typecheck_fol(x,signature,sorts,env) for x in phi['and'])
    if 'or' in phi:return isinstance(phi['or'],list) and all(typecheck_fol(x,signature,sorts,env) for x in phi['or'])
    return False


def eval_fol(phi: dict, M: dict, env: dict[str,str] | None=None) -> bool:
    """Exact evaluation for finite, explicitly typed, nonempty first-order models.
    Absence from relation is false under the closed-world finite-model convention.
    """
    e = {} if env is None else dict(env)
    if 'quant' in phi:
        d=M['domains'][phi['sort']]
        if not d: raise ValueError('empty sort not admitted by acceptance')
        evaluations=[eval_fol(phi['body'],M,{**e,phi['var']:x}) for x in d]
        if phi['quant']=='forall': return all(evaluations)
        if phi['quant']=='exists': return any(evaluations)
        raise ValueError('unknown quantifier')
    if 'pred' in phi:
        vals=tuple(e[x['var']] for x in phi['args'])
        return vals in {tuple(row) for row in M['relations'][phi['pred']]}
    if 'eq' in phi: return e[phi['eq'][0]['var']] == e[phi['eq'][1]['var']]
    if 'and' in phi:return all(eval_fol(x,M,e) for x in phi['and'])
    if 'or' in phi:return any(eval_fol(x,M,e) for x in phi['or'])
    if 'not' in phi:return not eval_fol(phi['not'],M,e)
    raise ValueError('unknown AST node')


def truth_vector(M:dict) -> dict[str,bool]:
    return {k:eval_fol(v,M) for k,v in INTERPRETATIONS.items()}


def distinguishing_countermodel(left:dict, right:dict, nr:int=2, nh:int=2,
                                 max_relations:int=1024) -> dict[str,Any] | None:
    """Find countermodel in FINITE, explicitly bounded domain. None means unknown,
    NOT 'formulas equivalent'; unbounded FOL equivalence not decided here.
    """
    rs=tuple(f'r{i}' for i in range(nr))
    hs=tuple(f'h{i}' for i in range(nh))
    edges=list(product(rs,hs))
    examined=0
    for size in range(len(edges)+1):
        for bits in product((0,1), repeat=len(edges)):
            if sum(bits) != size:continue
            examined+=1
            if examined>max_relations:return None
            M=model(rs,hs,tuple(e for e,b in zip(edges,bits) if b))
            if eval_fol(left,M)!=eval_fol(right,M):
                return {'model':M,'left':eval_fol(left,M),'right':eval_fol(right,M),
                        'examined':examined,'proof_status':'FINITE_COUNTERMODEL'}
    return None


def shortest_distinguishing_word(g1:Grammar,g2:Grammar,
                                 alphabet:tuple[str,...],max_length:int=8):
    """Finite bounded equivalence witness; absence is UNKNOWN, not equivalent."""
    for l in range(max_length+1):
        for word in product(alphabet, repeat=l):
            a=parse(g1,word);b=parse(g2,word)
            if a.status=='UNKNOWN_BOUND' or b.status=='UNKNOWN_BOUND':continue
            if bool(a.trees)!=bool(b.trees):
                return {'word':list(word), 'left':bool(a.trees), 'right':bool(b.trees),
                        'bounded_to':max_length, 'status':'DISTINGUISHING_WORD'}
    return {'bounded_to':max_length,'status':'NO_DIFFERENCE_IN_BOUND_UNKNOWN_GLOBALLY'}


def json_repr(data:Any) -> str:
    return json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':'))
