"""Small outward-rounded Decimal intervals; no third-party dependencies."""
from decimal import Decimal, Context, ROUND_FLOOR, ROUND_CEILING, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
P=58
DN=Context(prec=P, rounding=ROUND_FLOOR, Emin=-999999, Emax=999999)
UP=Context(prec=P, rounding=ROUND_CEILING, Emin=-999999, Emax=999999)
NEAR=Context(prec=P, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999)
class I:
    __slots__=('lo','hi')
    def __init__(self,lo,hi=None):
        if isinstance(lo,I): self.lo,self.hi=lo.lo,lo.hi; return
        self.lo=Decimal(lo); self.hi=Decimal(lo if hi is None else hi)
        assert self.lo<=self.hi
    @classmethod
    def frac(cls,q):
        q=Fraction(q)
        return cls(DN.divide(Decimal(q.numerator),Decimal(q.denominator)),UP.divide(Decimal(q.numerator),Decimal(q.denominator)))
    def __add__(self,b):
        b=I(b); return I(DN.add(self.lo,b.lo),UP.add(self.hi,b.hi))
    __radd__=__add__
    def __neg__(self): return I(self.hi.copy_negate(),self.lo.copy_negate())
    def __sub__(self,b): return self+-I(b)
    def __rsub__(self,b): return I(b)+-self
    def __mul__(self,b):
        b=I(b); pairs=[(x,y) for x in (self.lo,self.hi) for y in (b.lo,b.hi)]
        return I(min(DN.multiply(x,y) for x,y in pairs),max(UP.multiply(x,y) for x,y in pairs))
    __rmul__=__mul__
    def __truediv__(self,b):
        b=I(b)
        assert b.lo>0 or b.hi<0, (b.lo,b.hi)
        pairs=[(x,y) for x in (self.lo,self.hi) for y in (b.lo,b.hi)]
        return I(min(DN.divide(x,y) for x,y in pairs),max(UP.divide(x,y) for x,y in pairs))
    def __rtruediv__(self,b): return I(b)/self
    def __pow__(self,n):
        assert isinstance(n,int) and n>=0
        out=I(1); a=self
        while n:
            if n&1: out=out*a
            n//=2
            if n: a=a*a
        return out
    def exp(self):
        # Decimal.exp is correctly rounded to nearest, even for directed contexts.
        # Widen by one representable number on each side.
        a=NEAR.exp(self.lo); b=NEAR.exp(self.hi)
        return I(NEAR.next_minus(a),NEAR.next_plus(b))
    def radius_bound(self): return max(self.lo.copy_abs(),self.hi.copy_abs())
    def widen(self,e):
        e=I(e).radius_bound(); return self+I(e.copy_negate(),e)
    def mid(self): return NEAR.divide(NEAR.add(self.lo,self.hi),Decimal(2))
    def json(self): return [str(self.lo),str(self.hi)]
    def __repr__(self): return f'I({self.lo},{self.hi})'

def atan_recip(q,m):
    S=sum((Fraction((-1)**k,(2*k+1)*q**(2*k+1)) for k in range(m)),Fraction())
    nxt=Fraction((-1)**m,(2*m+1)*q**(2*m+1))
    return I.frac(min(S,S+nxt))+I(0,(I.frac(max(S,S+nxt))-I.frac(min(S,S+nxt))).hi)

def pi_interval(): return 16*atan_recip(5,52)-4*atan_recip(239,17)

def exp_i(theta,terms=24):
    """Finite Taylor enclosure + algebraic repeated squaring; returns cos,sin."""
    theta=I(theta); k=0; y=theta
    while y.radius_bound()>Decimal('.125'):
        y=y/2; k+=1
    # exp(iy), successive complex terms. All evaluations are finite.
    tr,ti=I(1),I(0); cr,ci=tr,ti
    for j in range(1,terms+1):
        tr,ti=-(ti*y)/j,(tr*y)/j
        cr,ci=cr+tr,ci+ti
    r=I(y.radius_bound()); tail=2*r**(terms+1)
    import math
    tail=tail/math.factorial(terms+1)
    cr,ci=cr.widen(tail.hi),ci.widen(tail.hi)
    for _ in range(k): cr,ci=cr*cr-ci*ci,2*cr*ci
    return cr,ci
