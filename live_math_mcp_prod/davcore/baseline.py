"""DAV symbolic core v0.1: exact finite-domain model checking, no ML dependencies."""
from dataclasses import dataclass, asdict
from itertools import combinations, product
from typing import Protocol
import json

class Domain(Protocol):
    name: str
    def states(self): ...
    def operations(self): ...
    def apply(self, op, state): ...
    def observe(self, state): ...

@dataclass(frozen=True)
class Eq:
    left: str
    right: str

@dataclass(frozen=True)
class Implies:
    premise: Eq
    conclusion: Eq

@dataclass(frozen=True)
class Evidence:
    state: int
    premise: bool
    conclusion: bool
    results: dict

class Engine:
    def __init__(self, domain: Domain):
        self.domain=domain
        self._cache={}
    def _result(self, operation, state):
        key=(operation,state)
        if key not in self._cache:
            self._cache[key]=self.domain.apply(operation,state)
        return self._cache[key]
    def atom(self, eq: Eq, state):
        return self._result(eq.left,state)==self._result(eq.right,state)
    def evidence(self, law: Implies, state: int):
        ops={law.premise.left,law.premise.right,law.conclusion.left,law.conclusion.right}
        values={op:self._result(op,state) for op in sorted(ops)}
        return Evidence(state,self.atom(law.premise,state),self.atom(law.conclusion,state),values)
    def check(self, law: Implies, states=None, complete=False):
        if states is None:
            if not complete: raise ValueError('Explicit states or complete=True required')
            states=list(self.domain.states())
        else: states=list(states)
        failures=[]; support=0; counter_conclusion=0
        for x in states:
            e=self.evidence(law,x)
            support+=e.premise;counter_conclusion+=not e.conclusion
            if e.premise and not e.conclusion: failures.append(asdict(e))
        return {'status':('refuted' if failures else 'proved' if complete else 'consistent_with_observations'),
                'scope':'full_finite_domain' if complete else 'sample',
                'tested':len(states),'support':support,'nontrivial_conclusion_failures':counter_conclusion,
                'counterexample':failures[0] if failures else None}
    def atoms(self): return [Eq(a,b) for a,b in combinations(self.domain.operations(),2)]
    def laws(self):
        atoms=self.atoms()
        for p in atoms:
            for c in atoms:
                if p!=c: yield Implies(p,c)
    def signature(self, eq: Eq, states): return tuple(self.atom(eq,x) for x in states)
    def library(self, states=None, complete=False, min_support=1):
        if states is None:
            if not complete: raise ValueError('Explicit states or complete=True required')
            states=list(self.domain.states())
        else: states=list(states)
        atoms=self.atoms(); sigs={a:self.signature(a,states) for a in atoms}
        grouped={}
        for p,c in product(atoms,repeat=2):
            if p==c: continue
            sp,sc=sigs[p],sigs[c]
            if sum(sp)<min_support or all(sc) or any(x and not y for x,y in zip(sp,sc)): continue
            grouped.setdefault(sc,{}).setdefault(sp,Implies(p,c))
        representatives=[]
        for conclusion, by_premise in grouped.items():
            for prem,law in by_premise.items():
                if any(other!=prem and all((not x) or y for x,y in zip(prem,other)) for other in by_premise):
                    continue
                representatives.append(law)
        representatives.sort(key=lambda law:(law.conclusion.left,law.conclusion.right,law.premise.left,law.premise.right))
        return {'status':'proved' if complete else 'empirical_only',
                'laws':[asdict(law) for law in representatives],
                'count':len(representatives),
                'tested':len(states),
                'warning':'No claim of universal completeness beyond finite domain and this restricted formula grammar.'}

class CyclicCA:
    name='cyclic_ca_8'
    def __init__(self,n=8):self.n=n;self.name=f'cyclic_ca_{n}'
    def states(self):return range(1<<self.n)
    def operations(self):return tuple([f'T{i}' for i in range(self.n)]+[f'R{i}' for i in range(self.n)])
    def observe(self,x):return {'full_state':x,'bits':[(x>>i)&1 for i in range(self.n)]}
    def apply(self,op,x):
        k=int(op[1:])
        if op.startswith('R'):
            k%=self.n; mask=(1<<self.n)-1
            return ((x>>k)|(x<<(self.n-k)))&mask if k else x
        if not op.startswith('T'):raise ValueError(op)
        rule=sum(((x>>((k+j)%self.n))&1)<<j for j in range(8))
        result=0
        for j in range(self.n):
            triple=(((x>>((j-1)%self.n))&1)<<2)|(((x>>j)&1)<<1)|((x>>((j+1)%self.n))&1)
            result|=((rule>>triple)&1)<<j
        return result

class GraphBits:
    name='graph_bits'
    def __init__(self):
        self.maps={'P':(2,3,4,5,6,7,0,1),'Q':(4,5,6,7,0,1,2,3),
                   'S0':tuple(range(8)),'S1':tuple((i+1)%8 for i in range(8)),
                   'S2':tuple((i+2)%8 for i in range(8))}
    def states(self):return range(256)
    def operations(self):return tuple(self.maps)
    def observe(self,x):return {'full_state':x,'bits':[(x>>i)&1 for i in range(8)]}
    def apply(self,op,x):return sum(((x>>i)&1)<<j for i,j in enumerate(self.maps[op]))

class MaskedAdapter:
    """Explicit projection. Never claims original full-state equality."""
    def __init__(self,base,mask=0x0f):self.base=base;self.mask=mask;self.name=base.name+'_masked'
    def states(self):return self.base.states()
    def operations(self):return self.base.operations()
    def apply(self,op,x):return self.base.apply(op,x)&self.mask
    def observe(self,x):return {'observed':self.base.observe(x)['full_state']&self.mask,'projection':True}

def congruence_violations(base,mask=0x0f):
    states=list(base.states()); groups={}
    for x in states:groups.setdefault(x&mask,[]).append(x)
    findings=[]
    for op in base.operations():
        for xs in groups.values():
            outputs={base.apply(op,x)&mask for x in xs}
            if len(outputs)>1:
                findings.append({'operation':op,'states':xs[:2],'different_observed_outputs':sorted(outputs)[:2]})
                break
    return findings
