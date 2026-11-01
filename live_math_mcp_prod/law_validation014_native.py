"""Frozen physical014 source algebras, without supplied learned transport maps."""
from dataclasses import dataclass
import hashlib
from pathlib import Path
from operational013_native import Ledger


def native_sha():return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


@dataclass(frozen=True)
class State:
    value:tuple
    history:tuple=()


class Port:
    def __init__(self,declaration,ledger=None):
        self.declaration=declaration;self.ledger=ledger or Ledger();self.trace=self.ledger.rows;self.counts={}
    def charge(self,op,**data):
        self.ledger.charge(op,**data);self.counts[op]=self.counts.get(op,0)+1
    def load(self,word):
        self.charge('load',word=word);state=State(tuple(self.declaration['initial']))
        for a in word:
            if not self.admissible(state,a):raise ValueError('INADMISSIBLE_SOURCE_HISTORY')
            state=self.extend(state,a)
        return state
    def admissible(self,state,a):
        self.charge('A',word=list(state.history),action=a)
        if a not in range(self.declaration['arity']):return False
        if self.declaration['algebra']=='stack':return len(state.value)<4 if a<2 else bool(state.value)
        return True
    def extend(self,state,a):
        self.charge('E',word=list(state.history),action=a)
        p=state.value;kind=self.declaration['algebra']
        if kind=='affine':
            x,y=p;out=(x+y,y+1) if a==0 else (x,y+x+1)
        elif kind=='permutation':
            period=self.declaration['clock_period']
            if a==1 and period and (len(state.history)+1)%period==0:out=(p[2],p[1],p[0],p[3])
            else:out=(p[0],p[2],p[1],p[3]) if a==0 else p[1:]+p[:1]
        elif kind=='stack':
            if (a<2 and len(p)>=4) or (a==2 and not p):raise ValueError('STACK_GUARD')
            out=p+(a,) if a<2 else p[:-1]
        elif kind=='latch':
            x,y=p;out=(y,y) if a==0 else (x,1-y)
        else:raise ValueError('SOURCE_ALGEBRA')
        return State(tuple(out),state.history+(a,))
    def inspect(self,state,opaque=False):
        self.charge('inspect',word=list(state.history),opaque=opaque)
        if opaque:return None
        return list(state.value[:1] if self.declaration['algebra']=='latch' else state.value)
    def guard_image(self,image,a):
        self.charge('G',action=a,image=image)
        return len(image)<=self.declaration['guard_width'] and self.admissible(State(tuple(image)),a)
    def within_guard(self,image):
        self.charge('G_terminal',image=image);return len(image)<=self.declaration['guard_width']
    def observe_image(self,image,observer):return self.observe(State(tuple(image)),observer)
    def observe(self,state,observer):
        self.charge('O',word=list(state.history))
        if observer!={'projection':'primary','mod':None}:raise ValueError('OBSERVER_ALIGNMENT_REQUIRED')
        return (state.value[-1] if state.value else 0) if self.declaration['algebra']=='stack' else state.value[0]//2
