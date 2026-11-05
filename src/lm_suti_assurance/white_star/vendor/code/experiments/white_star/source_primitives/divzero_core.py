"""Source-grounded finite portion of SRT Div_Zero.md.

SOURCES:
- library /SymSeq/Div_Zero.md, DIV-R2 and D11 (pair model, 0/0 fibers)
- library /SymSeq/SymStructures_v3.pdf, section 2.1 (S/P arithmetic)

NOT source code recovered from a file called Div Zero V1. This is a new,
fully explicit executable implementation of *specified source equations*.

No regular numerical division by zero is performed. 0/0 denotes a
multiplication-inverse fiber in the structure A=N^2 (non-absorbing zeros),
with a separate ratio presentation. The exceptional fiber at Z0/Z0 is
infinite; finite truncation makes it enumerable in a controlled experiment.
"""
from dataclasses import dataclass
from math import gcd
from typing import Tuple

@dataclass(frozen=True)
class Pair:
    s: int
    p: int
    def __post_init__(self):
        if self.s < 0 or self.p < 0: raise ValueError("pair coefficients must be nonnegative")
    def epsilon(self) -> int: return self.s - self.p
    def iota(self) -> 'Pair': return Pair(self.p, self.s)
    def add(self, other: 'Pair') -> 'Pair': return Pair(self.s+other.s, self.p+other.p)
    def multiply(self, other: 'Pair') -> 'Pair':
        return Pair(self.s*other.s+self.p*other.p, self.s*other.p+self.p*other.s)
    def norm(self) -> int: return self.s + self.p
    def sp_word(self, max_chars=96) -> str:
        w = 'S'*min(self.s,max_chars//2)+'P'*min(self.p,max_chars//2)
        return w if len(w)<max_chars else w[:max_chars]+'…'

ZERO = Pair(0,0)
ONE = Pair(1,0)
def z(u: int) -> Pair:
    return Pair(u,u)

def equal_sharp(x: Pair, y: Pair) -> bool:
    """Exact equality in the N^2 model; not merely equality of shadow epsilon."""
    return x == y

def div_fibre(numerator: Pair, denominator: Pair, bound: int=64) -> Tuple[Pair,...]:
    """Finite enumeration of all q such that q * denominator == numerator.

    Special zero sectors are formula-based, not a fabricated scalar value.
    With Z_u=(u,u), Z_v=(v,v), u>0 and v=n*u: exactly n+1 solutions
    q=(a,b) with a+b=n. With Z0/Z0 all q possible, truncated by norm<=bound.
    """
    if bound < 0: raise ValueError("negative bound")
    if denominator == ZERO:
        if numerator != ZERO: return ()
        return tuple(Pair(a,s-a) for s in range(bound+1) for a in range(s+1))
    if denominator.s == denominator.p and numerator.s == numerator.p and denominator.s>0:
        u,v=denominator.s,numerator.s
        if v%u != 0:return ()
        n=v//u
        if n > bound:return ()
        return tuple(Pair(a,n-a) for a in range(n+1))
    out=[]
    for s in range(bound+1):
        for a in range(s+1):
            q=Pair(a,s-a)
            if equal_sharp(q.multiply(denominator),numerator):out.append(q)
    return tuple(out)

@dataclass(frozen=True)
class RatPres:
    """Formal fraction presentation; no projective quotient by zero rescaling."""
    numerator: Pair
    denominator: Pair
    def rho(self) -> 'RatPres':
        return RatPres(self.denominator,self.numerator)
    def J(self) -> 'RatPres':
        return RatPres(self.denominator.iota(), self.numerator)
    def T(self, q: Pair) -> 'RatPres':
        return RatPres(self.numerator.add(q.multiply(self.denominator)),self.denominator)
    def product(self,other:'RatPres')->'RatPres':
        return RatPres(self.numerator.multiply(other.numerator), self.denominator.multiply(other.denominator))
    def divide(self,other:'RatPres')->'RatPres':
        return self.product(other.rho())
    def is_exceptional(self): return self.numerator==ZERO and self.denominator==ZERO

@dataclass(frozen=True)
class DivisionWitness:
    """Witness q for 0/0, carrying original numerator/denominator."""
    numerator:Pair
    denominator:Pair
    quotient:Pair
    def verify(self)->bool: return self.quotient.multiply(self.denominator)==self.numerator
    @property
    def presentation(self):return RatPres(self.numerator,self.denominator)
    @property
    def direction(self):return (self.quotient.s,self.quotient.p)
    @property
    def gcd(self):return gcd(self.quotient.s,self.quotient.p)

def zero_over_zero_witness(a:int,b:int)->DivisionWitness:
    """Every a,b>=0 is an exact member of DivFib#(Z0,Z0)."""
    witness=DivisionWitness(ZERO,ZERO,Pair(a,b))
    assert witness.verify()
    return witness

@dataclass(frozen=True)
class EuclideanTraceStep:
    quotient_steps: int
    residual: int
    divisor: int


def euclid_repeated_subtraction(a:int,b:int,steps:int):
    """Finite prefix of original symbolic repeated-subtraction division.

    For b=0 each step is r <- r-0 = r and quotient_steps increases;
    no actual quotient is claimed. Distinct zero-fibre witnesses are ADDITIONAL
    structure from the later Div_Zero.md pair-model, not a consequence of
    repeated subtraction alone.
    """
    if a<0 or b<0 or steps<0:raise ValueError('nonnegative inputs required')
    r=a;trace=[EuclideanTraceStep(0,a,b)]
    for n in range(1,steps+1):
        if b>0 and r<b:break
        r-=b
        trace.append(EuclideanTraceStep(n,r,b))
    return tuple(trace)
