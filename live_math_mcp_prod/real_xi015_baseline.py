"""Exploratory stronger baseline after P0, never labelled preregistered or blind.

Two-value geometric interpolation: f0*(f1/f0)^(h/.001). For the fixed
half/double queries only a complex square root/square is needed. No source
coordinate, derivative, theta formula or withheld value is read.
"""
from decimal import Decimal,localcontext


def geometric(a,b,h):
    with localcontext() as ctx:
        ctx.prec=90
        mid=lambda v:(Decimal(v[0])+Decimal(v[1]))/2
        x,y=mid(a['value']['re']),mid(a['value']['im'])
        u,v=mid(b['value']['re']),mid(b['value']['im']);den=x*x+y*y
        if den==0:raise ValueError('BASELINE_ZERO_ANCHOR')
        r,s=(u*x+v*y)/den,(v*x-u*y)/den
        fraction=Decimal(h)/Decimal('.001')
        if fraction==Decimal('.5'):
            if r<=0:raise ValueError('BASELINE_PRINCIPAL_ROOT_GUARD')
            p=((r*r+s*s).sqrt()+r)/2;p=p.sqrt();q=s/(2*p)
        elif fraction==2:p,q=r*r-s*s,2*r*s
        else:raise ValueError('BASELINE_QUERY_NOT_REGISTERED_HALF_OR_DOUBLE')
        return {'re':str(x*p-y*q),'im':str(x*q+y*p)}
