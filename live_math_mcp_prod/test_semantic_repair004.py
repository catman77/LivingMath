"""R1-R8 on the actual repair code; authored logic fixtures are calibration only."""
from copy import deepcopy

import pytest

from artifact_genesis.source import packet_from_text
from semantic_repair.observe import observe
from semantic_repair.search import enumerate_bindings, generate_queries, summarize
from semantic_repair.compiler import compile_model
from semantic_repair.query import evaluate, deletion_witnesses


def gamma():
    return observe(packet_from_text('synthetic', 'A implies B.\nB implies C.\n'))


def dims():
    return [{'id': 'm1', 'kind': 'sense', 'mention_refs': ['s:1'], 'values': ['a', 'b'], 'scope': 'test'},
            {'id': 'm2', 'kind': 'sense', 'mention_refs': ['s:2'], 'values': ['a', 'b'], 'scope': 'test'}]


def test_R1_two_senses_four_assignments_no_confidence():
    f = enumerate_bindings(dims())
    assert len(f['bindings']) == 4
    assert f['enumeration_complete_within_family'] and not f['truncated']
    assert all('confidence' not in b and b['status'] == 'HYPOTHESIS' for b in f['bindings'])
    assert {b['assignments']['m1'] == b['assignments']['m2'] for b in f['bindings']} == {True, False}


def test_R2_assignment_witness_filters_only_applicable_values():
    a = enumerate_bindings(dims(), [{'dimension': 'm1', 'allowed_values': ['a'], 'source_refs': ['test:3'], 'scope': 'test'}])
    b = enumerate_bindings(dims(), [{'dimension': 'm1', 'allowed_values': ['b'], 'source_refs': ['test:4'], 'scope': 'test'}])
    assert len(a['bindings']) == len(b['bindings']) == 2
    assert {x['assignments']['m1'] for x in a['bindings']} == {'a'}
    assert {x['assignments']['m1'] for x in b['bindings']} == {'b'}


def test_R3_pronoun_binding_keeps_mentions_and_actor_object():
    obs = observe(packet_from_text('references', 'The pilot met the engineer.\nHe returned.\n'))
    ids = [m['id'] for m in obs['mentions']]
    family = enumerate_bindings(obs['dimensions'])
    assert len(ids) == 3 and len(set(ids)) == 3
    assert len(family['bindings']) == 2
    assert all(len(obs['mentions']) == 3 for _ in family['bindings'])


def test_R4_same_referent_different_state_is_not_coordinate_equality():
    obs = gamma(); b = enumerate_bindings([])['bindings'][0]
    one = compile_model(obs['premises'], b)
    b2 = {**b, 'assignments': {'same_referent': 'one_person'}}
    two = compile_model(obs['premises'], b2)
    assert one['coordinate_count'] == two['coordinate_count'] == 3
    assert one['spec'] == two['spec']
    mutated = deepcopy(obs['premises']); mutated[1]['src']['stage'] = 'later_state'
    assert compile_model(mutated, b)['coordinate_count'] == 4


def test_R5_essential_direct_effect_remains_definition_check():
    obs = gamma(); b = enumerate_bindings([])['bindings'][0]; m = compile_model(obs['premises'], b)
    direct = generate_queries(obs['premises'], m, include_direct=True)
    q = next(q for q in direct if len(q['premise_ids']) == 1)
    assert evaluate(m, q)['classification'] == 'DEFINITION_CHECK_ONLY'


def test_R6_two_distinct_premises_each_has_countermodel():
    obs = gamma(); b = enumerate_bindings([])['bindings'][0]; m = compile_model(obs['premises'], b)
    q = generate_queries(obs['premises'], m)[0]
    assert evaluate(m, q)['evidence']['status'] == 'proved'
    ws = deletion_witnesses(obs['premises'], b, m, q)
    assert len(ws) == 2 and all(w['evidence']['counterexample'] for w in ws)
    assert all(w['same_coordinate_contract'] for w in ws)


def test_R7_unresolved_robust_empty_truncated_and_unknown_separate():
    obs = gamma(); f = enumerate_bindings(dims()); m = compile_model(obs['premises'], f['bindings'][0]); q = generate_queries(obs['premises'], m)[0]
    outcomes = [evaluate(compile_model(obs['premises'], b), q) for b in f['bindings']]
    assert summarize(f, outcomes)['status'] == 'ROBUST_WITHIN_CANDIDATE_SET'
    cut = enumerate_bindings(dims(), bound=2)
    assert summarize(cut, outcomes[:2])['status'] == 'COMPUTATION_UNKNOWN'
    empty = enumerate_bindings(dims(), [{'dimension': 'm1', 'allowed_values': [], 'source_refs': ['test:3'], 'scope': 'test'}])
    assert summarize(empty, [])['status'] == 'INCONSISTENT_PREMISES'
    assert summarize(f, [{'status': 'RESOURCE_LIMIT'}])['status'] == 'COMPUTATION_UNKNOWN'


def test_R8_compiler_signature_rejects_query_or_gold():
    obs = gamma(); b = enumerate_bindings([])['bindings'][0]
    m = compile_model(obs['premises'], b)
    assert len(generate_queries(obs['premises'], m, include_direct=True)) >= 3
    assert compile_model(obs['premises'], b)['compiled_hash'] == m['compiled_hash']
    with pytest.raises(TypeError):
        compile_model(obs['premises'], b, query={'gold': True})
