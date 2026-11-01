"""Source-audited H -> existing DAV; countermodels never confirm source meaning."""
from copy import deepcopy
from davcore.adapters import Adapter,AdapterSpec
from davcore.ast import Formula,Eq,Implies,Apply,term,implication,digest
from davcore.finite import check
from artifact_translation.network import Network


def nontriviality(adapter: Adapter,formula: Formula) -> dict:
    original=check(adapter,formula)
    conclusion=formula.body.conclusion if isinstance(formula.body,Implies) else formula.body
    empty=check(adapter,Formula(equality=formula.equality,body=conclusion))
    vacuous=empty['status']=='proved' or original['support']==0
    return {'status':'FAIL_VACUOUS_LAW' if vacuous else 'PASS_FORMAL_NONTRIVIALITY' if original['status']=='proved' else 'REFUTED',
        'with_premise':original,'without_premise':empty,'same_domain_and_semantics':True,
        'essential_premise_counterexample':empty['counterexample'],'scientific_source_success':False}


def descriptor(h: dict,mode: str) -> Network:
    roles=h['roles'][:2]
    species=[{'id':'v'+str(i),'label':r['name'][:120],'source_refs':[r['span_id']]} for i,r in enumerate(roles)]
    if mode=='joint_guard':left={'v0':1,'v1':1};right=dict(left)
    elif mode=='conditional_effect':left={'v0':1};right={'v0':1,'v1':1}
    else:left={'v0':1};right={'v1':1}
    return Network.model_validate({'species':species,'reactions':[{'id':'r0','reactants':left,'products':right,
        'source_relation_ids':[h['hypothesis_id']]}]})


def bind_and_challenge(h: dict,audit: dict,*,allow_repair: bool=True) -> dict:
    if audit.get('status')!='PROXY_SUPPORTED':raise ValueError('SOURCE_AUDIT_REQUIRED_BEFORE_TARGET_BINDING')
    old=descriptor(h,'directed_trial');a=Adapter(AdapterSpec(kind='reaction_network',reaction_network=old))
    # Probe the tempting but unjustified necessity reading before considering a transfer.
    law=implication('S0','One','S1','One');evidence=check(a,law)
    result={'hypothesis_id':h['hypothesis_id'],'audit_status':audit['status'],'old_binding':old.model_dump(),
        'probe_formula':law.canonical_ast(),'probe_evidence':evidence,'counterexample':evidence['counterexample'],
        'source_truth_established':False,'empirically_realized':'UNKNOWN','proof_status':'unverified','execution_permission':{'allowed':False}}
    result['nontriviality']=nontriviality(a,law)
    if not allow_repair:
        result.update(revision=None,effective_network=old.model_dump(),repair_enabled=False)
        return result
    if h['proposed_relation']['claim']=='joint_predication':
        new=descriptor(h,'joint_guard');revision=deepcopy(h)
        revision['counterevidence']=[{'kind':'DAV_BINDING_COUNTEREXAMPLE','witness':evidence['counterexample']}]
        revision['confidence_status']='TEXTUAL_COASSERTION_ONLY_NECESSITY_REJECTED'
        revision['target_binding']={'network':new.model_dump(),'meaning':'Joint symbolic guard; no P-implies-Q and no causal reaction asserted.'}
        revision['parent_hypothesis_id']=h['hypothesis_id'];revision['hypothesis_id']=digest(revision)
        result['revision']={'kind':'BINDING_REPAIR','old_binding':old.model_dump(),'new_binding':new.model_dump(),
            'old_H':h,'new_H':revision,'counterexample':evidence['counterexample'],
            'reason':'Co-predication was over-bound to directed necessity; retain two roles and joint observation.',
            'source_truth_established':False,'source_modified':False,'checker_modified':False}
        result['effective_network']=new.model_dump()
        repaired_formula=Formula(body=Implies(premise=Eq(left=term('E0'),right=term('One')),
            conclusion=Eq(left=Apply(operation='S1',argument=term('R0')),right=term('One'))))
        result['repaired_formal_check']=nontriviality(Adapter(AdapterSpec(kind='reaction_network',reaction_network=new)),repaired_formula)
        result['repaired_formal_check']['source_novelty']='REJECT_DIRECT_GUARD_ENCODING_AS_SCIENTIFIC_TRANSFER'
    else:
        result['revision']={'kind':'REFUSE_UNSUPPORTED_NECESSITY','counterexample':evidence['counterexample'],
                           'source_truth_established':False};result['effective_network']=old.model_dump()
    return result


def synthetic_control() -> dict:
    # Known original fixture, never evidence about a historical artifact.
    network=Network.model_validate({'species':[{'id':'a','label':'synthetic antecedent','source_refs':['synthetic-train']},
        {'id':'b','label':'synthetic consequence','source_refs':['synthetic-train']}],
        'reactions':[{'id':'r','reactants':{'a':1},'products':{'a':1,'b':1},'source_relation_ids':['synthetic-if-rule']}]})
    adapter=Adapter(AdapterSpec(kind='reaction_network',reaction_network=network))
    law=Formula(body=Implies(premise=Eq(left=term('S0'),right=term('One')),
        conclusion=Eq(left=Apply(operation='S1',argument=term('R0')),right=term('One'))))
    proof=nontriviality(adapter,law)
    return {'status':'PASS_SYNTHETIC_CALIBRATION' if proof['status']=='PASS_FORMAL_NONTRIVIALITY' else 'FAIL',
            'network':network.model_dump(),'formula':law.canonical_ast(),'evidence':proof,
            'scientific_evidence':False,'target_law_directly_encoded':True,'proof_status':'unverified','execution_permission':{'allowed':False}}
