"""Lexical binder normalization, without model enumeration or source semantics."""
from ...core import digest
from ...formal_bridge.fol import typecheck

VERSION='sb-alpha/1'


def canonicalize(formula,signature):
    check=typecheck(formula,signature)
    if check['status']!='TYPED':raise ValueError(check['reason'])
    def walk(p,env):
        def terms(xs):return [env[::-1].index(t['var']) for t in xs]
        if 'quant' in p:return ['quant',p['quant'],p['sort'],walk(p['body'],[*env,p['var']])]
        if 'pred' in p:return ['pred',p['pred'],terms(p['args'])]
        if 'eq' in p:return ['eq',terms(p['eq'])]
        if 'not' in p:return ['not',walk(p['not'],env)]
        op='and' if 'and' in p else 'or'
        return [op,[walk(x,env) for x in p[op]]]
    return walk(formula,[])


def prove_alpha(left,right,signature):
    a,b=canonicalize(left,signature),canonicalize(right,signature)
    if a!=b:return {'status':'NOT_ALPHA_EQ','model_enumerations':0}
    cert={'rule':'ALPHA_NORMALIZATION','checker_version':VERSION,'input_formula_sha256_left':digest(left),'input_formula_sha256_right':digest(right),'canonical_sha256_left':digest(a),'canonical_sha256_right':digest(b),'signature_sha256':digest(signature),'result':'PROVED_ALPHA_EQ'}
    from .checker import check_certificate
    if not check_certificate(left,right,signature,cert):raise ValueError('INDEPENDENT_CERTIFICATE_REJECTED')
    return {'status':'PROVED_ALPHA_EQ','certificate':cert,'certificate_sha256':digest(cert),'independent_check':'PASS','model_enumerations':0}
