"""Actual finite binding enumeration and source-path composition, without case tables."""
from itertools import islice, product
from math import prod

from davcore.ast import digest, Formula, Eq, Implies, Apply, term
from .contract import coordinate


def enumerate_bindings(dimensions: list[dict], constraints: list[dict] | None = None, bound: int = 32, *, project: str = 'LM_QA_REPAIR004') -> dict:
    from davcore.service import Service
    Service.project(project)
    if not 1 <= bound <= 32:
        raise ValueError('BINDING_BOUND')
    by = {d['id']: d for d in dimensions}
    if len(by) != len(dimensions):
        raise ValueError('DUPLICATE_BINDING_DIMENSION')
    values = {k: list(dict.fromkeys(d['values'])) for k, d in by.items()}
    for c in constraints or []:
        if c['dimension'] not in by or c['scope'] != by[c['dimension']]['scope']:
            raise ValueError('CROSS_SCOPE_CONSTRAINT')
        values[c['dimension']] = [v for v in values[c['dimension']] if v in c['allowed_values']]
    total = prod(len(v) for v in values.values())
    bs = []
    for assignment in islice(product(*values.values()), bound):
        record = {'assignments': dict(zip(values, assignment)), 'status': 'HYPOTHESIS',
                  'assumptions': ['Assignment is a conditional candidate, not a source FACT.'], 'project': project}
        record['id'] = 'b_' + digest(record)[:24]; bs.append(record)
    return {'bindings': bs, 'candidate_family_version': digest([dimensions, constraints or []]),
            'search_bound': bound, 'total_in_declared_finite_family': total, 'truncated': total > bound,
            'enumeration_complete_within_family': total <= bound, 'unresolved_dimensions': [k for k, v in values.items() if len(v) > 1],
            'universal_interpretation_claim': False, 'authorship': 'SYMBOLIC_CARTESIAN_SEARCH'}


def generate_queries(premises: list[dict], model: dict, *, include_direct: bool = False, limit: int = 16) -> list[dict]:
    if model['status'] != 'COMPILED_CONDITIONAL_MODEL':
        return []
    index = {tuple(c): i for i, c in enumerate(model['coordinates'])}
    edges = [(coordinate(p['src']), coordinate(p['dst']), i, p) for i, p in enumerate(premises)
             if p['id'] not in model.get('inactive_premise_ids',[])]
    primitive_pairs = {(e[0], e[1]) for e in edges}
    out: list[dict] = []; seen = set()

    def walk(path, visited):
        first, last = path[0][0], path[-1][1]
        candidate = (include_direct or len(path) >= 2) and first != last
        if any(e[3].get('semantics') for e in path):
            from .scoped import composable
            candidate = candidate and composable([e[3] for e in path])
        if len(path) >= 2 and (first, last) in primitive_pairs:
            candidate = False
        if candidate:
            ids = [e[3]['id'] for e in path]
            key = (first, last, tuple(ids))
            if key not in seen and len(out) < limit:
                seen.add(key); expression = term('Id')
                for e in path:
                    expression = Apply(operation='R' + str(e[2]), argument=expression)
                formula = Formula(body=Implies(premise=Eq(left=term('S' + str(index[first])), right=term('One')),
                    conclusion=Eq(left=Apply(operation='S' + str(index[last]), argument=expression), right=term('One'))))
                q = {'formula': formula.canonical_ast(), 'premise_ids': ids,
                     'coordinate_contract_hash': digest([model['coordinates'], model['source_hashes'], model['observer']]),
                     'src_predicate': first[0], 'dst_predicate': last[0], 'depth': len(path),
                     'dependency_DAG': [{'premise_id': e[3]['id'], 'premise_unit': e[3]['premise_unit'],
                                         'source_refs': e[3]['source_refs'], 'scope': e[0][1],
                                         'modality': e[0][3], 'stage': e[0][2]} for e in path],
                     'authorship': 'SYMBOLIC_SOURCEGRAPH_PATH_SEARCH', 'H_status': 'HYPOTHESIS'}
                q['query_id'] = 'q_' + digest(q)[:24]; out.append(q)
        if len(path) == 3:
            return
        for e in edges:
            if e[0] == last and e[1] not in visited:
                walk(path + [e], visited | {e[1]})
    for e in edges:
        walk([e], {e[0], e[1]})
    return out


def summarize(family: dict, outcomes: list[dict]) -> dict:
    if not family['bindings']:
        return {'status': 'INCONSISTENT_PREMISES', 'universal_claim': False}
    if family['truncated'] or len(outcomes) != len(family['bindings']) or any(o.get('status') != 'CHECKED' for o in outcomes):
        return {'status': 'COMPUTATION_UNKNOWN', 'reason': 'TRUNCATED_FAMILY_OR_INCOMPLETE_COMPUTATION', 'universal_claim': False}
    vals = {o['value'] for o in outcomes}
    return {'status': 'BINDING_SENSITIVE' if len(vals) > 1 else 'ROBUST_WITHIN_CANDIDATE_SET',
            'values': sorted(vals), 'witnesses': [next(o for o in outcomes if o['value'] == v) for v in sorted(vals)],
            'universal_claim': False, 'scope': 'Only the declared complete finite candidate family'}
