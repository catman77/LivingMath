"""012 S/H projection into existing SourceGraph and optional strict Network."""
from artifact_translation.contract import SourceGraph
from artifact_translation.network import Network
from davcore.ast import digest


def command_eligible(d: dict) -> bool:
    c = d['source_claim']
    return (d['relation_kind'] == 'TRANSITION' and d['polarity'] == 'POSITIVE'
        and d['modality'] in {'ASSERTED', 'NARRATED', 'PRESCRIBED', 'CONDITIONAL', 'POSSIBLE'}
        and d['order_kind'] in {'EVENT_ORDER', 'INFERRED_EVENT_ORDER'}
        and d['critic_status'] == 'HYPOTHESIS' and c['source_status'] == 'HYPOTHESIS'
        and c['mode'] in {'DIRECT', 'NARRATION'} and c['stance'] == 'ASSERTS'
        and c['quotation_guard'] == 'NOT_QUOTED'
        and d['source']['level'] == d['target']['level'] == 'WORLD_STATE'
        and d['source']['key'] != d['target']['key']
        and d['executable_assumption_supported']
        and 'CONDITIONAL_EXECUTABLE_CHANGE' in d['interpretation_assumptions'])


def compile_semantics(request, premises: list[dict], disabled, context) -> dict:
    if context is None:
        raise ValueError('AUTHENTICATED_SOURCE_CONTEXT_REQUIRED')
    context.require(request.binding.project, premises)
    if request.binding.assignments != {'observation': 'SOURCE_SCOPED012'}:
        raise ValueError('SOURCE_NAMED_OBSERVERS_REQUIRED')
    infos = [p['realization']['transition']['inference'] for p in premises if p['realization']['transition'].get('inference') is not None]
    if len(infos) > 1: raise ValueError('OBSERVER013_DEFINITIONS_MUST_BE_UNIQUE')
    inference = infos[0] if infos else None
    states: dict[str, dict] = {}
    profiles: list[dict] = []
    initials: list[str] = []
    annotations = []
    graph_relations = []
    commands = []
    allowed = {r for p in premises for r in p['source_refs']}
    graph_kind = {'TRANSITION': 'sequence', 'SEQUENCE': 'sequence', 'CONDITION': 'condition',
        'ORDER': 'order', 'REPEAT': 'repeat', 'IDENTICAL': 'cooccur', 'EQUIVALENT_O': 'repeat',
        'SIMILAR_O': 'repeat', 'REORDERED': 'order', 'NEGATED': 'contrast', 'COOCCUR': 'cooccur', 'UNKNOWN': 'cooccur'}
    for premise in premises:
        d = premise['realization']['transition']
        if d['version'] != 'source-transition012/1':
            raise ValueError('MIXED_SOURCE_SEMANTICS_VERSIONS')
        for s in (d.get('declared_states') or []) + [d['source'], d['target']]:
            if not set(s['source_refs']) <= allowed:
                raise ValueError('FOREIGN_SOURCE_STATE_REFERENCE')
            if any(a['ref'] not in allowed for a in s['addresses'] + s['feature_addresses']):
                raise ValueError('FOREIGN_SOURCE_FEATURE_ADDRESS')
            if s['key'] in states and states[s['key']] != s:
                raise ValueError('CONFLICTING_SOURCE_STATE')
            states[s['key']] = s
        if d.get('observers') is not None:
            if profiles: raise ValueError('OBSERVER_DEFINITIONS_MUST_BE_UNIQUE')
            profiles = d['observers']
            initials = d.get('initial_keys') or []
        if any(a['ref'] not in allowed for a in d['source_claim']['addresses']):
            raise ValueError('FOREIGN_SOURCE_CLAIM_ADDRESS')
        active = command_eligible(d) and premise['id'] not in disabled
        annotations.append({**{k: v for k, v in d.items() if k not in {'observers', 'declared_states', 'initial_keys', 'inference'}},
            'premise_id': premise['id'], 'assumption_withdrawn': premise['id'] in disabled,
            'executable_transition': active, 'performance': 'UNKNOWN', 'source_verified': False})
        if active: commands.append(annotations[-1])
    if not 2 <= len(states) <= 8 or len(annotations) > 12:
        return {'status': 'BOUND_INSUFFICIENT_FOR_QUERY', 'compiled_hash': digest(premises)}
    node_ids = {key: 'n' + str(i) for i, key in enumerate(states)}
    for a in annotations:
        graph_relations.append({'id': a['premise_id'], 'kind': graph_kind[a['relation_kind']],
            'src': node_ids[a['source']['key']], 'dst': node_ids[a['target']['key']],
            'source_refs': next(p['source_refs'] for p in premises if p['id'] == a['premise_id']), 'grade': 'B'})
    graph = SourceGraph.model_validate({'id': 'source012_' + digest(premises)[:24],
        'interpretation': 'MIXED' if commands else 'META_ONLY', 'semantics_version': 'source-graph012/1',
        'nodes': [{'id': node_ids[k], 'kind': s['node_kind'], 'source_refs': s['source_refs']} for k, s in states.items()],
        'relations': graph_relations})
    for o in profiles:
        addresses = o['addresses'] + [a for sample in o['samples'] for aa in sample['addresses'].values() for a in aa]
        if any(a['ref'] not in allowed for a in addresses):
            raise ValueError('FOREIGN_OBSERVER_ADDRESS')
        if any(s['state_key'] not in states for s in o['samples']):
            raise ValueError('OBSERVER_OUTSIDE_DECLARED_SOURCE_GRAPH')
    worlds = {k: s for k, s in states.items() if s['level'] == 'WORLD_STATE'}
    position = {key: i for i, key in enumerate(worlds)}
    initial_marks = [1 << position[k] for k in initials if k in position]
    initial_choice = 'SOURCE_CITED_CONDITIONAL_INITIALS' if initial_marks else 'NO_SOURCE_ATTESTED_INITIAL; FIRST_COMMAND_START_CHOSEN_IN_H'
    if commands and not initial_marks:
        initial_marks = [1 << position[commands[0]['source']['key']]]
    observer = {'kind': 'SOURCE_SEMANTICS012', 'version': 'source-observer012/1',
        'states': list(states.values()), 'world_positions': position, 'observers': profiles,
        'source_annotations': annotations, 'initial_choice': initial_choice, 'source_initial_keys': initials,
        'equal_observations_imply_full_identity': False, 'source_verified': False}
    body = {'profile': 'typed008/1', 'observer_version': 'source-observer012/1',
        'source_graph': graph.model_dump(), 'source_hashes': sorted({p['source_hash'] for p in premises}),
        'source_premises_hash': digest(premises), 'binding_assignments': request.binding.assignments,
        'observer': observer, 'disabled_premises': list(disabled), 'source_context': context.public(),
        'premise_ids': [a['premise_id'] for a in commands], 'coordinate_count': len(worlds) if commands else 0,
        'initial_states': initial_marks if commands else [], 'guards': [], 'role_map': [],
        'compiler_received_query': False, 'target_model': 'APPLICABLE' if commands else 'NOT_APPLICABLE',
        'interpretation_assumptions': sorted({v for a in annotations for v in a['interpretation_assumptions']}),
        'proof_status': 'unverified', 'source_verified': False, 'execution_permission': {'allowed': False},
        'assumptions': ['S reports H; H is not a world fact.', 'A conditional command is not attested performance.',
            'An observer equivalence never identifies complete physical states.']}
    if commands:
        network = Network.model_validate({'species': [{'id': 'n' + str(i), 'label': s['label'][:120],
            'source_refs': s['source_refs']} for i, s in enumerate(worlds.values())],
            'reactions': [{'id': a['premise_id'], 'reactants': {'n' + str(position[a['source']['key']]): 1},
                'products': {'n' + str(position[a['target']['key']]): 1}, 'source_relation_ids': [a['premise_id']]} for a in commands]})
        body.update(status='COMPILED_CONDITIONAL_MODEL', spec={'kind': 'reaction_network', 'reaction_network': network.model_dump()})
    else:
        body.update(status='META_ONLY_SOURCE_MODEL')
    if inference is not None:
        if inference['source_sha256'] not in body['source_hashes']: raise ValueError('FOREIGN_OBSERVER013_SOURCE')
        def addresses(value):
            if isinstance(value, dict):
                if 'ref' in value and value['ref'] not in allowed: raise ValueError('FOREIGN_OBSERVER013_ADDRESS')
                for v in value.values(): addresses(v)
            elif isinstance(value, list):
                for v in value: addresses(v)
        addresses(inference)
        if any(s['state_key'] not in states for p in inference['profiles'] for s in p['samples']):
            raise ValueError('OBSERVER013_OUTSIDE_DECLARED_SOURCE_GRAPH')
        if any(r['source'] not in states or r['target'] not in states for r in inference['reports']):
            raise ValueError('REPORT013_OUTSIDE_DECLARED_SOURCE_GRAPH')
        body['observer']['inference'] = inference
        body['observer_version'] = 'source-observer013/1'
    body['compiled_hash'] = digest(body)
    projection = {'spec': body.get('spec'), 'observers': profiles,
        'states': [(s['key'], s['features']) for s in worlds.values()]}
    if inference is not None: projection['inference'] = inference
    body['target_projection_hash'] = digest(projection)
    return body


def observe(model: dict, state: int) -> dict:
    positions = model['observer']['world_positions']
    keys = [key for key, i in positions.items() if state & (1 << i)]
    key = keys[0] if len(keys) == 1 else None
    outputs = {}
    for o in model['observer']['observers']:
        sample = next((s for s in o['samples'] if s['state_key'] == key), None)
        values = sample['values'] if sample else {f: None for f in o['features']}
        outputs[o['id']] = {'values': values, 'unknown_mask': [f for f, v in values.items() if v is None]}
    return {'full_state': state, 'state_key': key, 'named_observers': outputs,
        'observation_known': key is not None and bool(outputs) and all(not o['unknown_mask'] for o in outputs.values()),
        'performance': 'UNKNOWN', 'source_claim_verified': False}
