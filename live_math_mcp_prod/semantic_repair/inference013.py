"""Fixed conditional observer checks after source/model freeze, using existing DAV.

No source-truth checker, expression language, new adapter or executable command.
"""
from copy import deepcopy
from itertools import combinations

from davcore.adapters import Adapter, AdapterSpec
from davcore.ast import digest, eq, implication
from davcore.finite import Meter, witness
from davcore.models import Budget

from .reference013 import enumerate_reference

ADOPT = 'ADOPT_ADDRESSED_VALUE_RECORDS_NOT_WORLD_FACTS'
ALIAS = 'COMMON_FEATURE_REFERENT_BINDING'
MEANING = 'COMMON_COMPARISON_MEANING_AND_SCOPE'


def _binding(profile, pair):
    samples={s['state_key']:s for s in profile['samples']}
    missing=[]
    for field in ('scope','time'):
        values=[samples.get(s,{}).get(field) for s in pair]
        if values[0] is None or values[0]!=values[1]:missing.append({'observer_id':profile['id'],'field':field,'values':values,'states':pair})
    for state in pair:
        if samples.get(state,{}).get('referent') is None:
            missing.append({'observer_id':profile['id'],'field':'referent','state':state,'reason':'UNBOUND_SAMPLE_REFERENCE'})
    return missing


def _plan(profiles, pair, shared):
    variables=[];domains={};constraints=[];projections=[];locations={};conflicts=[]
    for p in profiles:
        samples={s['state_key']:s for s in p['samples']}
        projection=[]
        for f in p['features']:
            ends=[]
            for state in pair:
                key='cell_'+digest(['shared' if shared else p['id'],state,f])[:32]
                if key not in domains:variables.append(key);domains[key]=[]
                cell=samples.get(state,{}).get('values',{}).get(f,{'status':'UNKNOWN','value':None,'addresses':[]})
                locations.setdefault(key,[]).append({'observer_id':p['id'],'state_key':state,'feature':f,
                    'time':samples.get(state,{}).get('time'),'scope':samples.get(state,{}).get('scope'),
                    'referent':samples.get(state,{}).get('referent'),'source_addresses':cell.get('addresses',[])})
                if cell['status']=='CONFLICT':conflicts.append({'observer_id':p['id'],'state_key':state,'feature':f,'evidence':cell.get('conflicts',[])})
                if cell['status'] in {'KNOWN','EXPLICIT_NEGATIVE'} and p['source_status']=='HYPOTHESIS':
                    constraints.append({'id':'basis_'+digest([p['id'],state,f,cell])[:20],'key':key,'value':cell['value'],
                        'negative':cell['status']=='EXPLICIT_NEGATIVE','source_addresses':cell.get('addresses',[])})
                ends.append(key)
            projection.append(ends)
        projections.append(projection)
    # Two explicitly non-source representatives preserve both equal/unequal
    # completions of missing values. They are witness symbols, never observations.
    for key in variables:
        feature=locations[key][0]['feature']
        known=sorted({c['value'] for c in constraints if locations[c['key']][0]['feature']==feature})
        domains[key]=[('SOURCE_VALUE',v) for v in known]+[('UNOBSERVED_ALTERNATIVE',0),('UNOBSERVED_ALTERNATIVE',1)]
    for c in constraints:c['value']=('SOURCE_VALUE',c['value'])
    return {'variables':variables,'domains':domains,'constraints':constraints,'projections':projections,
        'locations':locations,'conflicts':conflicts}


def _primary(plan, limit):
    options={}
    for key in plan['variables']:
        allowed=set(plan['domains'][key])
        for c in plan['constraints']:
            if c['key']==key:allowed=allowed-{c['value']} if c['negative'] else allowed & {c['value']}
        options[key]=sorted(allowed,key=repr)
    count=1
    for xs in options.values():count*=len(xs)
    if count>limit:return {'status':'RESOURCE_BOUND','world_count':count,'rows':[]}
    rows=[]
    def visit(i,world):
        if i==len(plan['variables']):
            truths=[all(world[left]==world[right] for left,right in projection) and bool(projection) for projection in plan['projections']]
            rows.append({'world':world.copy(),'truth':truths});return
        key=plan['variables'][i]
        for x in options[key]:world[key]=x;visit(i+1,world)
    visit(0,{})
    return {'status':'COMPLETE','world_count':count,'rows':rows}


def _enumerate(plan,limit):
    a=_primary(plan,limit);b=enumerate_reference(plan,limit)
    def normalize(r):return sorted((tuple(sorted(x['world'].items())),tuple(x['truth'])) for x in r['rows'])
    if a['status']!=b['status'] or a['world_count']!=b['world_count'] or normalize(a)!=normalize(b):
        raise ValueError('OBSERVER013_INDEPENDENT_ENUMERATOR_DISAGREEMENT')
    return a


def _dav(rows, kind):
    a=Adapter(AdapterSpec(kind='gate6'))
    formula=eq('P','One') if kind=='OBSERVATIONAL_EQUALITY' else implication('P','One','Q','One')
    signatures=sorted({int(r['truth'][0])+(2*int(r['truth'][1]) if len(r['truth'])>1 else 0) for r in rows})
    vectors=[];meter=Meter(Budget())
    for state in signatures:
        w=witness(a,formula,state,meter)
        expected=bool(state & 1) if kind=='OBSERVATIONAL_EQUALITY' else not bool(state & 1) or bool(state & 2)
        if w['actual_relation']!=expected:raise ValueError('OBSERVER013_DAV_VECTOR_DISAGREEMENT')
        vectors.append({'marking':state,'actual_relation':w['actual_relation']})
    return formula.canonical_ast(),vectors


def _missing(plan, rows, kind):
    """Minimum coordinate observations separating all opposed finite completions."""
    fixed={c['key'] for c in plan['constraints'] if not c['negative']}
    keys=[k for k in plan['variables'] if k not in fixed]
    def truth(r):return r['truth'][0] if kind=='OBSERVATIONAL_EQUALITY' else not r['truth'][0] or r['truth'][1]
    yes=[r for r in rows if truth(r)];no=[r for r in rows if not truth(r)]
    if len(yes)*len(no)>65536:return [],'RESOURCE_BOUND_MINIMAL_OBLIGATION_SEARCH'
    differences={frozenset(k for k in keys if x['world'][k]!=y['world'][k]) for x in yes for y in no}
    for size in range(len(keys)+1):
        for chosen in combinations(keys,size):
            if all(set(chosen)&s for s in differences):
                return [plan['locations'][k][0] for k in chosen],'EXACT_MINIMUM_IN_DECLARED_FINITE_COMPLETIONS'
    return [],'NO_OBSERVATION_ONLY_RESOLUTION'


def _question(profiles,pair,model,kind,limit):
    shared=kind=='PROJECTION_IMPLICATION'
    plan=_plan(profiles,pair,shared);result=_enumerate(plan,limit)
    assumptions=[ADOPT]+([ALIAS] if shared else [])
    base={'kind':kind,'observers':[o['id'] for o in profiles],'states':list(pair),'assumptions':assumptions,
        'model_hash':model['compiled_hash'],'source_sha256':model['source_hashes'][0],
        'source_supports':'ADDRESSED_HYPOTHESIS_RECORDS_ONLY; NOT_THE_DERIVED_WORLD_CLAIM',
        'world_truth':'UNKNOWN','source_verified':False,'full_state_identity_inferred':False,
        'check_scope':'ALL_DECLARED_FINITE_VALUE_COMPLETIONS; OBSERVER_PROJECTIONS_ONLY',
        'quantifier_scope':'ONLY_NAMED_SAMPLES; NO_ALL_FROM_SOME_OR_POPULATION_LIFT',
        'source_basis':plan['constraints'],'missing_bindings':[x for p in profiles for x in _binding(p,pair)],
        'missing_observations':[],'essential_basis_ablations':[],'nonessential_basis_ablations':[],'unresolved_basis_ablations':[],
        'necessity_check_status':'NOT_RUN',
        'witness':None,'counterexample':None,'nonvacuous_premise':False,
        'finite_domain':{'variables':plan['variables'],'values':plan['domains'],'world_count':result['world_count'],
            'unobserved_values_are_witness_symbols_not_source':True,'enumeration_status':result['status']},'independent_agreement':True}
    if shared:
        # Different samples are precisely what Eq_O compares. Referential
        # alignment is PER STATE across observers, never identity of s and t.
        for state in pair:
            for field in ('time','referent'):
                xs=[next((s.get(field) for s in p['samples'] if s['state_key']==state),None) for p in profiles]
                if xs[0] is None or len(set(xs))!=1:base['missing_bindings'].append({'field':field,'state':state,'observers':base['observers'],'values':xs})
        base['interpretation_binding'] = {'common_scope_and_feature_meaning': 'EXPLICIT_CONDITIONAL_ALIAS_ASSUMPTION_NOT_SOURCE_FACT',
            'observer_scopes': [[s.get('scope') for s in p['samples'] if s['state_key'] in pair] for p in profiles],
            'different_sample_referents_need_not_be_identical': True}
    if plan['conflicts']:
        base.update(verdict='CONFLICTING_REPORTS',conflicting_assignments=plan['conflicts']);return base
    if base['missing_bindings']:
        if result['status'] == 'COMPLETE' and result['rows']:
            missing, scope = _missing(plan, result['rows'], kind)
            base.update(missing_observations=missing, minimal_obligation_scope=scope + '; ADDITIONALLY_RESOLVE_BINDINGS')
        base.update(verdict='UNKNOWN_INSUFFICIENT_OBSERVATION',reason='TIME_SCOPE_OR_REFERENT_NOT_COMPARABLE');return base
    if result['status']=='RESOURCE_BOUND':base.update(verdict='RESOURCE_BOUND');return base
    rows=result['rows']
    if not rows:base.update(verdict='INCONSISTENT_ASSUMPTIONS',reason='NO_COMPLETION_OF_ADOPTED_VALUE_RECORDS');return base
    formula,vectors=_dav(rows,kind);base.update(dav_formula=formula,dav_truth_vector=vectors)
    def holds(row):return row['truth'][0] if not shared else not row['truth'][0] or row['truth'][1]
    yes=[r for r in rows if holds(r)];no=[r for r in rows if not holds(r)]
    support=rows if not shared else [r for r in rows if r['truth'][0]]
    base.update(witness=yes[0] if yes else None,counterexample=no[0] if no else None,nonvacuous_premise=bool(support),
        world_truth_vector_sha256=digest(sorted(tuple(r['truth']) for r in rows)))
    if not support:base.update(verdict='UNKNOWN_INSUFFICIENT_OBSERVATION',reason='VACUOUS_PREMISE_NOT_CREDITED')
    elif not no:base.update(verdict='ENTAILED_UNDER_ASSUMPTIONS', equality_scope='EXACTLY_DECLARED_NAMED_FEATURE_MASK; NOT_COMPLETE_IDENTITY')
    elif not yes:base.update(verdict='REFUTED_UNDER_ASSUMPTIONS')
    else:
        missing,scope=_missing(plan,rows,kind)
        base.update(verdict='UNKNOWN_INSUFFICIENT_OBSERVATION',missing_observations=missing,minimal_obligation_scope=scope)
    for c in plan['constraints']:
        altered=deepcopy(plan);altered['constraints']=[v for v in altered['constraints'] if v['id']!=c['id']]
        other=_enumerate(altered,limit)
        changed=next((r for r in other['rows'] if holds(r)!=(not no)),None) if base['verdict'] in {'ENTAILED_UNDER_ASSUMPTIONS','REFUTED_UNDER_ASSUMPTIONS'} else None
        row={'removed_basis':c['id'],'counterexample':changed,'independent_agreement':True,
            'scope':'Adoption withdrawn, original source record retained','resource_bound':other['status']=='RESOURCE_BOUND'}
        base['unresolved_basis_ablations' if row['resource_bound'] else 'essential_basis_ablations' if changed else 'nonessential_basis_ablations'].append(row)
    if shared and base['verdict']=='ENTAILED_UNDER_ASSUMPTIONS':
        altered=_plan(profiles,pair,False);other=_enumerate(altered,limit)
        counter=next((r for r in other['rows'] if r['truth'][0] and not r['truth'][1]),None)
        target='unresolved_basis_ablations' if other['status']=='RESOURCE_BOUND' else 'essential_basis_ablations' if counter else 'nonessential_basis_ablations'
        base[target].append({'removed_basis':ALIAS,'counterexample':counter,'independent_agreement':True,
            'reason':'Separate observer coordinates permit distinction' if counter else 'RESOURCE_BOUND_NOT_A_PROOF_OF_SAME_PROJECTION' if other['status']=='RESOURCE_BOUND' else 'Already assigned records determine the same projection',
            'resource_bound':other['status']=='RESOURCE_BOUND'})
    base['necessity_check_status'] = 'RESOURCE_BOUND' if base['unresolved_basis_ablations'] else 'COMPLETE_IN_DECLARED_FINITE_DOMAIN'
    return base


def _reports(reports,model):
    out=[]
    for a,b in combinations(reports,2):
        if {a['source'],a['target']}!={b['source'],b['target']}:continue
        if a['comparison']=='UNSPECIFIED' or b['comparison']=='UNSPECIFIED':continue
        if 'UNKNOWN' in (a['reported_value'],b['reported_value']):continue
        expected=[a['reported_value']=='TRUE',b['reported_value']=='TRUE']
        independent=[{'P':bool(s&1),'Q':bool(s&2)} for s in range(4)]
        concrete=next(w for w in independent if [w['P'],w['Q']]==expected)
        base={'kind':'REPORT_COMPATIBILITY','reports':[a['id'],b['id']],'source_addresses':a['addresses']+b['addresses'],
            'model_hash':model['compiled_hash'],'assumptions':[],'world_truth':'UNKNOWN','source_verified':False,
            'source_supports':'REPORT_EVENTS_ONLY; CONTENTS_NOT_AXIOMS', 'verdict':'ASSERTED_BY_SOURCE_ONLY',
            'witness':concrete,'counterexample_without_assumption':concrete}
        out.append(base)
        common=[w for w in independent if w['P']==w['Q']]
        joint=[w for w in common if [w['P'],w['Q']]==expected]
        formula,vectors=_dav([{'truth':[w['P'],w['Q']]} for w in common],'PROJECTION_IMPLICATION')
        out.append({**base,'assumptions':[MEANING],'verdict':'COMPATIBLE_ONLY' if joint else 'CONFLICTING_REPORTS',
            'witness':joint[0] if joint else None,'counterexample_without_assumption':concrete,
            'finite_domain':{'admissible_gate6_markings':[0,3],'enumerated_full_boolean_domain':[0,1,2,3]},
            'dav_formula':formula,'dav_truth_vector':vectors,'independent_agreement':True,
            'adopt_all_report_contents':False,'inconsistent_world_claim':False,
            'hypothetical_common_meaning_not_established_by_source':True,
            'interpretation_binding':{'P_report':a,'Q_report':b,'additional_assumption':'The two signed comparisons denote one predicate in one common scope/time'},
            'reason':'Report contents can disagree only under the displayed common interpretation; neither speaker is declared factually right'})
    return out


def analyze(model: dict, *, max_worlds: int=4096) -> dict:
    if not 1<=max_worlds<=4096:raise ValueError('OBSERVER013_FINITE_BOUND')
    info=model['observer']['inference']
    if info['version']!='observer-inference013/1' or info['source_sha256'] not in model['source_hashes']:
        raise ValueError('STALE_OBSERVER013_SOURCE_BINDING')
    profiles=info['profiles'];reports=info['reports']
    pairs={tuple(sorted({a['source'],a['target']})) for a in reports if a['source']!=a['target']}
    pairs.update(tuple(pair) for p in profiles for pair in combinations(sorted({s['state_key'] for s in p['samples']}),2))
    results=[]
    for pair in sorted(pairs):
        for p in profiles:
            results.append(_question([p],pair,model,'OBSERVATIONAL_EQUALITY',max_worlds))
        for a,b in combinations(profiles,2):
            results.append(_question([a,b],pair,model,'PROJECTION_IMPLICATION',max_worlds))
            results.append(_question([b,a],pair,model,'PROJECTION_IMPLICATION',max_worlds))
        if len(results)>24:
            results=[{'kind':'QUESTION_FAMILY','verdict':'RESOURCE_BOUND','reason':'MORE_THAN_24_QUESTIONS','source_verified':False}];break
    results+=_reports(reports,model)
    for row in results:row['id']='inference_'+digest([model['compiled_hash'],row])[:24]
    return {'version':'observer-inference013/1','model_hash':model['compiled_hash'],'consequences':results,
        'independent_enumeration_agrees':True,'query_generation':'AFTER_SOURCE_AND_MODEL_FREEZE',
        'source_assertions_represented':len(reports),'conditional_consequences':sum(q['verdict']=='ENTAILED_UNDER_ASSUMPTIONS' for q in results),
        'independent_source_validations':0,'full_state_identity_inferred':False,'source_verified':False,
        'proof_status':'unverified','execution_permission':{'allowed':False}}
