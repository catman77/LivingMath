"""R9-R16 plus actual query-free worker and source evidence safeguards."""
import asyncio
from copy import deepcopy

import pytest

from artifact_genesis.source import packet_from_text
from semantic_repair.observe import observe, constraints_from_evidence
from semantic_repair.search import enumerate_bindings, generate_queries
from semantic_repair.compiler import compile_model
from semantic_repair.query import evaluate
from semantic_repair.worker import call
from semantic_repair.capability import preflight
from semantic_repair.qa import schema_limit, paginate
from semantic_repair.bundle import include_artifact


def setup(text='A implies B.\nB implies C.\n'):
    obs = observe(packet_from_text('calibration', text))
    b = enumerate_bindings(obs['dimensions'])['bindings'][0]
    m = compile_model(obs['premises'], b)
    return obs, b, m


def test_R9_rename_negation_modality_and_order():
    for text in ['A implies B.\nB implies C.\n', 'Reader implies Bell.\nBell implies Dawn.\n']:
        obs, b, m = setup(text)
        assert evaluate(m, generate_queries(obs['premises'], m)[0])['value']
    obs, _, m = setup('A implies not B.\nB implies C.\n')
    assert generate_queries(obs['premises'], m) == []
    obs, _, m = setup('A may imply B.\nB implies C.\n')
    assert generate_queries(obs['premises'], m) == []
    assert observe(packet_from_text('order', 'First A.\nThen B.\n'))['premises'] == []


def test_R10_conditional_H_and_finite_proof_do_not_become_facts():
    obs, b, m = setup()
    result = evaluate(m, generate_queries(obs['premises'], m)[0])
    assert b['status'] == 'HYPOTHESIS'
    assert result['proof_status'] == 'unverified' and result['execution_permission'] == {'allowed': False}
    assert result['source_verdict'] == 'NOT_TESTED'


def test_R11_counterexample_restricts_strong_scope_preserves_weak_H():
    full = packet_from_text('scope', 'Methods in diuers manners be doone.\nFor such work is not to our intent.\n')
    train = full.model_copy(update={'spans': full.spans[:1]})
    evidence = full.model_copy(update={'spans': full.spans[1:]})
    obs = observe(train); before = enumerate_bindings(obs['dimensions'])
    after = enumerate_bindings(obs['dimensions'], constraints_from_evidence(obs, evidence))
    assert len(before['bindings']) == 2 and len(after['bindings']) == 1
    assert list(after['bindings'][0]['assignments'].values()) == ['DESCRIPTIVE_ONLY']
    assert before['bindings'][0]['status'] == after['bindings'][0]['status'] == 'HYPOTHESIS'


def test_R12_duplicate_quote_and_same_local_relation_are_not_two_bases():
    obs = observe(packet_from_text('duplicates', 'A implies B.\nA implies B.\nA is cause of B.\n'))
    assert len(obs['premises']) == 1
    b = enumerate_bindings([])['bindings'][0]; model = compile_model(obs['premises'], b)
    assert generate_queries(obs['premises'], model) == []


def test_R13_changed_source_scope_observer_invalidates_dependent_query():
    obs, b, m = setup(); q = generate_queries(obs['premises'], m)[0]
    altered = deepcopy(obs['premises'])
    for p in altered:
        p['source_hash'] = '0' * 64
    new = compile_model(altered, b)
    with pytest.raises(ValueError, match='STALE_SOURCE'):
        evaluate(new, q)
    altered[0]['observer_version'] = 'unregistered'
    with pytest.raises(ValueError):
        compile_model(altered, b)


def test_R14_schema_bound_and_actual_pagination_contract():
    schema = {'properties': {'limit': {'maximum': 3}}}
    assert schema_limit(schema, 20) == 3
    data = [{'id': i} for i in range(7)]
    async def read_page(offset, limit):
        return {'total': len(data), 'records': data[offset:offset+limit]}
    pages = asyncio.run(paginate(read_page, schema, preferred=20))
    assert [row['id'] for row in pages] == list(range(7))


def test_R15_root_sidecars_excluded_nested_frozen_receipts_retained():
    assert include_artifact('frozen/old/final-replay-receipt.json')
    assert not include_artifact('final-replay-receipt.json')
    assert not include_artifact('final-manifest.json')
    assert not include_artifact('private-oauth.json')


def test_R16_actual_symbolic_generation_without_fake_model_usage():
    result = preflight()
    assert result['status'] == 'PASS_SYMBOLIC_CAPABILITY'
    assert len(result['generated_family']['bindings']) == 2
    assert len(result['revised_family']['bindings']) == 1
    assert result['LLM_calls'] == 0 and result['tokens'] is None
    assert result['human_review'] == 'NOT_TESTED'
    assert result['generated_queries'][0]['authorship'] == 'SYMBOLIC_SOURCEGRAPH_PATH_SEARCH'


def test_actual_compiler_process_cannot_load_or_read_query():
    obs, b, m = setup()
    answer = asyncio.run(call('compile', {'premises': obs['premises'], 'binding': b}))
    assert answer['compiled_hash'] == m['compiled_hash']
    assert answer['isolation']['probes'] == {'file': 'DENIED', 'socket': 'DENIED'}
    assert answer['isolation']['query_modules_loaded'] == []
    for extra in [{'query': True}, {'gold': True}, {'metadata': {'answer': True}}]:
        with pytest.raises(ValueError):
            asyncio.run(call('compile', {'premises': obs['premises'], 'binding': b, **extra}))


def test_assignment_constraint_other_scope_is_not_an_authority():
    dims = [{'id': 'm', 'kind': 'sense', 'mention_refs': ['a'], 'values': ['first', 'second'], 'scope': 'local'}]
    with pytest.raises(ValueError, match='CROSS_SCOPE'):
        enumerate_bindings(dims, [{'dimension': 'm', 'allowed_values': ['first'], 'scope': 'foreign', 'source_refs': ['other']}])


def test_query_already_in_local_premises_is_not_a_new_composition():
    obs, _, model = setup('A implies B.\nB implies C.\nA implies C.\n')
    assert generate_queries(obs['premises'], model) == []
