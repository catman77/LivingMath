"""One explicit source-law candidate. Not an extension of013's integer learner."""
import hashlib
import json
from decimal import Decimal,localcontext


def binding_fingerprint(binding):
    # Display labels are intentionally absent; true addresses and definitions are mandatory.
    keys=('source_address','origin_id','h','t','observer','version','definition_sha256')
    return hashlib.sha256(json.dumps({k:binding[k] for k in keys},sort_keys=True,separators=(',',':')).encode()).hexdigest()


def require_binding(binding,expected):
    if binding_fingerprint(binding)!=binding_fingerprint(expected):raise ValueError('SOURCE_REBIND_REQUIRED')


def discover(native,training,nodes):
    I=native.I;checked=[]
    for pair in training:
        for row in pair:
            sign=row['exponent_sign'];a=row['source_address'];u=I(*nodes[str(a['cell']*8+a['node'])]['u'])
            if row['exact_expression']!={'op':'A*exp(epsilon*u*(h+i*t))','origin_id':row['origin_id'],'epsilon':sign}:
                raise ValueError('UNSUPPORTED_ACTUAL_SOURCE_EXPRESSION')
            for component in ('re','im'):
                residual=I(*row['d_h'][component])-sign*u*I(*row['value'][component])
                if not residual.lo<=0<=residual.hi:raise ValueError('SOURCE_DERIVATIVE_LEDGER_MISMATCH')
            checked.append(row['index'])
    return {'status':'LAW_CANDIDATE','mechanism':'Native exp parameter-addition law; source expression supplies the analytic mechanism.',
            'formula':'f_a(h+delta,t)=exp(epsilon*u_a*delta)*f_a(h,t)',
            'coordinate':'epsilon*u_a, with d_h f=(epsilon*u_a) f checked on training addresses',
            'training_addresses':sorted(set(checked)),'old013_induction':False,
            'novel_theorem':False,'proof_status':'unverified',
            'guard':'unchanged address/origin/definition/observer/version, fixed t and amplitude, real delta; archived source analytic domain'}


def predict(native,anchor,node,h,h0='0'):
    if not Decimal(h).is_finite() or abs(Decimal(h))>Decimal('.5') or Decimal(h)**2+Decimal(native.TARGET)**2>729:
        raise ValueError('OUTSIDE_ARCHIVED_ANALYTIC_GUARD')
    if anchor['exponent_sign'] not in (-1,1):raise ValueError('INVALID_SOURCE_BRANCH')
    I=native.I;u=I(*node['u']);multiplier=(anchor['exponent_sign']*u*(I(h)-I(h0))).exp()
    return {c:(I(*anchor['value'][c])*multiplier).json() for c in ('re','im')}


def interpolation(a,b,h,hermite=False):
    with localcontext() as ctx:
        ctx.prec=90;delta=Decimal('.001');x=Decimal(h)/delta;out={}
        for component in ('re','im'):
            mid=lambda v:(Decimal(v[0])+Decimal(v[1]))/2
            f0,f1=mid(a['value'][component]),mid(b['value'][component])
            if hermite:
                d0,d1=mid(a['d_h'][component]),mid(b['d_h'][component])
                value=(2*x**3-3*x*x+1)*f0+(x**3-2*x*x+x)*delta*d0+(-2*x**3+3*x*x)*f1+(x**3-x*x)*delta*d1
            else:value=f0+x*(f1-f0)
            out[component]=str(value)
        return out


def assess(prediction,actual,anchors):
    result={};passed=True
    with localcontext() as ctx:
        ctx.prec=90
        scale=max(abs(Decimal(v)) for row in anchors for component in ('re','im') for v in row['value'][component])
        tolerance=scale*Decimal('1e-40')
        for component in ('re','im'):
            lo,hi=map(Decimal,actual['value'][component]);p=prediction[component]
            if isinstance(p,list):
                pl,ph=map(Decimal,p);ok=max(pl,lo)<=min(ph,hi) and ph-pl<=tolerance and hi-lo<=tolerance
                error=abs((pl+ph-lo-hi)/2);width=str(ph-pl)
            else:
                error=abs(Decimal(p)-(lo+hi)/2);ok=error<=tolerance;width=None
            result[component]={'PASS':ok,'midpoint_absolute_error':str(error),'tolerance':str(tolerance),'prediction_width':width}
            passed &= ok
    return {'PASS':passed,'components':result}
