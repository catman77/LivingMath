"""Native007 source definitions and leaf-level accounting, including adapter work."""
from collections import Counter
import hashlib
import inspect
import json
from types import CodeType
import time

from live_transfer006_primitives import State,Exhausted


class Ledger:
    def __init__(self,limit=2048,seconds=2):
        self.limit=limit;self.seconds=seconds;self.start=time.perf_counter();self.stage='input'
        self.native=Counter({'extend':0,'observe':0,'admissible':0});self.stages={};self.work=Counter();self.trace=[]

    def charge(self,name,n=1):self.work[self.stage+':'+name]+=n

    def call(self,name,state,argument):
        if sum(self.native.values())>=self.limit or time.perf_counter()-self.start>self.seconds:raise Exhausted('GLOBAL_NATIVE_OR_TIME_CAP')
        self.native[name]+=1
        self.stages.setdefault(self.stage,Counter({'extend':0,'observe':0,'admissible':0}))[name]+=1
        self.trace.append({'operation':name,'stage':self.stage,'source':{'value':state.value,'history':list(state.history)},'argument':argument})
        return len(self.trace)-1

    def answer(self,index,value):
        self.trace[index]['result']={'value':value.value,'history':list(value.history)} if isinstance(value,State) else value
        return value

    def summary(self):
        return {'native':dict(self.native),'total_native_calls':sum(self.native.values()),
                'native_by_stage':{k:dict(v) for k,v in self.stages.items()},'structural_work':dict(self.work),
                'trace_events':len(self.trace),'scalar_work_units_are_not_native_calls':True}


def native_admissible(s,a,p,ledger):
    call=ledger.call('admissible',s,a);role=p['actions'].index(a)
    return ledger.answer(call,not (p['family']=='boundary' and s.history and p['actions'].index(s.history[0])==1 and role==len(p['actions'])-1))


def native_extend(s,a,p,ledger):
    call=ledger.call('extend',s,a);role=p['actions'].index(a);v=s.value;family=p['family']
    if family=='affine':
        k=p['coefficients'][role];x,y=v;v=((x+k*y)%p['modulus'],(y+k)%p['modulus'])
    elif family=='permutation':v=tuple(v[i] for i in p['permutations'][role])
    elif family=='erasure':v=v[p['cuts'][role]:]
    elif family not in {'opaque','boundary'}:raise ValueError('Unknown native source')
    return ledger.answer(call,State(v,s.history+(a,)))


def native_observe(s,observer,p,ledger):
    call=ledger.call('observe',s,observer)
    if p['family']=='opaque':
        n=len(p['actions']);tail=[p['actions'].index(a) for a in s.history[-2:]]
        return ledger.answer(call,p['actions'].index(s.history[0])%2 if len(s.history)>=3 and sum(tail)==2*(n-1) else 0)
    if p['family']=='boundary':return ledger.answer(call,0)
    value=s.value[0] if s.value else 'EMPTY'
    return ledger.answer(call,value if observer['mod'] is None else value%observer['mod'])


def stable_code_value(value):
    # marshal flags depend on reference counts/object sharing, not semantics.
    if isinstance(value,CodeType):
        return {'bytecode':value.co_code.hex(),'exception_table':value.co_exceptiontable.hex(),
                'names':value.co_names,'variables':value.co_varnames,'freevars':value.co_freevars,'cellvars':value.co_cellvars,
                'args':[value.co_argcount,value.co_posonlyargcount,value.co_kwonlyargcount,value.co_flags],
                'constants':[stable_code_value(x) for x in value.co_consts]}
    if isinstance(value,tuple):return {'tuple':[stable_code_value(x) for x in value]}
    if isinstance(value,frozenset):
        items=[stable_code_value(x) for x in value]
        return {'frozenset':sorted(items,key=lambda x:json.dumps(x,sort_keys=True))}
    if isinstance(value,bytes):return {'bytes':value.hex()}
    return value


def native_fingerprint():
    descriptions=[{'source':inspect.getsource(f),'code':stable_code_value(f.__code__)} for f in
                  (native_admissible,native_extend,native_observe)]
    return hashlib.sha256(json.dumps(descriptions,sort_keys=True,separators=(',',':')).encode()).hexdigest()


AUDITED_IMPLEMENTATION=native_fingerprint()


class Port:
    def __init__(self,p,ledger):self.parameters=p;self.ledger=ledger
    @property
    def counts(self):return dict(self.ledger.native)
    @property
    def trace(self):return self.ledger.trace
    def admissible(self,s,a):
        self.ledger.charge('adapter_admissible');return native_admissible(s,a,self.parameters,self.ledger)
    def extend(self,s,a):
        self.ledger.charge('adapter_extend');return native_extend(s,a,self.parameters,self.ledger)
    def observe(self,s,o):
        self.ledger.charge('adapter_observe')
        value=None
        for _ in range(self.parameters.get('adapter_repeat',1)):value=native_observe(s,o,self.parameters,self.ledger)
        return value
    def load(self,word):
        self.ledger.charge('source_loads');initial=self.parameters['initial']
        s=State(tuple(initial),())
        for a in word:
            if not self.admissible(s,a):raise ValueError('Invalid initial history')
            s=self.extend(s,a)
        return s
