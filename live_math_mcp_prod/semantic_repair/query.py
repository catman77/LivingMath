"""Existing DAV exact finite executor; actual dependency deletion in the same contract."""
from davcore.adapters import Adapter, AdapterSpec
from davcore.ast import Formula, digest
from davcore.finite import check
from artifact_translation.checker import independent_verdict
from artifact_translation.network import Network
from .compiler import compile_model


def evaluate(model: dict, query: dict) -> dict:
    if model['status'] != 'COMPILED_CONDITIONAL_MODEL':
        return {'status': 'RESOURCE_LIMIT', 'reason': model['status']}
    if query['coordinate_contract_hash'] != digest([model['coordinates'], model['source_hashes'], model['observer']]):
        raise ValueError('STALE_SOURCE_SCOPE_OBSERVER_OR_COORDINATES')
    formula = Formula.model_validate(query['formula'])
    spec = AdapterSpec.model_validate(model['spec'])
    evidence = check(Adapter(spec), formula)
    if evidence['status'] not in {'proved', 'refuted'}:
        return {'status': 'RESOURCE_LIMIT', 'reason': evidence['reason'], 'evidence': evidence}
    reference = independent_verdict(Network.model_validate(model['spec']['reaction_network']), formula)
    if reference['status'] != evidence['status']:
        raise ValueError('INDEPENDENT_STOICHIOMETRY_DISAGREES')
    units = {n['premise_unit'] for n in query['dependency_DAG']}
    return {'status': 'CHECKED', 'value': evidence['status'] == 'proved', 'evidence': evidence,
            'query_id': query['query_id'], 'compiled_hash': model['compiled_hash'],
            'classification': 'DEFINITION_CHECK_ONLY' if len(units) < 2 else 'MULTI_PREMISE_CONDITIONAL',
            'independent': reference, 'proof_status': 'unverified', 'source_verdict': 'NOT_TESTED',
            'execution_permission': {'allowed': False}}


def deletion_witnesses(premises: list[dict], binding: dict, model: dict, query: dict) -> list[dict]:
    out = []
    for pid in query['premise_ids']:
        reduced = compile_model(premises, binding, disabled=(pid,))
        result = evaluate(reduced, query)
        out.append({'deleted_premise': pid, 'same_coordinate_contract': reduced['coordinates'] == model['coordinates'],
                    'deletion_operation': 'Replace this premise command with identity; retain operation IDs and all states.',
                    'evidence': result['evidence'], 'essential': result['value'] is False,
                    'source_assumption_retracted': pid})
    return out


def target_contract(claim, premises: list[dict], binding: dict, model: dict, query: dict) -> dict:
    from .search import generate_queries
    compiled=compile_model(premises,binding)
    if compiled['compiled_hash']!=model['compiled_hash'] or compiled.get('spec')!=model.get('spec'):
        raise ValueError('MODEL_OR_PREMISE_BINDING_DRIFT')
    if query not in generate_queries(premises,compiled,include_direct=True):
        # A multi-step query can be excluded as a direct primitive restatement;
        # check the actual generator's ordinary compound contract separately.
        if query not in generate_queries(premises,compiled):raise ValueError('QUERY_FORMULA_OR_ID_DRIFT')
    if (claim.subject,claim.object)!=(query['src_predicate'],query['dst_predicate']):
        raise ValueError('SOURCE_TARGET_ENDPOINT_MAP_DRIFT')
    if claim.source_hash not in compiled['source_hashes'] or claim.scope!=query['dependency_DAG'][0]['scope']:
        raise ValueError('SOURCE_TARGET_NAMESPACE_DRIFT')
    body={'version':'source-target007/1','claim_id':claim.identity(),'query_id':query['query_id'],
        'query':query,'model_hash':compiled['compiled_hash'],'model_spec_hash':digest(compiled['spec']),
        'premises_sha256':digest(premises),'binding_sha256':digest(binding),
        'source_to_target':{'subject':claim.subject,'object':claim.object,
            'roles':{k:getattr(claim,k) for k in ['participant','stimulus_participant','recipient','direction']},
            'role_projection':'SOURCE_ONLY_NOT_TARGET_REALIZED','loss':'Predicate coordinates do not realize entity identity or human role interpretation.'}}
    return {**body,'contract_sha256':digest(body)}


def verify_target_contract(contract: dict, expected_sha: str, claim, premises: list[dict], binding: dict, model: dict) -> dict:
    body={k:v for k,v in contract.items() if k!='contract_sha256'}
    if digest(body)!=expected_sha or contract.get('contract_sha256')!=expected_sha:
        raise ValueError('SEALED_SOURCE_TARGET_CONTRACT_DRIFT')
    actual=target_contract(claim,premises,binding,model,contract['query'])
    if actual!=contract:raise ValueError('SOURCE_TARGET_DEPENDENCY_DRIFT')
    evidence=evaluate(model,contract['query'])
    return {'target_query_verified':True,'contract_sha256':expected_sha,'model_law':evidence,
        'source_claim_verified_by_target':False,'proof_status':'unverified','execution_permission':{'allowed':False}}
