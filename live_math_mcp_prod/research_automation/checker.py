"""Independent acceptance checker. Does not import the planner or its congruence audit."""
from dataclasses import dataclass
from typing import Any

from davcore.adapters import Adapter
from davcore.ast import Eq, Var, canonical, digest
from davcore.finite import Limit, Meter
from davcore.models import Budget
from .contract import Hypothesis


def check_refinement(base: Adapter, proposal: Adapter, budget: Budget) -> dict:
    """Check preservation and every original continuation with a separately built map."""
    original = base.spec.model_dump()
    replacement = proposal.spec.model_dump()
    initial_mask = (1 << base.width) - 1 if original['mask'] is None else original['mask']
    mask = (1 << proposal.width) - 1 if replacement['mask'] is None else replacement['mask']
    fixed_original = {k: v for k, v in original.items() if k != 'mask'}
    fixed_replacement = {k: v for k, v in replacement.items() if k != 'mask'}
    if fixed_original != fixed_replacement or base.states() != proposal.states() or base.ops != proposal.ops:
        return {'status': 'rejected', 'reason': 'SOURCE_DOMAIN_OPERATION_OR_ASSUMPTION_CHANGED'}
    if mask & initial_mask != initial_mask:
        return {'status': 'rejected', 'reason': 'ORIGINAL_DISTINCTIONS_LOST'}
    if len(base.states()) > budget.max_states:
        return {'status': 'timeout', 'reason': 'STATE_LIMIT'}
    meter = Meter(budget)
    rows = []
    try:
        for operation in base.ops:
            continuations: dict[int, tuple[int, int]] = {}
            for x in base.states():
                meter.tick()
                y = meter.apply(base, operation, x)
                obs, following = x & mask, y & mask
                previous = continuations.get(obs)
                if previous is not None and previous[1] != following:
                    return {'status': 'rejected', 'reason': 'CONTINUATION_STILL_AMBIGUOUS',
                            'counterexample': {'operation': operation, 'states': [previous[0], x],
                                              'observed_continuations': [previous[1], following]}}
                continuations[obs] = (x, following)
                rows.append([operation, x, y, obs, following])
    except Limit as exc:
        return {'status': 'timeout', 'reason': str(exc)}
    return {'status': 'accepted', 'reason': 'FINITE_CONGRUENCE_AND_ORIGINAL_DISTINCTIONS_REPLAYED',
            'observer_mask': mask, 'preserved_initial_mask': initial_mask, 'tested_states': len(base.states()),
            'operations': list(base.ops), 'complete_replay_sha256': digest(rows),
            'assumptions': base.metadata['assumptions'], 'new_observation_of_external_world': False,
            'metrics': meter.metrics()}


def check_law_result(a: Adapter, formula, claimed: dict, budget: Budget) -> dict:
    """Independently replay a counterexample or every initial valuation; no dependency on SMT."""
    status = claimed.get('status')
    if status not in {'proved', 'refuted'}:
        return {'status': 'rejected', 'reason': 'NO_DEFINITIVE_FINITE_CLAIM'}
    if formula.equality == 'full_state' and a.spec.mask is not None:
        return {'status': 'rejected', 'reason': 'PROJECTION_CANNOT_CLAIM_STATE_IDENTITY'}
    if status == 'proved' and a.spec.fidelity != 'full':
        return {'status': 'rejected', 'reason': 'EMPIRICAL_ENUMERATION_IS_NOT_COMPLETE_SEMANTICS'}
    xs = [claimed.get('counterexample', {}).get('state')] if status == 'refuted' else list(a.states())
    if len(xs) > budget.max_states or any(not a.valid_state(x) for x in xs):
        return {'status': 'rejected', 'reason': 'INITIAL_STATE_SCOPE_MISMATCH'}
    meter = Meter(budget)
    try:
        for x in xs:
            def apply(t):
                if isinstance(t, Var):
                    return x
                return meter.apply(a, t.operation, apply(t.argument))

            def equal(e):
                left, right = apply(e.left), apply(e.right)
                return (a.observe(left) == a.observe(right)) if formula.equality == 'observation' else left == right
            body = formula.body
            holds = equal(body) if isinstance(body, Eq) else not equal(body.premise) or equal(body.conclusion)
            if (status == 'proved' and not holds) or (status == 'refuted' and holds):
                return {'status': 'rejected', 'reason': 'CLAIM_DISAGREES_WITH_INDEPENDENT_REPLAY', 'state': x}
    except (ValueError, TypeError) as exc:
        return {'status': 'rejected', 'reason': str(exc)}
    except Limit as exc:
        return {'status': 'timeout', 'reason': str(exc)}
    return {'status': 'accepted', 'reason': 'INDEPENDENT_FINITE_FORMULA_REPLAY', 'adapter_relative_status': status,
            'tested_initial_states': len(xs), 'claim_digest': digest(claimed), 'metrics': meter.metrics()}


@dataclass(frozen=True)
class InputAnalysis:
    outcome: str
    result: dict


def analyze_inputs(problem, inputs: list[dict]) -> InputAnalysis:
    """Retain all contradictory declarations; absent and null facts never become zero."""
    by_feature: dict[str, dict[str, dict[str, Any]]] = {}
    origins: dict[str, list[int]] = {}
    for row in inputs:
        for fact in row['payload']['input']['facts']:
            if fact['value'] is None:
                continue
            feature = fact['feature']
            key = canonical([fact['unit'], fact['value']])
            by_feature.setdefault(feature, {})[key] = fact
            origins.setdefault(feature, []).append(row['id'])
    conflicts = sorted(k for k, values in by_feature.items() if len(values) > 1)
    relevant = set(problem.required_features)
    if problem.kind == 'identify_model':
        relevant.update(p.feature for h in problem.hypotheses for p in h.predictions)
        relevant.update('model_target/' + h.model_id for h in problem.hypotheses if h.target is None)
    conflicts = [name for name in conflicts if name in relevant]
    if conflicts:
        return InputAnalysis('REQUIRES_REVIEW', {'outcome': 'CONTRADICTORY_REFERENCED_INPUTS', 'conflicting_features': conflicts,
            'source_record_ids': {k: origins[k] for k in conflicts}, 'condition_to_continue': 'A new scoped source/review must resolve the conflicting declarations; old evidence is retained.'})
    facts = {k: next(iter(values.values())) for k, values in by_feature.items()}
    if problem.kind == 'input_gap':
        missing = sorted(set(problem.required_features) - set(facts))
        return InputAnalysis('WAITING_FOR_INPUT' if missing else 'COMPLETED', {
            'outcome': 'INPUT_REQUIRED' if missing else 'INPUTS_AVAILABLE_UNVERIFIED', 'required_features': missing,
            'available_features': sorted(set(problem.required_features) & set(facts)),
            'external_claim_verified': False, 'unknown_refs': problem.unknown_refs})
    survivors: list[Hypothesis] = []
    excluded: list[Hypothesis] = []
    unit_conflicts: list[str] = []
    for h in problem.hypotheses:
        definition = facts.get('model_target/' + h.model_id)
        if h.target is None and definition is not None:
            if definition['unit'] is not None:
                return InputAnalysis('REQUIRES_REVIEW', {'outcome': 'TARGET_DEFINITION_IS_NOT_A_MEASURED_QUANTITY'})
            h = h.model_copy(update={'target': definition['value']})
        mismatches = []
        for p in h.predictions:
            if p.feature not in facts:
                continue
            f = facts[p.feature]
            if p.unit != f['unit']:
                unit_conflicts.append(p.feature)
            elif canonical(p.value) != canonical(f['value']):
                mismatches.append(p.feature)
        (excluded if mismatches else survivors).append(h)
    if unit_conflicts:
        return InputAnalysis('REQUIRES_REVIEW', {'outcome': 'INPUT_UNIT_MISMATCH', 'features': sorted(set(unit_conflicts))})
    if not survivors:
        return InputAnalysis('REQUIRES_REVIEW', {'outcome': 'ALL_CANDIDATE_MODELS_CONTRADICT_INPUT',
            'excluded_models': [h.model_id for h in excluded], 'source_record_ids': [r['id'] for r in inputs]})
    undefined = [h.model_id for h in survivors if h.target is None]
    result = {'surviving_models': [h.model_id for h in survivors], 'excluded_models': [h.model_id for h in excluded],
              'external_claim_verified': False, 'assurance': 'RELATIVE_TO_DECLARED_MODELS_AND_INPUTS'}
    if undefined:
        return InputAnalysis('WAITING_FOR_INPUT', {**result, 'outcome': 'MODEL_TARGETS_UNDEFINED',
            'required_features': ['model_target/' + name for name in undefined], 'models_requiring_target_definition': undefined})
    if len({canonical(h.target) for h in survivors}) == 1:
        return InputAnalysis('COMPLETED', {**result, 'outcome': 'MODEL_IDENTIFIED_UNDER_DECLARED_INPUTS',
            'target': survivors[0].target, 'multiple_models_can_remain': len(survivors) > 1})
    features = sorted({p.feature for h in survivors for p in h.predictions} - set(facts))
    separating = []
    for feature in features:
        values = [next((canonical([p.unit, p.value]) for p in h.predictions if p.feature == feature), None) for h in survivors]
        if len(set(values)) > 1 and None not in values:
            separating.append(feature)
    return InputAnalysis('WAITING_FOR_INPUT', {**result,
        'outcome': 'DISCRIMINATING_INPUT_REQUIRED' if separating else 'MODELS_OBSERVATIONALLY_UNDERDETERMINED',
        'required_features': separating, 'unmeasured_features': features,
        'condition_to_continue': 'Provide a scoped discriminating observation or a newly specified independently testable model.'})
