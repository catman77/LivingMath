"""Reversible 8-bit UDAV historical law + new CAD observation controller.

Historical recurrence s[t+1]=s[t-1] xor G(s[t]),
G(s) = ((s<<1) xor (s>>3)) &127; reconstructed from historical project
report, NOT the entire latest UDAV code. Controller is new.
"""
from collections import Counter
from math import gcd, isqrt
from dataclasses import dataclass
from divzero_core import Pair, z, DivisionWitness, zero_over_zero_witness
from cad import CHARTS, project, sanity_check

class ReversibleUDAV:
    def __init__(self,seed=42):
        self.a=int(seed)&255
        self.b=(int(seed)*73+37)&255
    @staticmethod
    def G(x):return ((x<<1)^(x>>3))&127
    def step(self):
        self.a,self.b=self.b,self.a^self.G(self.b)
        return self.b
    @staticmethod
    def inv(a,b):
        # Input pair is state AFTER update (old_b, new_b).
        return b^ReversibleUDAV.G(a),a

class WhiteStarOrbit:
    """Exhaustive, expanding enumeration of witnesses of Z0/Z0.

    t->(a,b), a+b=s for triangular layers; no RNG and no arbitrary
    numeric division by zero. Each witness ALSO proves Z_s / Z_1, with
    exactly s+1 members per layer. Seed scrambles within layer bijectively.
    """
    def __init__(self,seed=0):self.t=0;self.seed=int(seed)
    def next(self):
        t=self.t;self.t+=1
        s=(isqrt(8*t+1)-1)//2
        pos=t-s*(s+1)//2
        m=s+1
        # invertible stride, unique witness at every position of the layer
        stride=(2*(self.seed%19)+1)
        while gcd(stride,m)!=1:stride+=2
        a=(pos*stride+self.seed)%m
        b=s-a
        w=zero_over_zero_witness(a,b)
        # stronger finite-fibre statement: q*Z_1 == Z_s
        assert w.quotient.multiply(z(1))==z(s)
        return w

class GraphTopology:
    """Betti numbers β0, β1 of the observed undirected signature graph.
    This is NOT a claim about the full topological space of division objects.
    """
    def __init__(self):
        self.parent={};self.edges=set();self.beta0=0;self.beta1=0
    def root(self,x):
        if x not in self.parent:return None
        while self.parent[x]!=x:
            self.parent[x]=self.parent[self.parent[x]]
            x=self.parent[x]
        return x
    def novelty(self,prev,cur):
        nv=int(cur not in self.parent)
        if prev is None:return nv,0,0
        edge=frozenset((prev,cur))
        if prev==cur:return nv,0,0
        ne=int(edge not in self.edges)
        cyc=int(ne and prev in self.parent and cur in self.parent and self.root(prev)==self.root(cur))
        return nv,ne,cyc
    def add(self,prev,cur):
        if cur not in self.parent:self.parent[cur]=cur;self.beta0+=1
        if prev is None:return
        if prev not in self.parent:self.parent[prev]=prev;self.beta0+=1
        if prev==cur:return
        e=frozenset((prev,cur))
        if e in self.edges:return
        self.edges.add(e)
        rp,rc=self.root(prev),self.root(cur)
        if rp==rc:self.beta1+=1
        else:self.parent[rc]=rp;self.beta0-=1

class UDAVController:
    """Topologically informed active chooser of CAD projections.

    Selection is based on novelty of observed signature-graph topology,
    then rarity of signatures and used charts. No TSP cost is used.
    """
    def __init__(self,seed=42,mode='active'):
        if mode not in ('active','fixed','rotate','balanced','active_nobin'):raise ValueError(mode)
        self.seed=seed;self.mode=mode
        self.orbit=WhiteStarOrbit(seed)
        self.reversible=ReversibleUDAV(seed)
        self.graph=GraphTopology();self.prev=None
        self.seen=Counter();self.used=Counter();self.phase=Counter()
        self.count=0;self.unique_witnesses=set();self.u_hist=[]
        self.last=None
    def next(self,context=None):
        self.count+=1
        w=self.orbit.next()
        self.unique_witnesses.add(w.direction)
        state=self.reversible.step()
        if self.mode=='fixed': candidates=(0,)
        elif self.mode=='rotate': candidates=(self.count%len(CHARTS),)
        else: candidates=range(len(CHARTS))
        best=None
        for j in candidates:
            p=project(w,j)
            new_v,new_e,new_cycle=self.graph.novelty(self.prev,p.signature)
            if self.mode=='balanced':
                # Control without structural novelty; same 29 candidate charts.
                key=(1/(1+self.phase[int(p.quantile*8)]),
                     1/(1+self.used[j]),-((j+state)%len(CHARTS)))
            elif self.mode=='active_nobin':
                # Structural graph novelty without quantile-bin coverage term.
                key=(new_v*4+new_cycle*2+new_e*2,
                     1/(1+self.seen[p.signature]),
                     1/(1+self.used[j]),-((j+state)%len(CHARTS)))
            else:
                key=(new_v*4+new_cycle*2+new_e*2,
                     1/(1+self.seen[p.signature]),
                     1/(1+self.phase[int(p.quantile*8)]),
                     1/(1+self.used[j]),
                     -((j+state)%len(CHARTS)))
            if best is None or key>best[0]:best=(key,p)
        p=best[1]
        self.graph.add(self.prev,p.signature);self.prev=p.signature
        self.seen[p.signature]+=1;self.used[p.view]+=1
        self.phase[min(int(p.quantile*8),7)]+=1
        self.u_hist.append(p.quantile)
        self.last=(w,p)
        return p.quantile
    def snapshot(self):
        return {'witness_count':len(self.unique_witnesses),
                'observed_signature_count':len(self.graph.parent),
                'transition_edges':len(self.graph.edges),
                'beta0':self.graph.beta0,'beta1':self.graph.beta1,
                'charts_used':len(self.used),
                'quantile_bins':[self.phase[i] for i in range(8)]}

def tests():
    assert sanity_check()>10
    for a in range(256):
        for b in range(256):
            r=ReversibleUDAV(a);r.a=a;r.b=b;r.step()
            assert ReversibleUDAV.inv(r.a,r.b)==(a,b)
    for mode in ('active','fixed','rotate'):
        o=UDAVController(42,mode)
        for i in range(500):assert 0<o.next()<1
        assert o.graph.beta1==len(o.graph.edges)-len(o.graph.parent)+o.graph.beta0
    return True

if __name__=='__main__':
    print('PASS',tests())
    for mode in ('fixed','rotate','active'):
        o=UDAVController(42,mode)
        for i in range(3000):o.next()
        print(mode,o.snapshot())
