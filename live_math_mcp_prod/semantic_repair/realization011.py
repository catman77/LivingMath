"""Source-state annotations -> existing SourceGraph and capacity-one Network."""
from artifact_translation.contract import SourceGraph
from artifact_translation.network import Network
from davcore.ast import digest


def compile_transitions(request, premises: list[dict], disabled, context) -> dict:
    if context is None:
        raise ValueError('AUTHENTICATED_SOURCE_CONTEXT_REQUIRED')
    if set(request.binding.assignments) != {'observation'}:
        raise ValueError('EXPLICIT_SOURCE_OBSERVER_REQUIRED')
    criterion = request.binding.assignments['observation']
    if criterion not in {'SEQUENCE', 'MULTISET', 'SET', 'PARTIAL_SET'}:
        raise ValueError('REGISTERED_OBSERVATION_CRITERION_REQUIRED')
    states = []
    position = {}
    reactions = []
    relations = []
    mapping = []
    annotations = []
    flags = set()
    focus = set()
    def node(value):
        if value['key'] in position:
            existing = states[position[value['key']]]
            if any(existing.get(k, True) != value.get(k, True) for k in
                    ('label', 'features', 'feature_order_known', 'feature_multiplicity_known', 'node_kind')):
                raise ValueError('CONFLICTING_SOURCE_STATE_DESCRIPTOR')
            existing['source_refs'] = sorted(set(existing['source_refs'] + value['source_refs']))
            return position[value['key']]
        position[value['key']] = len(states)
        states.append({**value})
        return len(states) - 1
    graph_kind = {'TRANSITION': 'sequence', 'SEQUENCE': 'sequence', 'CONDITION': 'condition',
        'ORDER': 'order', 'REPEAT': 'repeat', 'IDENTICAL': 'cooccur', 'EQUIVALENT_O': 'repeat',
        'SIMILAR_O': 'repeat', 'REORDERED': 'order', 'NEGATED': 'contrast',
        'COOCCUR': 'cooccur', 'UNKNOWN': 'cooccur'}
    for premise in premises:
        descriptor = premise['realization'].get('transition')
        if not descriptor:
            raise ValueError('ADDRESSED_STATE_TRANSITION_DESCRIPTOR_REQUIRED')
        if not set(descriptor['source']['source_refs'] + descriptor['target']['source_refs']) <= set(premise['source_refs']):
            raise ValueError('UNADDRESSED_TRANSITION_STATE')
        a = node(descriptor['source'])
        b = node(descriptor['target'])
        kinetic = (descriptor['relation_kind'] in {'TRANSITION', 'SEQUENCE'}
            and descriptor['polarity'] == 'POSITIVE' and descriptor['critic_status'] == 'HYPOTHESIS'
            and descriptor['modality'] != 'UNKNOWN'
            and (descriptor['relation_kind'] != 'SEQUENCE' or descriptor['order_kind'] != 'TEXT_ORDER'))
        active = kinetic and premise['id'] not in disabled
        reactions.append({'id': premise['id'], 'reactants': {'n' + str(a): 1},
            'products': {'n' + str(b if active else a): 1}, 'source_relation_ids': [premise['id']]})
        kind = graph_kind[descriptor['relation_kind']]
        relations.append({'id': premise['id'], 'kind': kind, 'src': 'n' + str(a),
            'dst': 'n' + str(b), 'source_refs': premise['source_refs'], 'grade': 'B'})
        annotations.append({'premise_id': premise['id'], **descriptor, 'executable_transition': kinetic,
            'assumption_withdrawn': premise['id'] in disabled})
        mapping.append({'source_role': premise['src'], 'target_coordinate': a,
            'target_state_coordinate': b, 'source_refs': premise['source_refs'],
            'entity_identity': False, 'source_hypothesis': True})
        flags.update(descriptor['review_flags'])
        focus.update(descriptor['projection_features'])
    if len(states) > 8 or len(reactions) > 12 or len(states) < 2:
        return {'status': 'BOUND_INSUFFICIENT_FOR_QUERY', 'profile': 'typed008/1',
            'coordinate_count': len(states), 'compiled_hash': digest(premises),
            'losses': ['Only explicit bounded local state interfaces are admitted.']}
    graph = SourceGraph.model_validate({'id': 'general_' + digest(premises)[:24],
        'nodes': [{'id': 'n' + str(i), 'kind': s.get('node_kind', 'predicate'), 'source_refs': s['source_refs']}
            for i, s in enumerate(states)], 'relations': relations})
    network = Network.model_validate({'species': [{'id': 'n' + str(i), 'label': s['label'][:120],
        'source_refs': s['source_refs']} for i, s in enumerate(states)], 'reactions': reactions})
    observer = {'kind': 'SOURCE_TRANSITION', 'version': 'source-observer011/1',
        'criterion': criterion, 'states': states, 'projection_features': sorted(focus),
        'source_annotations': annotations, 'source_review_flags': sorted(flags),
        'source_cycle_status': 'CONFLICT_OR_NEGATED' if flags else 'HYPOTHESIS_ONLY',
        'equal_observations_imply_full_identity': False, 'physical_identity': False}
    body = {'profile': 'typed008/1', 'observer_version': 'source-observer011/1',
        'spec': {'kind': 'reaction_network', 'reaction_network': network.model_dump()},
        'source_graph': graph.model_dump(), 'premise_ids': [p['id'] for p in premises],
        'source_hashes': sorted({p['source_hash'] for p in premises}),
        'source_premises_hash': digest(premises), 'binding_assignments': request.binding.assignments,
        'disabled_premises': list(disabled), 'initial_states': [1 << position[annotations[0]['source']['key']]],
        'observer': observer, 'role_map': mapping, 'guards': [],
        'assumptions': ['Source annotations and role bindings are conditional hypotheses.',
            'One-hot state markings describe the declared source reading, not a measured world.',
            'Negative/metarelational statements do not create positive transitions.',
            'Prescribed, possible, narrated and physical events remain distinct.'],
        'interface': {'global_composition_verified': False, 'domain': 'DECLARED_REACHABLE_ONEHOT_STATES'},
        'source_context': context.public()}
    return {**body, 'status': 'COMPILED_CONDITIONAL_MODEL', 'compiled_hash': digest(body),
        'target_projection_hash': digest({'spec': body['spec'], 'observer': observer}),
        'coordinate_count': len(states), 'compiler_received_query': False,
        'proof_status': 'unverified', 'execution_permission': {'allowed': False},
        'losses': ['MODEL_DERIVATION is distinct from SOURCE_SUPPORT and literary judgment.']}


def observe_transition(model: dict, state: int) -> dict:
    observer = model['observer']
    active = [i for i in range(model['coordinate_count']) if (state >> i) & 1]
    if len(active) != 1:
        return {'full_state': state, 'state_key': None, 'projection': None,
            'observation_known': False, 'reason': 'NOT_ONE_HOT_DECLARED_SOURCE_STATE',
            'performance': 'UNKNOWN'}
    source = observer['states'][active[0]]
    values = source['features']
    criterion = observer['criterion']
    known = bool(values)
    if criterion == 'SEQUENCE':
        projected = list(values)
        known &= source.get('feature_order_known', True) and source.get('feature_multiplicity_known', True)
    elif criterion == 'MULTISET':
        projected = sorted(values)
        known &= source.get('feature_multiplicity_known', True)
    elif criterion == 'SET':
        projected = sorted(set(values))
    else:
        focus = observer['projection_features']
        vocabulary = {feature for state in observer['states'] for feature in state['features']}
        projected = sorted(set(values) & set(focus))
        known = bool(focus) and set(focus) <= vocabulary and bool(projected)
    return {'full_state': state, 'state_key': source['key'],
        'projection': projected if known else None, 'observation_known': known,
        'criterion': criterion, 'partial_observation': criterion == 'PARTIAL_SET',
        'performance': 'UNKNOWN', 'source_claim_verified': False}
