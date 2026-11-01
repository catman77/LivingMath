"""An explicitly ordered, refinable theta-kernel source for completed xi.
Each realization retains (cell,node,n,branch) addresses and edge order.
Numeric reduction is an observer, never source equality.
"""
import json, math
from pathlib import Path
from fractions import Fraction
import numpy as np
from scipy.special import roots_legendre
from intervals import I,pi_interval,exp_i

U=2; N=4; M=256; ORDER=8

def fast_source(h=0.,t=0.,cells=M,n_max=N,u_max=U):
    U,N=u_max,n_max
    x,w=roots_legendre(ORDER); d=U/(2*cells)
    u=(((np.arange(cells)+.5)*U/cells)[:,None]+d*x).reshape(-1)
    weights=np.tile(w*d,cells)
    n=np.arange(1,N+1)
    a=np.pi*n[None,:]**2*np.exp(2*u[:,None])
    amp=weights[:,None]*(4*a*a-6*a)*np.exp(u[:,None]/2-a)
    z=(h+1j*t)*u[:,None]
    edges=np.stack((amp*np.exp(z),amp*np.exp(-z)),axis=-1)
    return u,amp,edges.reshape(-1)

def fast_read(h,t,cells=M,n_max=N,u_max=U):
    u,amp,_=fast_source(cells=cells,n_max=n_max,u_max=u_max)
    return np.sum(2*amp.sum(axis=1)*np.cosh((h+1j*t)*u))

def poly8(x):
    return 6435*x**8-12012*x**6+6930*x**4-1260*x**2+35

def exact_gauss_nodes():
    """Disjoint rational sign brackets for eight roots of explicit P8."""
    guesses,_=roots_legendre(8); out=[]; brackets=[]
    for seed in guesses:
        l=Fraction(str(float(seed)))-Fraction(1,10**12)
        r=Fraction(str(float(seed)))+Fraction(1,10**12)
        fl=poly8(l); fr=poly8(r); assert fl*fr<0
        while r-l>Fraction(1,10**56):
            m=(l+r)/2; fm=poly8(m)
            if fl*fm<0: r=m;fr=fm
            else: l=m;fl=fm
        x=I(I.frac(l).lo,I.frac(r).hi)
        # Explicit polynomial entering the algebraic weight formula.
        D=(51480*x**7-72072*x**5+27720*x**3-2520*x)/128
        w=2/((1-x*x)*D*D)
        out.append((x,w));brackets.append({'lo':str(l),'hi':str(r),'x':x.json(),'weight':w.json()})
    assert all(out[j][0].hi<out[j+1][0].lo for j in range(7))
    return out,brackets

def prepare_certified(cells=M,n_max=N,u_max=U):
    U,N=u_max,n_max
    pi=pi_interval(); nodes,brackets=exact_gauss_nodes(); d=I(U)/(2*cells)
    data=[]
    for j in range(cells):
        c=I(U)*(2*j+1)/(2*cells)
        for x,w in nodes:
            u=c+d*x; eu=(2*u).exp(); phi=I(0)
            for n in range(1,N+1):
                a=pi*n*n*eu
                phi=phi+(4*a*a-6*a)*(u/2-a).exp()
            data.append((u,d*w*phi))
    return data,brackets,pi

def error_bounds(cells=M,H='0.5',L='27',n_max=N,u_max=U):
    """Uniform bounds for |h|<=H, |h+it|<=L (H<=.5)."""
    U,N=u_max,n_max
    H,L=I(H),I(L); assert H.lo>=0 and H.hi<=I('.5').hi and L.lo>=0
    assert U>=0 and N>=1 and cells>16*U
    d=I(U)/(2*cells); R=I(1)/16; pi=pi_interval(); majors=I(0)
    for j in range(cells):
        c=I(U)*(2*j+1)/(2*cells)
        for n in range(1,N+1):
            a=pi*n*n*(2*c).exp()
            maj=2*((I('.5')+H)*c+a*((2*R).exp()-2)).exp()*(4*a*a*((I('4.5')+L)*R).exp()+6*a*((I('2.5')+L)*R).exp())
            majors=majors+maj
    eq=4*d*majors*(d/R)**16
    k=N+1
    en=27*k*k*I(-3*k*k).exp()/(1-4*I(-3*(2*k+1)).exp())
    X=I(2*U).exp()
    eu=27*X**2*(-3*X).exp()/(1-4*(-9*X).exp())
    total=eq+en+eu
    return {'quadrature':eq.json(),'n_tail':en.json(),'u_tail':eu.json(),'total':total.json(),'H':str(H.hi),'L':str(L.hi)}

def certified_read(data,h,t,bound):
    h,t=I(h),I(t); sr,si=I(0),I(0)
    for u,amp in data:
        co,sn=exp_i(t*u)
        plus=(h*u).exp(); minus=(-h*u).exp()
        sr=sr+amp*(plus+minus)*co
        si=si+amp*(plus-minus)*sn
    # The complete source is within the analytic omitted-contribution bound.
    e=bound['total'][1]
    return {'finite_re':sr.json(),'finite_im':si.json(),'full_re':sr.widen(e).json(),'full_im':si.widen(e).json()}
