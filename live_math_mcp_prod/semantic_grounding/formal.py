"""Existing SourceGraph/reaction adapter only; finite truth cannot certify meaning."""
from copy import deepcopy

from artifact_translation.contract import SourceGraph, ProposalRequest
from artifact_translation.generator import propose
from artifact_translation.checker import check_translation, independent_verdict
from artifact_translation.network import Network
from artifact_genesis.binding import nontriviality
from davcore.adapters import Adapter, AdapterSpec
from davcore.ast import Formula, Eq, Implies, Apply, term, implication, digest


def formalize(h: dict, critique: dict) -> dict:
    if critique['status'] != 'SOURCE_INTERNAL_SUPPORT' or not critique['independent_source_evidence']:
        raise ValueError('INDEPENDENT_SOURCE_BINDING_REQUIRED_BEFORE_DAV')
    if critique['target_used'] or h['proof_status'] != 'unverified':
        raise ValueError('SOURCE_AUTHORITY_OR_TARGET_FEEDBACK')
    if h['source_packet_sha256'] != critique['train_packet_sha256'] or h['family'] != critique['family']:
        raise ValueError('REVIEW_BELONGS_TO_ANOTHER_SOURCE_INPUT')
    if h['prediction']['label'] != critique['label']:
        raise ValueError('SOURCE_REVIEW_REJECTS_THIS_READING')
    if digest({k: v for k, v in critique.items() if k != 'review_id'}) != critique['review_id']:
        raise ValueError('SOURCE_REVIEW_HASH_DRIFT')
    rs = h['roles']
    relation = h['proposed_relation']
    evidence_refs = [e['span_id'] for e in critique['independent_source_evidence']]
    nodes = [{'id': r['id'], 'kind': 'symbolic_role', 'source_refs': [r['span_id']]} for r in rs]
    graph = SourceGraph.model_validate({
        'id': 'source_' + h['hypothesis_id'][:24], 'nodes': nodes,
        'relations': [{'id': 'relation_' + h['hypothesis_id'][:24],
                       'kind': 'condition' if critique['label'] == 'ORDERED' else 'role',
                       'src': relation['src'], 'dst': relation['dst'],
                       'source_refs': sorted(set([r['span_id'] for r in rs] + evidence_refs)), 'grade': 'B'}],
    })
    candidate = propose(ProposalRequest(graph=graph, allowed_edits=['catalytic']))['candidates'][0]
    fidelity = check_translation(graph, candidate)
    if fidelity['status'] != 'FORMAL_TRANSLATION_VALID':
        raise ValueError('EXISTING_REVERSE_TRANSLATION_REJECTED')
    network = Network.model_validate(candidate['network'])
    adapter = Adapter(AdapterSpec(kind='reaction_network', reaction_network=network))
    # This is an actual countermodel to static necessity, never an empirical claim.
    positions = {r['id']: i for i, r in enumerate(rs)}
    source_op = 'S' + str(positions[relation['src']])
    target_op = 'S' + str(positions[relation['dst']])
    probe = implication(source_op, 'One', target_op, 'One')
    necessity = nontriviality(adapter, probe)
    law = Formula(body=Implies(
        premise=Eq(left=term('E0'), right=term('One')),
        conclusion=Eq(left=Apply(operation=target_op, argument=term('R0')), right=term('One'))))
    guard = nontriviality(adapter, law)
    reference = independent_verdict(network, law)
    if reference['status'] != guard['with_premise']['status']:
        raise ValueError('INDEPENDENT_FINITE_VERDICT_DISAGREES')
    # A constitutive command consequence is not a discovered source law.
    scientific = 'FAIL_TARGET_TAUTOLOGY' if guard['status'] == 'PASS_FORMAL_NONTRIVIALITY' else guard['status']
    bindings = [{'source_role_id': r['id'], 'source_span_id': r['span_id'],
                 'source_quote': r['name'], 'target_species': candidate['mapping'][r['id']],
                 'source_reference_identity': critique['distinctions']['reference_identity'],
                 'meaning': 'Presence coordinate for an addressed mention/event, not substance or entity identity'} for r in rs]
    loss = {'hypothesis_id': h['hypothesis_id'], 'review_id': critique['review_id'],
            'preserved_at_source': deepcopy(critique['distinctions']),
            'target_unrepresented': ['Reference identity', 'Negation scope', 'Narrative agency',
                                     'Actual chronology', 'Analogy', 'Prescriptive modality'],
            'source_evidence_retained': critique['independent_source_evidence'],
            'back_translation_limit': 'Finite markings and guards return mention provenance only; they do not return the unrepresented semantic distinctions.',
            'empirically_realized': 'UNKNOWN'}
    return {'hypothesis_id': h['hypothesis_id'], 'review_id': critique['review_id'],
            'source_graph': graph.model_dump(), 'candidate': candidate, 'reverse_check': fidelity,
            'role_bindings': bindings, 'loss': loss, 'necessity_probe': necessity,
            'formula': law.canonical_ast(), 'guard_law': guard, 'independent_stoichiometric_verdict': reference,
            'status': 'TARGET_MODEL_VALID', 'scientific_law_status': scientific,
            'source_semantics_proved': False, 'proof_status': 'unverified',
            'execution_permission': {'allowed': False}}


def calibration_controls() -> list[dict]:
    gate6 = nontriviality(Adapter(AdapterSpec(kind='gate6')), implication('P', 'One', 'Q', 'One'))
    vacuous = nontriviality(Adapter(AdapterSpec(kind='graph')), implication('S0', 'S0', 'P', 'P'))
    network = Network.model_validate({'species': [{'id': k, 'label': k, 'source_refs': ['synthetic']} for k in 'abcd'],
        'reactions': [{'id': 'x', 'reactants': {'a': 1}, 'products': {'b': 1}, 'source_relation_ids': ['synthetic']},
                      {'id': 'y', 'reactants': {'c': 1}, 'products': {'d': 1}, 'source_relation_ids': ['synthetic']}]})
    independent = Formula(body=Implies(
        premise=Eq(left=term('S0'), right=term('Zero')),
        conclusion=Eq(left=Apply(operation='R1', argument=term('R0')),
                      right=Apply(operation='R0', argument=term('R1')))))
    shortcut = nontriviality(Adapter(AdapterSpec(kind='reaction_network', reaction_network=network)), independent)
    return [{'control': 'KNOWN_GATE6_P1_Q0', 'passed': gate6['with_premise']['status'] == 'refuted'
             and gate6['with_premise']['counterexample']['state'] == 1, 'evidence': gate6},
            {'control': 'NO_PREMISE_VACUITY_REJECTED', 'passed': vacuous['status'] == 'FAIL_VACUOUS_LAW', 'evidence': vacuous},
            {'control': 'INDEPENDENT_COMMAND_SHORTCUT_REJECTED', 'passed': shortcut['status'] == 'FAIL_VACUOUS_LAW', 'evidence': shortcut}]
