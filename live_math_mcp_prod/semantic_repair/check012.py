"""Scoped record obligations and independent finite witnesses, after model freeze.

These are fixed Python checks on existing records, not a formula interpreter.
A passed transport check does not validate a source interpretation.
"""
from copy import deepcopy
from itertools import combinations

from davcore.ast import digest

from .check011 import reference_step
from .realization012 import command_eligible, observe
from .trace008 import adapter, certify, evaluate, questions


def compare_observer(profile: dict, left: str, right: str) -> dict:
    samples = {s['state_key']: s['values'] for s in profile['samples']}
    x, y = samples.get(left, {}), samples.get(right, {})
    features = profile['features']
    shared = [f for f in features if x.get(f) is not None and y.get(f) is not None]
    unknown = [f for f in features if f not in shared]
    different = [f for f in shared if x[f] != y[f]]
    if different:
        status = 'DISTINGUISHABLE_ON_NAMED_OBSERVER'
    elif not shared or profile['criterion'] == 'UNKNOWN':
        status = 'UNKNOWN'
    elif unknown or profile['criterion'] == 'PARTIAL_SET':
        status = 'CONSISTENT_ON_SHARED_FEATURES'
    else:
        status = 'EQUIVALENT_ON_NAMED_OBSERVER'
    return {'observer_id': profile['id'], 'states': [left, right], 'status': status,
        'criterion': profile['criterion'], 'shared_features': shared, 'unknown_mask': unknown,
        'different_features': different, 'full_state_equality_inferred': False,
        'source_claim_verified': False}


def compact_trace(model: dict, initial: int, path: list[str], tables: dict) -> dict:
    state = initial
    steps = []
    for pid in path:
        after = tables[pid][state]
        steps.append({'source_operation_id': pid, 'before': state, 'after': after,
            'fired': after != state and pid not in model['disabled_premises'], 'identity_is_not_event': after == state})
        state = after
    body = {'initial_state': initial, 'registered_initial': initial in model['initial_states'],
        'final_state': state, 'steps': steps,
        'all_steps_fired': bool(steps) and all(s['fired'] for s in steps),
        'actual_round_trip': len(steps) >= 2 and all(s['fired'] for s in steps) and state == initial,
        'scope': 'FINITE_CONDITIONAL_MODEL_NOT_SOURCE_PERFORMANCE', 'source_claim_verified': False}
    return {**body, 'trace_id': 'tr_' + digest(body)[:24]}


def dynamics(model: dict) -> dict:
    a = adapter(model)
    network = model['spec']['reaction_network']
    tables = {pid: [reference_step(network, i, s) for s in a.states()] for i, pid in enumerate(model['premise_ids'])}
    agree = all(a.apply('R' + str(i), s) == tables[pid][s]
        for s in a.states() for i, pid in enumerate(model['premise_ids']))
    # Includes projections/enabled operations, independently checked by the old reference.
    from artifact_translation.checker import independent_apply
    assert a.spec.reaction_network is not None
    agree = agree and all(a.apply(op, s) == independent_apply(a.spec.reaction_network, op, s)
        for s in a.states() for op in a.ops)
    if not agree:
        raise ValueError('INDEPENDENT_FINITE_TABLE_DISAGREEMENT')
    reached = set(model['initial_states'])
    frontier = list(reached)
    while frontier:
        s = frontier.pop()
        for table in tables.values():
            if table[s] not in reached:
                reached.add(table[s]); frontier.append(table[s])
    cycles: list[dict] = []
    returns: list[dict] = []
    walks: list[dict] = []
    expansions = 0
    for start in model['initial_states']:
        pending: list[tuple[int, list[str], set[int]]] = [(start, [], {start})]
        while pending and expansions < 512:
            state, path, seen = pending.pop()
            expansions += 1
            for pid, table in tables.items():
                after = table[state]
                if after == state:
                    continue
                steps = path + [pid]
                t = compact_trace(model, start, steps, tables)
                if len(walks) < 12: walks.append(t)
                if after == start and len(steps) >= 2 and len(cycles) < 12: cycles.append(t)
                positions = model['observer']['world_positions']
                first = next((k for k, i in positions.items() if start == 1 << i), None)
                last = next((k for k, i in positions.items() if after == 1 << i), None)
                if first is not None and last is not None:
                    for o in model['observer']['observers']:
                        comparison = compare_observer(o, first, last)
                        if comparison['status'] == 'EQUIVALENT_ON_NAMED_OBSERVER' and len(returns) < 12:
                            returns.append({'kind': 'OBSERVATION_RECURRENCE', 'trace_id': t['trace_id'],
                                'trace': t, 'comparison': comparison, 'same_full_state': start == after})
                if after not in seen and len(steps) < model['coordinate_count'] + 1:
                    pending.append((after, steps, seen | {after}))
    closure = bool(reached) and all(t[s] in reached for s in reached for t in tables.values())
    semantic = {'transitions': list(tables.values()), 'observations': [observe(model, s)['named_observers'] for s in a.states()]}
    return {'full_state_count': len(a.states()), 'all_operations_independently_replayed': agree,
        'operation_table_sha256': digest(list(tables.values())), 'traces': walks,
        'outcome': 'HAS_ENABLED_TRACE' if walks else 'NO_ENABLED_TRACE',
        'source_transition_analysis': {'independent_full_table_sha256': digest(list(tables.values())),
            'semantic_projection_sha256': digest(semantic), 'registered_initial_states': model['initial_states'],
            'reachable_states': sorted(reached), 'T_C_subset_C': closure,
            'closure_scope': 'REGISTERED_REACHABLE_FINITE_MARKINGS_ONLY',
            'nonvacuous_enabled_reachable_edge': bool(walks), 'full_state_cycles': cycles,
            'cycle_status': 'MODEL_CYCLE_REACHABLE' if cycles else 'NO_REACHABLE_CYCLE_WITNESS',
            'observed_returns': returns, 'walk_witnesses_truncated': expansions >= 512,
            'cycle_search_scope': 'SIMPLE_FIRED_PATHS_FROM_REGISTERED_INITIALS; 512 expansion bound',
            'performance': 'UNKNOWN', 'source_claim_verified': False},
        'invariants': {'single_source_state_in_registered_reachable_domain': all(s > 0 and s & (s - 1) == 0 for s in reached),
            'successor_closed_in_registered_domain': closure, 'no_performance_attested': True}}


def obligations(model: dict) -> list[dict]:
    """Record predicates about S/H, never a theorem that an attributed p holds."""
    result = []
    for a in model['observer']['source_annotations']:
        c = a['source_claim']
        item = {'premise_id': a['premise_id'], 'source_claim': c['id'], 'source_addresses': c['addresses'],
            'interpretation_assumptions': a['interpretation_assumptions'],
            'check_scope': 'EXACT_FROZEN_SOURCE_ANNOTATION_TRANSPORT; NOT S entails H',
            'source_status': c['source_status'], 'source_verified': False}
        def add(kind, formula, witness, countermodel=None, item=item):
            result.append({**item, 'kind': kind, 'target_assertion': formula, 'proof_witness': witness,
                'countermodel': countermodel, 'result': 'PASS_META_TRANSPORT',
                'world_truth': 'UNKNOWN', 'proof_status': 'unverified'})
        add('ATTRIBUTION_IS_NOT_TRUTH', 'retained(source_claim) = addressed H; reports(speaker,p) does not entail p',
            {'speaker': c['speaker'], 'mode': c['mode'], 'stance': c['stance'], 'world_assertion_emitted': False},
            {'reported_p': True, 'world_p': False, 'scope': 'Minimal logical countermodel, not source evidence'})
        add('SCOPED_RELATION', 'retained(kind,polarity,order,coordinates,projection) = H',
            {'record_sha256': digest({k: a[k] for k in ('relation_kind', 'polarity', 'order_kind', 'claim', 'source_projection')})})
        add('CONDITIONAL_COMMAND_NOT_PERFORMANCE', 'command_exists => conditional_in_M; performance remains UNKNOWN',
            {'command_exists': a['executable_transition'], 'performance': a['performance'],
                'eligible': command_eligible(a), 'assumption_withdrawn': a['assumption_withdrawn']})
        if a['relation_kind'] == 'TRANSITION':
            add('DIRECTION_WITHOUT_INFERRED_CONVERSE', 'this premise can emit only source -> target; any converse needs its own source premise',
                {'source': a['source']['key'], 'target': a['target']['key'], 'premise_id': a['premise_id']},
                {'minimal_example': 'A -> B; B has no outgoing edge', 'converse_follows': False})
        if a['relation_kind'] in {'ORDER', 'REORDERED'} or a['order_kind'] == 'TEXT_ORDER':
            add('TEXT_ORDER_NOT_CAUSALITY', 'text_order alone emits no executable operation',
                {'order_kind': a['order_kind'], 'command_exists': a['executable_transition']})
        if a['relation_kind'] in {'REPEAT', 'EQUIVALENT_O', 'SIMILAR_O', 'IDENTICAL'}:
            add('RECURRENCE_NOT_RETURN_COMMAND', 'reported recurrence emits no reverse command',
                {'command_exists': a['executable_transition'], 'full_identity_inferred': False})
        if a['polarity'] in {'NEGATIVE', 'CONFLICT'} or a['relation_kind'] == 'NEGATED':
            add('SOURCE_NEGATIVE_NOT_ABSENCE', 'retained explicit source negative != missing positive',
                {'polarity': a['polarity'], 'command_exists': a['executable_transition'], 'global_not_p_emitted': False})
    return result


def loss_ledger(premises: list[dict], model: dict) -> list[dict]:
    """Every consequential field gets an exact retention/alteration witness.

    Target credit requires an actual changed integer transition. Merely keeping
    a label, digest or annotation earns only META_ONLY credit.
    """
    ledger = []
    annotations = {a['premise_id']: a for a in model['observer']['source_annotations']}
    paths = ['relation_kind', 'polarity', 'modality', 'order_kind', 'critic_status', 'review_flags',
        'interpretation_assumptions', 'executable_assumption_supported']
    def get(d, path):
        for part in path.split('.'): d = d[part]
        return d
    def put(d, path, value):
        parts = path.split('.')
        for part in parts[:-1]: d = d[part]
        d[parts[-1]] = value
    for p in premises:
        d = p['realization']['transition']; saved = annotations[p['id']]
        fields = paths + [group + '.' + key for group in ('claim', 'source_claim', 'source_projection')
            for key in d[group] if key not in {'id', 'addresses'}]
        fields += [group + '.' + key for group in ('source', 'target') for key in d[group]]
        for field in fields:
            value, actual = get(d, field), get(saved, field)
            retained = actual == value
            status = 'PRESERVED_META_ONLY' if retained else 'LOST'
            witness = {'path': field, 'value_sha256': digest(value), 'same_value': retained,
                'mutation': 'replace field by a distinct tagged value',
                'record_predicate_after_mutation': actual == {'removed_distinction': field}}
            mutants = {'relation_kind': 'UNKNOWN', 'polarity': 'UNKNOWN', 'modality': 'UNKNOWN',
                'order_kind': 'UNKNOWN', 'critic_status': 'UNKNOWN', 'interpretation_assumptions': [],
                'executable_assumption_supported': False, 'source_claim.mode': 'ATTRIBUTED',
                'source_claim.stance': 'UNKNOWN', 'source_claim.source_status': 'UNKNOWN',
                'source_claim.quotation_guard': 'AMBIGUOUS', 'source.level': 'SOURCE_EVENT', 'target.level': 'SOURCE_EVENT'}
            if retained and saved['executable_transition'] and field in mutants.keys() | {'source.key', 'target.key'}:
                mutant = deepcopy(saved)
                replacement = saved['target' if field == 'source.key' else 'source']['key'] if field.endswith('.key') else mutants[field]
                put(mutant, field, replacement)
                if not command_eligible(mutant):
                    i = model['premise_ids'].index(p['id'])
                    state = 1 << model['observer']['world_positions'][saved['source']['key']]
                    after = reference_step(model['spec']['reaction_network'], i, state)
                    if after != state:
                        status = 'PRESERVED_IN_TARGET'
                        witness['target_counterfactual'] = {'state': state,
                            'before': after, 'after_command_withdrawal': state, 'mutated_eligible': False}
            # Resolve source_claim against frozen observer.source_annotations for exact byte addresses.
            ledger.append({'source_operation_id': p['id'], 'source_claim': d['source_claim']['id'],
                'distinction': field, 'status': status, 'critical': True, 'witness': witness})
    info = premises[0]['realization']['transition'].get('inference')
    if info is not None:
        actual = model['observer'].get('inference')
        ledger.append({'distinction': 'inference013.addressed_values_bindings_reports',
            'status': 'PRESERVED_META_ONLY' if info == actual else 'LOST', 'critical': True,
            'witness': {'expected_sha256': digest(info), 'actual_sha256': digest(actual),
                'each_expected_record_retained': info == actual, 'source_truth_validated': False},
            'scope': 'Source records retained; conditional consequences separately enumerated after freeze'})
    # Declared states, observer values/masks and chosen initial markings persist once.
    first = premises[0]['realization']['transition']
    for field, stored in [('declared_states', model['observer']['states']), ('observers', model['observer']['observers']), ('initial_keys', model['observer']['source_initial_keys'])]:
        expected = first.get(field, [])
        # Source events reified as relation endpoints are also included in states.
        okay = all(v in stored for v in expected)
        ledger.append({'distinction': field, 'status': 'PRESERVED_META_ONLY' if okay else 'LOST',
            'critical': True, 'address_refs': sorted({r for p in premises for r in p['source_refs']}),
            'witness': {'expected_sha256': digest(expected), 'actual_sha256': digest(stored),
                'each_expected_record_retained': okay, 'counterfactual_removed_record_changes_meta': bool(expected)},
            'scope': 'Named values and masks retained; not full state identity'})
    for index, profile in enumerate(model['observer']['observers']):
        for j, sample in enumerate(profile['samples']):
            for feature, value in sample['values'].items():
                witness = {'path': f'observers/{index}/samples/{j}/values/{feature}',
                    'value_sha256': digest(value), 'unknown': value is None,
                    'source_addresses': sample['addresses'].get(feature, []),
                    'same_value': first['observers'][index]['samples'][j]['values'][feature] == value}
                status = 'PRESERVED_META_ONLY'
                positions = model['observer']['world_positions']
                if model['target_model'] == 'APPLICABLE' and sample['state_key'] in positions:
                    state = 1 << positions[sample['state_key']]
                    mutated = deepcopy(model)
                    altered = None if value is not None else 'COUNTERFACTUAL_NOT_SOURCE_EVIDENCE'
                    mutated['observer']['observers'][index]['samples'][j]['values'][feature] = altered
                    before = observe(model, state)['named_observers'][profile['id']]
                    after = observe(mutated, state)['named_observers'][profile['id']]
                    if before != after:
                        status = 'PRESERVED_IN_TARGET'
                        witness['target_counterfactual'] = {'state': state, 'before_observation': before,
                            'after_observation': after, 'scope': 'Mutation witness only; altered value is not source evidence'}
                ledger.append({'distinction': 'observer_value_and_unknown_mask', 'observer_id': profile['id'],
                    'state_key': sample['state_key'], 'feature': feature, 'status': status, 'critical': True, 'witness': witness})
    return ledger


def ablations(premises, binding, model, context):
    from .compiler import compile_model
    result = []
    for p in premises:
        removed = compile_model(premises, binding, profile='typed008/1', context=context, disabled=(p['id'],))
        a = next(v for v in removed['observer']['source_annotations'] if v['premise_id'] == p['id'])
        target = p['id'] in model['premise_ids']
        witness = None
        if target:
            old = next(v for v in model['observer']['source_annotations'] if v['premise_id'] == p['id'])
            state = 1 << model['observer']['world_positions'][old['source']['key']]
            i = model['premise_ids'].index(p['id'])
            witness = {'state': state, 'before': reference_step(model['spec']['reaction_network'], i, state),
                'after': state, 'operation_withdrawn': p['id'] not in removed['premise_ids']}
        result.append({'kind': 'SOURCE_UNIT_DELETION', 'source_operation_id': p['id'], 'source_refs': p['source_refs'],
            'changed': target, 'target_witness': witness, 'source_assumption_withdrawn': a['assumption_withdrawn'],
            'historical_source_annotation_retained': True,
            'effect': 'TARGET_OPERATION_WITHDRAWN' if target else 'SOURCE_ASSUMPTION_WITHDRAWN_META_ONLY'})
    return result


def validate_source_boundary(model: dict) -> None:
    """Independent admission check, deliberately not command_eligible()."""
    admitted = []
    for a in model['observer']['source_annotations']:
        c = a['source_claim']
        forbidden = (a['relation_kind'] != 'TRANSITION' or a['polarity'] != 'POSITIVE'
            or a['modality'] == 'UNKNOWN' or a['order_kind'] not in ('EVENT_ORDER', 'INFERRED_EVENT_ORDER')
            or c['mode'] not in ('DIRECT', 'NARRATION') or c['stance'] != 'ASSERTS'
            or c['quotation_guard'] != 'NOT_QUOTED' or c['source_status'] != 'HYPOTHESIS'
            or a['critic_status'] != 'HYPOTHESIS' or a['assumption_withdrawn']
            or a['source']['level'] != 'WORLD_STATE' or a['target']['level'] != 'WORLD_STATE'
            or a['source']['key'] == a['target']['key'] or not a['executable_assumption_supported']
            or 'CONDITIONAL_EXECUTABLE_CHANGE' not in a['interpretation_assumptions'])
        if a['executable_transition'] == forbidden:
            raise ValueError('SOURCE_EXECUTION_SCOPE_COUNTERMODEL:' + a['premise_id'])
        if not forbidden: admitted.append(a)
        if a['performance'] != 'UNKNOWN' or a['source_verified']:
            raise ValueError('SOURCE_PERFORMANCE_OR_TRUTH_ESCALATION')
    if [a['premise_id'] for a in admitted] != model['premise_ids']:
        raise ValueError('FOREIGN_OR_META_EXECUTABLE_OPERATION')
    if not admitted:
        if model['target_model'] != 'NOT_APPLICABLE' or 'spec' in model or model['initial_states']:
            raise ValueError('FICTITIOUS_META_TARGET_MODEL')
    else:
        position = model['observer']['world_positions']
        network = model['spec']['reaction_network']
        if len(network['reactions']) != len(admitted): raise ValueError('UNSOURCED_OPERATION')
        for a, r in zip(admitted, network['reactions']):
            expected = ({'n' + str(position[a['source']['key']]): 1}, {'n' + str(position[a['target']['key']]): 1})
            if (r['reactants'], r['products']) != expected or r['source_relation_ids'] != [a['premise_id']]:
                raise ValueError('SOURCE_TARGET_DIRECTION_COUNTERMODEL')


def check_semantics(premises: list[dict], binding: dict, model: dict, context) -> dict:
    validate_source_boundary(model)
    meta = model['target_model'] == 'NOT_APPLICABLE'
    if meta:
        analysis = {'full_state_count': 0, 'traces': [], 'outcome': 'META_ONLY_SOURCE_FORMAL_REPORT',
            'operation_table_sha256': None, 'all_operations_independently_replayed': False,
            'target_check': 'NOT_APPLICABLE', 'classification': 'SOURCE_META_TRANSPORT_NOT_WORLD_TRUTH'}
    else:
        analysis = dynamics(model)
    comparisons: list[dict] = []
    for o in model['observer']['observers']:
        pairs = {tuple(sorted(pair)) for pair in combinations([s['state_key'] for s in o['samples']], 2)}
        pairs.update(tuple(sorted((a['source']['key'], a['target']['key'])))
            for a in model['observer']['source_annotations'] if a['source_claim']['observer_id'] == o['id'])
        comparisons.extend(compare_observer(o, *pair) for pair in sorted(pairs))
    source_obligations = obligations(model)
    ledger = loss_ledger(premises, model)
    checked = []
    qs = [] if meta else questions(model)
    selected = [q for q in qs if q['kind'] == 'PERSISTENCE'][:2]
    for kind in ('ORDER', 'ROUND_TRIP_EQUALITY_ONLY'):
        selected += next(([q] for q in qs if q['kind'] == kind), [])
    for q in selected:
        contract = certify(premises, binding, model, q, context=context)
        result = evaluate(premises, binding, model, contract, context=context)
        result['dav'].pop('evaluation_trace', None)
        xs = result['independent'].pop('counterexample_states')
        result['independent'].update(counterexample_count=len(xs), first_counterexample=xs[0] if xs else None)
        checked.append({'contract': contract, 'result': result})
    scene_comparisons = []
    for left, right in combinations(model['observer']['states'], 2):
        x, y = left['features'], right['features']
        known = bool(x and y)
        order = known and left['feature_order_known'] and right['feature_order_known']
        scene_comparisons.append({'states': [left['key'], right['key']],
            'sequence_equal': x == y if order else None,
            'multiset_equal': sorted(x) == sorted(y) if order else None,
            'set_equal': set(x) == set(y) if known else None,
            'shared_features': sorted(set(x) & set(y)),
            'full_symbolic_state_equal': left['key'] == right['key'], 'physical_identity': 'UNKNOWN',
            'scope': 'ADDRESSED_FEATURE_LISTS_ONLY; unmentioned is unknown, not absent'})
    analysis.update(declared_scene_comparisons=scene_comparisons, source_meta_obligations=source_obligations, observer_comparisons=comparisons,
        meta_transport_checked=True, source_claim_verified=False)
    critical_loss = any(x['critical'] and x['status'] in {'LOST', 'UNSUPPORTED'} for x in ledger)
    uncertain = any(a['critic_status'] != 'HYPOTHESIS' or a['review_flags'] for a in model['observer']['source_annotations'])
    if model['observer'].get('inference') is not None:
        from .inference013 import analyze
        analysis['conditional_observer_inference'] = analyze(model)
    return {'model_hash': model['compiled_hash'], 'analysis': analysis, 'checked': checked,
        'deletions': ablations(premises, binding, model, context), 'loss_ledger': ledger,
        'query_count': len(qs), 'query_generation': 'AFTER_MODEL_FREEZE',
        'formalization_status': 'PARTIAL_SOURCE_TRANSPORT' if critical_loss or uncertain else 'SCOPED_TRANSPORT_COMPLETE',
        'full_formalization': False, 'source_status': 'HYPOTHESIS', 'source_claim_verified': False,
        'proof_status': 'unverified', 'execution_permission': {'allowed': False}}


def hypothesis_families(rows: list[dict]) -> list[dict]:
    """Group identical projected behaviour; do not multiply evidence by bindings."""
    groups: dict[str, dict] = {}
    for row in rows:
        p = row['payload']; m = p['model']; a = p['check']['analysis']
        # Addresses and hypothesis labels remain provenance, not behaviour.
        profiles = [{'criterion': o['criterion'], 'features': o['features'],
            'samples': [v['values'] for v in o['samples']]} for o in m['observer'].get('observers', [])]
        signature = digest({'target': a['operation_table_sha256'], 'profiles': profiles,
            'claims': [{k: v[k] for k in ('relation_kind', 'polarity', 'modality', 'order_kind', 'claim')}
                | {'source_claim': {k: v['source_claim'][k] for k in ('mode', 'speaker', 'stance', 'connective', 'source_status')}}
                for v in m['observer'].get('source_annotations', [])]})
        if m['observer'].get('inference') is not None:
            signature = digest([signature, m['observer']['inference']])
        group = groups.setdefault(signature, {'family_hash': signature, 'result_ids': [],
            'model_hashes': [], 'independent_evidence_count': 0, 'source_verified': False})
        group['result_ids'].append(row['id']); group['model_hashes'].append(m['compiled_hash'])
    return list(groups.values())
