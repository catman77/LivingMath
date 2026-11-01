"""Native source operations, not world-specific witness/selection algorithms."""
from dataclasses import dataclass
import hashlib
import inspect
import time

from normalizer import digest


@dataclass(frozen=True)
class State:
    value: object
    history: tuple


def credit(history: tuple, p: dict) -> int:
    balance=0
    for action in history:
        role=p['actions'].index(action)
        if role==0:balance+=1
        elif role==1:balance-=1
        elif role==2:balance=0
    return balance


def native_admissible(s: State, a: str, p: dict) -> bool:
    role=p['actions'].index(a)
    if p['family']=='rewrite':
        return (role!=0 or bool(s.value)) and (role!=1 or len(s.value)<p['max_word'])
    if p['family']=='history':
        balance=credit(s.history,p)
        return (role!=0 or balance<p['capacity']) and (role!=1 or balance>0)
    return True


def native_extend(s: State, a: str, p: dict) -> State:
    role=p['actions'].index(a);v=s.value
    if p['family']=='register':
        x,y=v;v=((x+role*y)%p['modulus'],(y+role)%p['modulus'])
    elif p['family']=='rewrite':
        if role==0:v=v[1:]
        elif role==1:v=v+(p['letters'][0],)
        else:
            pair=tuple(p['letters']);at=next((i for i in range(len(v)-1) if v[i:i+2]==pair),None)
            if at is not None:v=v[:at+1]+v[at+2:]
    elif p['family']=='permutation':
        transform=p['permutations'][role];v=tuple(transform[i] for i in v)
    elif p['family']=='history':
        v=0 if role==2 else credit(s.history,p) if role==3 else (v+1)%p['display_mod']
    else:raise ValueError('Unsupported native source family')
    return State(v,s.history+(a,))


def native_observe(s: State, observer: dict, p: dict):
    if p['family']=='rewrite':return s.value[0] if s.value else 'EMPTY'
    value=s.value[0] if p['family'] in {'register','permutation'} else s.value
    return value if observer['mod'] is None else value % observer['mod']


def primitive_fingerprint() -> str:
    return hashlib.sha256(''.join(inspect.getsource(f) for f in
        (credit,native_admissible,native_extend,native_observe)).encode()).hexdigest()


class Exhausted(RuntimeError):
    pass


class Port:
    """Count and bound only primary operation access, retaining immutable histories."""
    def __init__(self, parameters: dict, max_calls: int = 2048, seconds: float = 2):
        self.parameters=parameters;self.limit=max_calls;self.seconds=seconds;self.start=time.perf_counter()
        self.counts={'extend':0,'observe':0,'admissible':0};self.trace=[]

    def call(self, name, source, argument, function):
        if sum(self.counts.values())>=self.limit or time.perf_counter()-self.start>self.seconds:
            raise Exhausted('PRIMARY_OPERATION_OR_TIME_BOUND')
        self.counts[name]+=1
        result=function()
        encoded={'value':result.value,'history':list(result.history)} if isinstance(result,State) else result
        self.trace.append({'operation':name,'source':{'value':source.value,'history':list(source.history)},
                           'argument':argument,'result':encoded})
        return result

    def extend(self, source: State, action: str) -> State:
        return self.call('extend',source,action,lambda:native_extend(source,action,self.parameters))

    def observe(self, source: State, observer: dict):
        return self.call('observe',source,observer,lambda:native_observe(source,observer,self.parameters))

    def admissible(self, source: State, action: str) -> bool:
        return self.call('admissible',source,action,lambda:native_admissible(source,action,self.parameters))

    def load(self, history: list[str]) -> State:
        value=self.parameters['initial']
        if isinstance(value,list):value=tuple(value)
        state=State(value,())
        for action in history:
            if not self.admissible(state,action):raise ValueError('Invalid source history')
            state=self.extend(state,action)
        return state
