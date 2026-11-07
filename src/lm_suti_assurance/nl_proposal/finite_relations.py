"""Independent finite FOL truth-set comparison, never semantic licensing."""
from itertools import product
from ..core import digest
from ..formal_bridge.fol import typecheck


def value(ast: dict, model: dict, tick, environment: dict | None = None) -> bool:
    env = {} if environment is None else environment
    tick()
    if 'pred' in ast:
        return tuple(env[t['var']] for t in ast['args']) in model['relations'][ast['pred']]
    if 'eq' in ast:
        return env[ast['eq'][0]['var']] == env[ast['eq'][1]['var']]
    if 'not' in ast:
        return not value(ast['not'], model, tick, env)
    if 'and' in ast:
        return all(value(p, model, tick, env) for p in ast['and'])
    if 'or' in ast:
        return any(value(p, model, tick, env) for p in ast['or'])
    results = (value(ast['body'], model, tick, {**env, ast['var']: x})
               for x in model['domains'][ast['sort']])
    return all(results) if ast['quant'] == 'forall' else any(results)


def relation(base: dict, candidate: dict, signature: dict, model_class: dict, tick) -> dict:
    result = {'status': 'UNKNOWN_BOUND', 'models_checked': 0, 'different_models': 0,
              'base_true_models': 0, 'candidate_true_models': 0,
              'base_true_candidate_false': None, 'base_false_candidate_true': None,
              'model_class': model_class, 'scope': 'EXPLICIT_UNIFORM_NONEMPTY_FINITE_DOMAINS',
              'equivalence_claim': 'UNIVERSAL_EQUIVALENCE_NOT_CLAIMED',
              'semantic_alignment_status': 'PROPOSED', 'execution_permission': False}
    if any(typecheck(a, signature)['status'] != 'TYPED' for a in (base, candidate)):
        return {**result, 'reason': 'UNSUPPORTED_OR_ILL_TYPED_REPRESENTATION'}
    try:
        for size in model_class['domain_sizes']:
            domains = {s: [s + ':' + str(i) for i in range(size)] for s in signature['sorts']}
            cells = [(p, row) for p, sorts in sorted(signature['predicates'].items())
                     for row in product(*(domains[s] for s in sorts))]
            if len(cells) > model_class['max_relation_cells']:
                return {**result, 'reason': 'RELATION_CELL_BOUND'}
            for bits in product((False, True), repeat=len(cells)):
                tick()
                if result['models_checked'] >= model_class['max_models']:
                    return {**result, 'reason': 'MODEL_COUNT_BOUND'}
                model = {'domains': domains, 'relations': {p: set() for p in signature['predicates']}}
                for (p, row), yes in zip(cells, bits):
                    if yes:
                        model['relations'][p].add(row)
                a = value(base, model, tick)
                b = value(candidate, model, tick)
                result['models_checked'] += 1
                result['different_models'] += a != b
                result['base_true_models'] += a
                result['candidate_true_models'] += b
                direction = 'base_true_candidate_false' if a and not b else 'base_false_candidate_true' if b and not a else None
                if direction and result[direction] is None:
                    witness = {'domains': domains, 'relations': {p: [list(x) for x in sorted(xs)] for p, xs in model['relations'].items()}, 'world': 'closed'}
                    result[direction] = {'finite_countermodel': witness, 'model_sha256': digest(witness),
                                         'base_truth': a, 'candidate_truth': b}
    except TimeoutError:
        return {**result, 'reason': 'CPU_BOUND'}
    lower = result['base_true_candidate_false'] is not None
    upper = result['base_false_candidate_true'] is not None
    result['status'] = ('INCOMPARABLE_ON_BOUND' if lower and upper else
                        'STRONGER_ON_BOUND' if lower else 'WEAKER_ON_BOUND' if upper else 'SAME_ON_BOUND')
    result['finite_status'] = 'FINITE_RELATION_CHECKED'
    return result
