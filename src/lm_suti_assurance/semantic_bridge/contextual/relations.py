"""Conservative exact proofs, followed only by bounded existing FOL search."""
from itertools import product
from ...core import digest,canonical
from ...formal_bridge import fol
from ...formal_bridge.ir import Budget,Bound,limits
from .alpha import canonicalize,prove_alpha
from .checker import check_certificate


def prove_entailment(left,right,signature,max_atoms=10,work=None):
    a,b=canonicalize(left,signature),canonicalize(right,signature)
    def strip(p):
        prefix=[]
        while p[0]=='quant':
            if p[1]!='forall':raise ValueError('EXISTENTIAL_PREFIX')
            prefix.append(p[2]);p=p[3]
        return prefix,p
    atoms={}
    def collect(p):
        if p[0] in ('pred','eq'):atoms[canonical(p)]=p
        elif p[0]=='not':collect(p[1])
        elif p[0] in ('and','or'):
            for x in p[1]:collect(x)
        else:raise ValueError('INTERNAL_QUANTIFIER')
    try:
        pa,a=strip(a);pb,b=strip(b)
        if pa!=pb:raise ValueError('DIFFERENT_PREFIX_SORTS')
        collect(a);collect(b)
        if len(atoms)>min(max_atoms,10):raise ValueError('ATOM_BOUND')
    except ValueError as e:return {'status':'UNKNOWN_UNSUPPORTED_PROOF_CLASS','reason':str(e)}
    keys=sorted(atoms)
    def val(p,values):
        if p[0] in ('pred','eq'):return values[canonical(p)]
        if p[0]=='not':return not val(p[1],values)
        return (all if p[0]=='and' else any)(val(x,values) for x in p[1])
    rows=[]
    for bits in product([False,True],repeat=len(keys)):
        if work:work.tick()
        values=dict(zip(keys,bits));x,y=val(a,values),val(b,values);rows.append([list(bits),x,y])
        if x and not y:return {'status':'UNKNOWN_NOT_TAUTOLOGY','rows_checked':len(rows),'reason':'Boolean counterassignment is not a FOL countermodel'}
    cert={'rule':'FORALL_BOOLEAN_TAUTOLOGY','checker_version':'sb-forall-boolean/1','input_formula_sha256_left':digest(left),'input_formula_sha256_right':digest(right),'signature_sha256':digest(signature),'prefix_sorts':pa,'matrix_sha256_left':digest(a),'matrix_sha256_right':digest(b),'atoms':[atoms[k] for k in keys],'rows_checked':len(rows),'truth_table_sha256':digest(rows),'equality_treatment':'INDEPENDENT_BOOLEAN_ATOM_SUFFICIENT_ONLY','result':'PROVED_ENTAILMENT'}
    if not check_certificate(left,right,signature,cert):raise ValueError('INDEPENDENT_CERTIFICATE_REJECTED')
    return {'status':'PROVED_ENTAILMENT','certificate':cert,'certificate_sha256':digest(cert),'independent_check':'PASS'}


class Work:
    def __init__(self,budget):
        self.bounds=limits({k:v for k,v in budget.items() if k in ('max_models','max_cpu_ms','max_steps')});self.counter=Budget(self.bounds);self.models=0
    def tick(self,n=1):self.counter.tick(n)
    def remaining(self):
        import time
        self.tick();b=dict(self.bounds);b['max_steps']=max(1,b['max_steps']-self.counter.steps);b['max_cpu_ms']=max(1,int(b['max_cpu_ms']-(time.process_time()-self.counter.started)*1000));return b
    def evaluate(self,formula,signature,model):
        bounds=self.remaining();v=fol.evaluate(formula,signature,model,bounds)
        if v['status']=='UNKNOWN_BOUND':
            self.counter.steps+=bounds['max_steps']
            raise Bound('FORMULA_EVALUATION_BOUND')
        self.tick(v.get('evaluated_nodes',1));return v


def scenario(hypothesis,signature,model,work):
    f=work.evaluate(hypothesis['formula_ast'],signature,model) if 'formula_ast' in hypothesis else {'status':'ILL_TYPED','truth':None}
    assumptions=[]
    for assumption in hypothesis['assumptions']:
        value=work.evaluate(assumption,signature,model)
        if value['status']=='ILL_TYPED':value={'status':'UNKNOWN','truth':None,'reason':'ILL_TYPED_ASSUMPTION','typecheck':value['typecheck'],'execution_permission':False}
        assumptions.append(value)
    statuses=[x['status'] for x in assumptions]
    applicability='CONTEXT_INCOMPATIBLE' if 'FALSE' in statuses else 'UNKNOWN_CONTEXT' if any(x!='TRUE' for x in statuses) else 'APPLICABLE'
    obligations=[]
    for o in hypothesis['obligations']:
        v={**o,'status':'OPEN'}
        if 'assumption_ast' in o:v['formal_assumption_check']=work.evaluate(o['assumption_ast'],signature,model)
        obligations.append(v)
    return {'hypothesis_ref':hypothesis['hypothesis_ref'],'client_id':hypothesis['client_id'],'formula_truth':f['status'] if f['status'] in ('TRUE','FALSE','ILL_TYPED') else 'UNKNOWN','formula_evaluation':f,'assumption_truths':assumptions,'applicability':applicability,'assumption_scope':'DECLARED_ASSUMPTIONS' if assumptions else 'NO_DECLARED_ASSUMPTIONS','source_alignment_status':'LANGUAGE_INSUFFICIENT' if hypothesis['type_status']=='LANGUAGE_INSUFFICIENT' else 'PROPOSED','obligations':obligations,'execution_permission':False}


def pair(left,right,signature,budget,work):
    edge={'left_ref':left['hypothesis_ref'],'right_ref':right['hypothesis_ref'],'client_ids':[left['client_id'],right['client_id']],'source_alignment_status':'PROPOSED','comparison_scope':'ALL_CANDIDATE_ASSUMPTIONS_HOLD','context_applicability':'UNKNOWN_CONTEXT','formal_contrast_calls':0,'model_enumerations':0,'countermodels':[],'execution_permission':False}
    if any(h['type_status']!='TYPED' for h in (left,right)):return {**edge,'status':'TYPE_REJECTED','reason':'Untyped or unsupported hypotheses are retained but never matched'}
    a,b=left['formula_ast'],right['formula_ast'];alpha=prove_alpha(a,b,signature);edge['alpha']=alpha
    if alpha['status']=='PROVED_ALPHA_EQ':return {**edge,'status':'PROVED_ALPHA_EQ','proof_scope':'FORMULAS_ONLY_ASSUMPTIONS_RETAINED_SEPARATELY'}
    directions={}
    for key,x,y in [('A_IMPLIES_B',a,b),('B_IMPLIES_A',b,a)]:directions[key]=prove_entailment(x,y,signature,budget.get('max_atoms',10),work)
    edge['directions']=directions
    # Search guards only constrain a requested direction; never become source assumptions.
    common=[*left['assumptions'],*right['assumptions']]
    for key,x,y,label in [('A_IMPLIES_B',a,b,'COUNTERMODEL_A_NOT_B'),('B_IMPLIES_A',b,a,'COUNTERMODEL_B_NOT_A')]:
        if directions[key]['status']=='PROVED_ENTAILMENT':continue
        if work.models>=work.bounds['max_models']:
            directions[key]['finite_search']={'status':'UNKNOWN_BOUND','reason':'TOTAL_MODEL_BOUND','models_checked':0};continue
        bounds=work.remaining();bounds['max_models']=min(bounds['max_models'],work.bounds['max_models']-work.models)
        candidates=[{'candidate_id':left['hypothesis_ref'],'formula_ast':a,'type_status':'TYPED','signature':signature,'assumptions':[*common,x]},{'candidate_id':right['hypothesis_ref'],'formula_ast':b,'type_status':'TYPED','signature':signature,'assumptions':[{'not':y}]}]
        result=fol.countermodels(candidates,bounds);edge['formal_contrast_calls']+=1;count=result['models_checked'];edge['model_enumerations']+=count;work.models+=count;work.tick(count)
        search={k:v for k,v in result.items() if k not in ('model','candidate_ids','truth_vector','assumption_truth_vectors')};directions[key]['finite_search']=search
        if result['status']=='FINITE_COUNTERMODEL':
            model=result['model'];checks=[scenario(h,signature,model,work) for h in [left,right]];values=[c['formula_evaluation']['truth'] for c in checks]
            expected=[True,False] if label=='COUNTERMODEL_A_NOT_B' else [False,True]
            if values!=expected or not all(c['applicability']=='APPLICABLE' for c in checks):raise ValueError('COUNTERMODEL_CHECK_REJECTED')
            cm={'status':label,'model_ref':digest(model),'model':model,'model_sha256':digest(model),'origin':'FORMAL_COUNTERMODEL','truth_vector':values,'checks':checks,'comparison_scope':'ALL_CANDIDATE_ASSUMPTIONS_HOLD','execution_permission':False};edge['countermodels'].append(cm);directions[key]['status']=label
    if len(edge['countermodels'])==2:edge['status']='INCOMPARABLE_PROVED_BY_TWO_COUNTERMODELS'
    elif edge['countermodels']:edge['status']=edge['countermodels'][0]['status']
    elif any(x['status']=='PROVED_ENTAILMENT' for x in directions.values()):edge['status']='PROVED_ENTAILMENT'
    else:edge['status']='UNKNOWN_BOUND' if any(x.get('finite_search',{}).get('status')=='UNKNOWN_BOUND' for x in directions.values()) else 'FINITE_SAME_ON_BOUND'
    return edge
