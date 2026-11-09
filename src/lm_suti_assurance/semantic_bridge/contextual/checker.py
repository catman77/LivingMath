"""Independent certificate reconstruction. Never trust producer normal forms/rows."""
from itertools import product
from ...core import digest,canonical
from ...formal_bridge.fol import typecheck


def normal(p,environment=None,depth=0):
    env={} if environment is None else environment
    if 'quant' in p:return ['quant',p['quant'],p['sort'],normal(p['body'],{**env,p['var']:depth},depth+1)]
    def addresses(terms):return [depth-env[t['var']]-1 for t in terms]
    if 'pred' in p:return ['pred',p['pred'],addresses(p['args'])]
    if 'eq' in p:return ['eq',addresses(p['eq'])]
    if 'not' in p:return ['not',normal(p['not'],env,depth)]
    key=next(k for k in ['and','or'] if k in p)
    return [key,[normal(x,env,depth) for x in p[key]]]


def check_certificate(left,right,signature,certificate):
    try:
        if any(typecheck(p,signature)['status']!='TYPED' for p in [left,right]):return False
        if certificate['signature_sha256']!=digest(signature) or certificate['input_formula_sha256_left']!=digest(left) or certificate['input_formula_sha256_right']!=digest(right):return False
        a,b=normal(left),normal(right)
        if certificate['rule']=='ALPHA_NORMALIZATION':
            expected={'rule':'ALPHA_NORMALIZATION','checker_version':'sb-alpha/1','input_formula_sha256_left':digest(left),'input_formula_sha256_right':digest(right),'canonical_sha256_left':digest(a),'canonical_sha256_right':digest(b),'signature_sha256':digest(signature),'result':'PROVED_ALPHA_EQ'}
            return a==b and canonical(certificate)==canonical(expected)
        if certificate['rule']!='FORALL_BOOLEAN_TAUTOLOGY' or certificate['checker_version']!='sb-forall-boolean/1':return False
        def strip(p):
            sorts=[]
            while p[0]=='quant':
                if p[1]!='forall':raise ValueError('UNSUPPORTED_PREFIX')
                sorts.append(p[2]);p=p[3]
            return sorts,p
        sa,a=strip(a);sb,b=strip(b)
        if sa!=sb:return False
        atoms={}
        def collect(p):
            if p[0] in ('pred','eq'):atoms[canonical(p)]=p
            elif p[0]=='not':collect(p[1])
            elif p[0] in ('and','or'):
                for q in p[1]:collect(q)
            else:raise ValueError('INTERNAL_QUANTIFIER')
        collect(a);collect(b);keys=sorted(atoms)
        if len(keys)>10 or certificate['atoms']!=[atoms[k] for k in keys] or certificate['prefix_sorts']!=sa:return False
        if certificate['matrix_sha256_left']!=digest(a) or certificate['matrix_sha256_right']!=digest(b):return False
        def val(p,values):
            op=p[0]
            if op in ('pred','eq'):return values[canonical(p)]
            if op=='not':return not val(p[1],values)
            answers=[val(q,values) for q in p[1]]
            return all(answers) if op=='and' else any(answers)
        rows=[]
        for bits in product([False,True],repeat=len(keys)):
            values=dict(zip(keys,bits));x,y=val(a,values),val(b,values)
            if x and not y:return False
            rows.append([list(bits),x,y])
        expected={'rule':'FORALL_BOOLEAN_TAUTOLOGY','checker_version':'sb-forall-boolean/1','input_formula_sha256_left':digest(left),'input_formula_sha256_right':digest(right),'signature_sha256':digest(signature),'prefix_sorts':sa,'matrix_sha256_left':digest(a),'matrix_sha256_right':digest(b),'atoms':[atoms[k] for k in keys],'rows_checked':len(rows),'truth_table_sha256':digest(rows),'equality_treatment':'INDEPENDENT_BOOLEAN_ATOM_SUFFICIENT_ONLY','result':'PROVED_ENTAILMENT'}
        return canonical(certificate)==canonical(expected)
    except (ValueError,KeyError,TypeError,RecursionError):return False
