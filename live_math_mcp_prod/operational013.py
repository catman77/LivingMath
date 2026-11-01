"""One exact partial linear intertwiner. No native implementation or oracle imports.

Finite observations determine a linear map only on their input span. Linearity
on unobserved native states remains an empirical hypothesis, never a theorem.
"""
from fractions import Fraction

VERSION='013.0'


class TransportRefusal(ValueError):
    pass


class Embedding:
    width=4

    def __init__(self, origin):
        self.origin=self.raw(origin)

    def raw(self, image):
        if not isinstance(image,list) or len(image)>self.width or any(type(v) is not int for v in image):
            raise TransportRefusal('INCOMPLETE_INTEGER_SEQUENCE_IMAGE')
        return [1,len(image)]+[int(i<len(image)) for i in range(self.width)]+list(reversed(image))+[0]*(self.width-len(image))

    def encode(self, image):
        vector=self.raw(image)
        return [1]+[a-b for a,b in zip(vector[1:],self.origin[1:])]

    def decode(self, vector):
        if len(vector)!=10 or vector[0]!=1 or any(Fraction(v).denominator!=1 for v in vector):
            raise TransportRefusal('INVALID_PREDICTED_SEQUENCE')
        raw=[1]+[int(a)+b for a,b in zip(vector[1:],self.origin[1:])]
        n=raw[1]
        if not 0<=n<=self.width or raw[2:6]!=[int(i<n) for i in range(self.width)] or any(raw[6+n:]):
            raise TransportRefusal('INVALID_PREDICTED_OCCUPANCY')
        return list(reversed(raw[6:6+n]))


class Span:
    def __init__(self):
        self.rows=[]

    def add(self, before, after):
        x,y=list(map(Fraction,before)),list(map(Fraction,after))
        for pivot,b,c in self.rows:
            coefficient=x[pivot]
            x=[u-coefficient*v for u,v in zip(x,b)]
            y=[u-coefficient*v for u,v in zip(y,c)]
        pivot=next((i for i,v in enumerate(x) if v),None)
        if pivot is None:
            if any(y):raise TransportRefusal('INCONSISTENT_LINEAR_RELATION')
            return False
        divisor=x[pivot]
        self.rows.append((pivot,[v/divisor for v in x],[v/divisor for v in y]))
        return True

    def apply(self, before):
        x=list(map(Fraction,before));result=[Fraction(0)]*len(x)
        for pivot,b,c in self.rows:
            coefficient=x[pivot]
            x=[u-coefficient*v for u,v in zip(x,b)]
            result=[u+coefficient*v for u,v in zip(result,c)]
        if any(x):raise TransportRefusal('OUTSIDE_OBSERVED_INPUT_SPAN')
        return result

    def artifact(self):
        return [{'pivot':p,'input':[str(v) for v in b],'output':[str(v) for v in c]} for p,b,c in self.rows]


class LinearTransport:
    def __init__(self, origin, binding):
        self.embedding=Embedding(origin)
        self.binding=dict(binding)
        self.actions={}
        self.status='CANDIDATE_TRANSPORT'
        self.counterexample=None

    @classmethod
    def fit(cls, origin, transitions, binding):
        if origin is None:
            result=cls([],binding);result.status='NO_TRANSFER_LAW'
            result.counterexample={'reason':'NATIVE_IMAGE_UNAVAILABLE','required_additional_distinction':'Inspectable source-native state or relation; none synthesized.'}
            return result
        result=cls(origin,binding);seen={}
        for transition in transitions:
            action=transition['action'];x=result.embedding.encode(transition['before']);y=result.embedding.encode(transition['after'])
            key=(action,tuple(x))
            old=seen.get(key)
            if old is not None and old['after']!=transition['after']:
                result.status='INSUFFICIENT_STATE'
                result.counterexample={'reason':'SAME_D_SAME_ACTION_DIFFERENT_SUCCESSOR','action':action,'coordinate':x,
                    'histories':[old['history'],transition['history']],'successors':[old['after'],transition['after']],
                    'required_additional_distinction':'Must distinguish these two source histories before applying this action; not added automatically.'}
                return result
            seen[key]=transition
            try:result.actions.setdefault(action,Span()).add(x,y)
            except TransportRefusal as error:
                result.status='NO_TRANSFER_LAW';result.counterexample={'reason':str(error),'transition':transition}
                return result
        if not result.actions:result.status='NO_TRANSFER_LAW'
        return result

    def step(self, image, action):
        if self.status!='CANDIDATE_TRANSPORT':raise TransportRefusal(self.status)
        if action not in self.actions:raise TransportRefusal('UNOBSERVED_ACTION')
        return self.embedding.decode(self.actions[action].apply(self.embedding.encode(image)))

    def assert_binding(self, binding):
        if binding!=self.binding:raise TransportRefusal('SOURCE_VERSION_OBSERVER_ALIGNMENT_REQUIRED')

    def artifact(self):
        return {'version':VERSION,'status':self.status,'binding':self.binding,'origin_raw':self.embedding.origin,
                'actions':{str(a):s.artifact() for a,s in self.actions.items()},'counterexample':self.counterexample,
                'guard':'valid integer sequence AND observed input span AND native action guard AND exact binding',
                'scope':'bounded empirical source transport, no universal/source equality claim',
                'proof_status':'unverified','execution_allowed':False}

    @classmethod
    def restore(cls, artifact):
        raw=artifact['origin_raw'];n=raw[1]
        result=cls(list(reversed(raw[6:6+n])),artifact['binding'])
        result.status=artifact['status'];result.counterexample=artifact['counterexample']
        for action,rows in artifact['actions'].items():
            span=Span()
            span.rows=[(r['pivot'],list(map(Fraction,r['input'])),list(map(Fraction,r['output']))) for r in rows]
            result.actions[int(action)]=span
        return result


class Predictor:
    """No native E calls: compose frozen maps; query only declared guard and O."""
    def __init__(self, law, native_port, observer, binding):
        law.assert_binding(binding)
        self.law,self.port,self.observer=law,native_port,observer
        self.guard_cache,self.observation_cache={},{}

    def predict(self, image, word):
        flags=[];current=list(image)
        try:
            for action in word:
                following=self.law.step(current,action)
                key=(tuple(current),action)
                if key not in self.guard_cache:self.guard_cache[key]=self.port.guard_image(current,action)
                allowed=self.guard_cache[key];flags.append(allowed)
                if not allowed:
                    return {'status':'PREDICTED','readout':{'defined':False,'observation':None,'admissibility':flags}}
                current=following
            key=tuple(current)
            if key not in self.observation_cache:self.observation_cache[key]=self.port.observe_image(current,self.observer)
            return {'status':'PREDICTED','readout':{'defined':True,'observation':self.observation_cache[key],'admissibility':flags},'image':current}
        except TransportRefusal as error:
            return {'status':'INSUFFICIENT_STATE','reason':str(error),'prefix_guards':flags,'asserts_equivalence':False}
