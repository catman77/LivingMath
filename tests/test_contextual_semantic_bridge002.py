"""PATCH002 mathematical and scheduling regressions on the real contextual engine."""
import copy
import json
from itertools import permutations
from pathlib import Path

import pytest

from lm_suti_assurance.core import digest
from lm_suti_assurance.semantic_bridge.contextual.checker import check_certificate
from lm_suti_assurance.semantic_bridge.contextual.engine import analyze, register
from lm_suti_assurance.semantic_bridge.contextual.relations import prove_entailment

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / 'docs/SEMANTIC_BRIDGE_PATCH002_20261109/fixtures/PATCH002_CASES.json').read_text())
CASES = {c['id']: c for c in FIXTURE['logical_cases']}


def batch_for(case, extra=None):
    text = case.get('source', 'Original synthetic PATCH002 source.')
    source = {'text_utf8': text, 'sha256': __import__('hashlib').sha256(text.encode()).hexdigest(),
              'spans': [], 'context_refs': [], 'rights': 'Original synthetic test, permission granted.'}
    link = {'byte_utf8': [0, len(text.encode())], 'literal': text}
    formulas = {**case['formulas'], **(extra or {})}
    args = {'source_ref': digest(source), 'expected_source_sha256': source['sha256'],
            'target_signature': case['signature'], 'hypotheses': [
                {'client_id': name, 'language': 'FOL_V1', 'formula_ast': phi, 'assumptions': [],
                 'source_links': [link], 'construction_trace': [{'origin': 'frozen synthetic external fixture'}],
                 'obligations': []} for name, phi in formulas.items()]}
    return register({'arguments': args, 'source': source})


def run_case(case, pairs, budget=32, extra=None):
    batch = batch_for(case, extra)
    refs = batch['hypothesis_refs']
    return analyze({'batch': batch, 'pairs': [[refs[a], refs[b]] for a, b in pairs], 'models': [],
                    'budget': {'max_models': budget}})


@pytest.mark.parametrize('names', [('HmsgE', 'Hskeleton'), ('HmsgBoth', 'HmsgE')])
def test_existential_projection_has_exact_certificate_and_zero_search(names):
    c = CASES['T4_existence_projection']
    a, b = [c['formulas'][n] for n in names]
    p = prove_entailment(a, b, c['signature'])
    assert p['status'] == 'PROVED_ENTAILMENT'
    assert p['model_enumerations'] == 0
    assert p['certificate']['prefix_quantifiers_and_sorts'] == [['exists', 'engineer'], ['exists', 'analyst']]
    assert check_certificate(a, b, c['signature'], p['certificate'])


@pytest.mark.parametrize('prefix', [('forall', 'exists'), ('exists', 'forall'), ('exists', 'exists')])
def test_same_mixed_prefix_is_monotone(prefix):
    c = copy.deepcopy(CASES['T4_existence_projection'])
    a, b = [copy.deepcopy(c['formulas'][n]) for n in ['HmsgE', 'Hskeleton']]
    for p in [a, b]: p['quant'], p['body']['quant'] = prefix
    proof = prove_entailment(a, b, c['signature'])
    assert proof['status'] == 'PROVED_ENTAILMENT'
    assert check_certificate(a, b, c['signature'], proof['certificate'])


@pytest.mark.parametrize('case', ['T2_quantifier_negation', 'boolean_commutativity'])
def test_both_proofs_aggregate_as_logical_equality(case):
    c = CASES[case]
    names = ['not_all', 'exists_not'] if case.startswith('T2') else ['A', 'B']
    result = run_case(c, [names])
    edge = result['graph']['relations'][0]
    assert edge['status'] == 'PROVED_LOGICAL_EQ'
    assert result['checks']['model_enumerations'] == 0
    assert all(x['status'] == 'PROVED_ENTAILMENT' for x in edge['directions'].values())
    assert result['checks']['directional_coverage'] == {'requested': 2, 'completed': 2, 'undecided': 0}


@pytest.mark.parametrize('swapped', [False, True])
def test_projection_reverse_counterexample_cannot_starve(swapped):
    c = CASES['T4_existence_projection']
    names = ['HmsgE', 'Hskeleton']
    if swapped: names.reverse()
    result = run_case(c, [names])
    edge = result['graph']['relations'][0]
    proved = edge['directions']['B_IMPLIES_A' if swapped else 'A_IMPLIES_B']
    refuted = edge['directions']['A_IMPLIES_B' if swapped else 'B_IMPLIES_A']
    assert proved['status'] == 'PROVED_ENTAILMENT' and proved['models_checked'] == 0
    assert refuted['status'].startswith('COUNTERMODEL_') and 0 < refuted['models_checked'] <= 32
    assert edge['status'] == 'PROVED_ENTAILMENT' and len(edge['countermodels']) == 1


def test_all_pair_permutations_share_models_and_preserve_two_proofs_two_failures():
    c = CASES['T4_existence_projection']
    pairs = [['HmsgE', 'Hskeleton'], ['HmsgBoth', 'HmsgE'], ['HmsgE', 'HmsgA']]
    expected = None
    for order in permutations(pairs):
        result = run_case(c, order)
        observed = {}
        for e in result['graph']['relations']:
            observed[tuple(e['client_ids'])] = (e['status'], e['model_enumerations'],
                [(d['status'], d['models_checked']) for d in e['directions'].values()],
                [(cm['status'], cm['model_sha256']) for cm in e['countermodels']])
        if expected is None: expected = observed
        assert observed == expected
        assert result['checks']['model_enumerations'] <= 32
        assert result['checks']['directional_coverage']['completed'] == 6


def test_finite_exhaustion_is_not_universal_equivalence():
    c = CASES['T3_forall_distributivity_trap']
    result = run_case(c, [['per', 'global']], budget=32)
    edge = result['graph']['relations'][0]
    assert edge['directions']['A_IMPLIES_B']['status'] == 'COUNTERMODEL_A_NOT_B'
    reverse = edge['directions']['B_IMPLIES_A']
    assert reverse['status'] == 'NO_COUNTERMODEL_WITHIN_BOUND'
    assert reverse['halt_reason'] == 'FINITE_EXHAUSTED'
    assert result['status'] == 'CHECKED_WITH_OPEN_DIRECTIONS'
    assert result['checks']['directional_coverage']['undecided'] == 1


def test_shared_assumptions_exclude_out_of_scope_worlds():
    c = CASES['T4_existence_projection']
    batch = batch_for(c)
    for h in batch['hypotheses']:
        if h['client_id'] == 'Hskeleton': h['assumptions'] = [c['formulas']['HmsgE']]
    refs = batch['hypothesis_refs']
    result = analyze({'batch': batch, 'pairs': [[refs['HmsgE'], refs['Hskeleton']]], 'models': [], 'budget': {'max_models': 32}})
    edge = result['graph']['relations'][0]
    assert not edge['countermodels'] and edge['directions']['B_IMPLIES_A']['status'] == 'UNKNOWN_BOUND'
    assert edge['directions']['A_IMPLIES_B']['status'] == 'PROVED_ENTAILMENT'
    assert result['status'] == 'CHECKED_WITH_OPEN_DIRECTIONS'


@pytest.mark.parametrize('field', ['prefix', 'rows', 'atom_type', 'signature', 'input'])
def test_forged_mixed_prefix_certificate_rejected(field):
    c = CASES['T4_existence_projection']; a, b = [c['formulas'][n] for n in ['HmsgE', 'Hskeleton']]
    cert = copy.deepcopy(prove_entailment(a, b, c['signature'])['certificate'])
    if field == 'prefix': cert['prefix_quantifiers_and_sorts'][0][0] = 'forall'
    elif field == 'rows': cert['rows_checked'] += 1
    elif field == 'signature': cert['signature_sha256'] = '0' * 64
    elif field == 'input': cert['input_formula_sha256_left'] = '0' * 64
    else: cert['atoms'][0][-1][0] = False
    assert not check_certificate(a, b, c['signature'], cert)


def test_nnf_certificate_and_semantically_wrong_quantifier_are_distinct():
    c = CASES['T2_quantifier_negation']; a, b = [c['formulas'][n] for n in ['not_all', 'exists_not']]
    p = prove_entailment(a, b, c['signature']); cert = p['certificate']
    assert cert['rule'] == 'NEGATION_NORMAL_FORM_EQUIVALENCE'
    assert check_certificate(a, b, c['signature'], cert)
    bad = copy.deepcopy(b); bad['quant'] = 'forall'
    assert not check_certificate(a, bad, c['signature'], cert)
    assert prove_entailment(a, bad, c['signature'])['status'] != 'PROVED_ENTAILMENT'


@pytest.mark.parametrize('budget', [32, 64])
def test_heavy_pair_cannot_consume_cheap_pair_budget(budget):
    c = CASES['T4_existence_projection']
    a = copy.deepcopy(c['formulas']['Hskeleton'])
    a['quant'] = 'forall'
    # Same two variables with reversed quantifier order, not just changed quantifier kinds.
    b = {'quant': 'exists', 'var': a['body']['var'], 'sort': a['body']['sort'],
         'body': {'quant': 'forall', 'var': a['var'], 'sort': a['sort'], 'body': copy.deepcopy(a['body']['body'])}}
    extra = {'HeavyA': a, 'HeavyB': b}
    pairs = [['HeavyA', 'HeavyB'], ['HmsgE', 'Hskeleton'], ['HmsgBoth', 'HmsgE']]
    first = run_case(c, pairs, budget, extra)
    second = run_case(c, [list(reversed(p)) for p in reversed(pairs)], budget, extra)
    def normalized(result):
        found = {}
        for edge in result['graph']['relations']:
            a, b = edge['client_ids']
            for key, x, y in [('A_IMPLIES_B', a, b), ('B_IMPLIES_A', b, a)]:
                d = edge['directions'][key]
                status = 'COUNTERMODEL' if d['status'] in ('COUNTERMODEL_A_NOT_B', 'COUNTERMODEL_B_NOT_A') else d['status']
                found[x, y] = (status, d['models_checked'], d['counterexample_ref'])
        return found
    assert normalized(first) == normalized(second)
    assert first['checks']['model_enumerations'] == budget
    assert first['status'] == 'CHECKED_WITH_OPEN_DIRECTIONS'
    assert first['checks']['directional_coverage']['undecided'] > 0
    for edge in first['graph']['relations'][1:]:
        assert edge['summary']['completed'] == 2
        assert sorted(d['models_checked'] for d in edge['directions'].values())[0] == 0
        assert len(edge['countermodels']) == 1


def test_cell_bound_preserves_already_found_proof_and_counterexample():
    sig = {'sorts': ['s'], 'predicates': {name: ['s', 's', 's'] for name in ['P', 'Q', 'R']}}
    p = {'pred': 'P', 'args': [{'var': 'x'}] * 3}
    q = {'pred': 'Q', 'args': [{'var': 'x'}] * 3}
    quant = lambda kind, body: {'quant': kind, 'var': 'x', 'sort': 's', 'body': body}
    case = {'signature': sig, 'formulas': {'All': quant('forall', p), 'Some': quant('exists', p),
            'Both': quant('exists', {'and': [p, q]}), 'P': quant('exists', p)}}
    result = run_case(case, [['All', 'Some'], ['Both', 'P']], 64)
    heavy, cheap = result['graph']['relations']
    assert all(d['status'] == 'UNKNOWN_BOUND' and d['halt_reason'] == 'RELATION_CELL_BOUND' for d in heavy['directions'].values())
    assert cheap['summary']['completed'] == 2 and len(cheap['countermodels']) == 1
    assert result['checks']['model_enumerations'] == 8


@pytest.mark.parametrize('kind', ['double_not', 'de_morgan', 'not_exists'])
def test_nnf_quantifier_negation_and_boolean_rules(kind):
    sig = {'sorts': ['s'], 'predicates': {'P': ['s'], 'Q': ['s']}}
    p = {'pred': 'P', 'args': [{'var': 'x'}]}
    q = {'pred': 'Q', 'args': [{'var': 'x'}]}
    quant = lambda quantifier, body: {'quant': quantifier, 'var': 'x', 'sort': 's', 'body': body}
    if kind == 'double_not':
        a, b = {'not': {'not': quant('forall', p)}}, quant('forall', p)
    elif kind == 'de_morgan':
        a, b = quant('forall', {'not': {'and': [p, q]}}), quant('forall', {'or': [{'not': p}, {'not': q}]})
    else:
        a, b = {'not': quant('exists', p)}, quant('forall', {'not': p})
    proof = prove_entailment(a, b, sig)
    assert proof['status'] == 'PROVED_ENTAILMENT'
    assert proof['certificate']['rule'] == 'NEGATION_NORMAL_FORM_EQUIVALENCE'
    assert check_certificate(a, b, sig, proof['certificate'])
    for field in ['normal_sha256_left', 'normal_sha256_right']:
        bad = copy.deepcopy(proof['certificate']); bad[field] = '0' * 64
        assert not check_certificate(a, b, sig, bad)


def test_ill_typed_assumption_never_reaches_countermodel_search():
    c = CASES['T4_existence_projection']; batch = batch_for(c)
    batch['hypotheses'][0]['type_status'] = 'TYPE_REJECTED'
    refs = batch['hypothesis_refs']
    result = analyze({'batch': batch, 'pairs': [[refs['HmsgE'], refs['Hskeleton']]], 'models': [], 'budget': {}})
    assert result['graph']['relations'][0]['status'] == 'TYPE_REJECTED'
    assert result['checks']['model_enumerations'] == 0
    assert result['checks']['directional_coverage']['undecided'] == 2


@pytest.mark.parametrize('attack', ['none', 'proof', 'countermodel', 'coverage'])
def test_stdlib_verifier_rejects_forged_evidence_even_with_rehashed_bundle(attack):
    import runpy
    verify = runpy.run_path(str(ROOT / 'tools/semantic_bridge002_verify.py'))['verify_bundle']
    case = CASES['T4_existence_projection']; batch = batch_for(case); refs = batch['hypothesis_refs']
    payload = {'batch': batch, 'pairs': [[refs['HmsgE'], refs['Hskeleton']]], 'models': [], 'budget': {'max_models': 32}}
    result = analyze(payload); packet = {'operation': 'analyze', 'payload': payload}
    if attack == 'proof':
        cert = result['graph']['relations'][0]['directions']['A_IMPLIES_B']['certificate']
        cert['prefix_quantifiers_and_sorts'][0][0] = 'forall'
    elif attack == 'countermodel':
        cm = result['graph']['relations'][0]['countermodels'][0]
        cm['model']['relations']['Said'] = []
        cm['model_ref'] = cm['model_sha256'] = digest(cm['model'])
        result['graph']['relations'][0]['directions']['B_IMPLIES_A']['counterexample_ref'] = cm['model_ref']
    elif attack == 'coverage': result['checks']['directional_coverage']['completed'] = 0
    bundle = {'schema': 'semantic-bridge-replay-bundle/1', 'operation': 'analyze', 'packet': packet,
              'packet_sha256': digest(packet), 'result': result, 'result_sha256': digest(result)}
    if attack == 'none': assert verify(bundle)['status'] == 'PASS'
    else:
        with pytest.raises((AssertionError, StopIteration)): verify(bundle)


@pytest.mark.parametrize('budget', [32, 64])
def test_cost_heavy_formula_loses_only_its_local_fuel_not_other_pairs(budget):
    sig = {'sorts': ['s'], 'predicates': {'P': ['s'], 'Q': ['s']}}
    p = {'pred': 'P', 'args': [{'var': 'x0'}]}; q = {'pred': 'Q', 'args': [{'var': 'x0'}]}
    per = {'quant': 'forall', 'var': 'x0', 'sort': 's', 'body': {'or': [p, q]}}
    global_ = {'or': [{'quant': 'forall', 'var': 'x0', 'sort': 's', 'body': p},
                      {'quant': 'forall', 'var': 'x0', 'sort': 's', 'body': q}]}
    def heavy(first):
        phi = {'or': [p, {'not': p}]}
        for i in reversed(range(14)):
            phi = {'quant': first if i == 0 else 'forall', 'var': 'x' + str(i), 'sort': 's', 'body': phi}
        return phi
    case = {'signature': sig, 'formulas': {'HeavyAll': heavy('forall'), 'HeavySome': heavy('exists'), 'Per': per, 'Global': global_}}
    result = run_case(case, [['HeavyAll', 'HeavySome'], ['Per', 'Global']], budget)
    expensive, cheap = result['graph']['relations']
    assert expensive['search_halt_reason'].startswith('PAIR_')
    assert expensive['charged_steps'] <= expensive['resource_allocation']['max_steps']
    assert cheap['directions']['A_IMPLIES_B']['status'] == 'COUNTERMODEL_A_NOT_B'
    assert cheap['directions']['A_IMPLIES_B']['models_checked'] == 11
    assert result['checks']['total_steps'] <= 100000 and result['checks']['model_enumerations'] <= budget
    assert result['checks']['directional_coverage']['undecided'] > 0
