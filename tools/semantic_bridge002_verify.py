"""Independent stdlib-only checker for actual PATCH002 bundles and finite witnesses.

No production package imports. This verifies formal evidence, never source meaning.
"""
import argparse
import hashlib
import json
from itertools import product, islice
from pathlib import Path


def canonical(v):
    return json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(v):
    return hashlib.sha256(canonical(v).encode()).hexdigest()


def normalized(phi, sig, nnf=False):
    assert type(sig) is dict and set(sig) == {'sorts', 'predicates'}
    assert type(sig['sorts']) is list and 1 <= len(sig['sorts']) <= 4
    assert all(type(s) is str and 0 < len(s) <= 128 for s in sig['sorts'])
    assert len(set(sig['sorts'])) == len(sig['sorts'])
    assert type(sig['predicates']) is dict and len(sig['predicates']) <= 4
    assert all(type(n) is str and n and type(ss) is list and 1 <= len(ss) <= 3 and all(s in sig['sorts'] for s in ss)
               for n, ss in sig['predicates'].items())
    count = 0
    def walk(p, env, depth, negative=False, nesting=0):
        nonlocal count
        count += 1
        assert count <= 128 and nesting <= 16 and type(p) is dict
        def term(t):
            assert type(t) is dict and set(t) == {'var'} and type(t['var']) is str and t['var'] in env
            pos, sort = env[t['var']]
            return depth - pos - 1, sort
        if set(p) == {'quant', 'var', 'sort', 'body'}:
            assert p['quant'] in ('forall', 'exists') and p['sort'] in sig['sorts'] and type(p['var']) is str and p['var'] and p['var'] not in env
            q = {'forall': 'exists', 'exists': 'forall'}[p['quant']] if negative else p['quant']
            return ['quant', q, p['sort'], walk(p['body'], {**env, p['var']: (depth, p['sort'])}, depth + 1, negative, nesting + 1)]
        if set(p) == {'not'}:
            child = walk(p['not'], env, depth, not negative if nnf else False, nesting + 1)
            return child if nnf else ['not', child]
        if set(p) in ({'and'}, {'or'}):
            op = 'and' if 'and' in p else 'or'
            assert type(p[op]) is list and 1 <= len(p[op]) <= 16
            key = {'and': 'or', 'or': 'and'}[op] if negative else op
            return [key, [walk(x, env, depth, negative, nesting + 1) for x in p[op]]]
        if set(p) == {'pred', 'args'}:
            assert p['pred'] in sig['predicates'] and type(p['args']) is list
            ts = [term(t) for t in p['args']]
            assert [s for _, s in ts] == sig['predicates'][p['pred']]
            atom = ['pred', p['pred'], [i for i, _ in ts]]
        else:
            assert set(p) == {'eq'} and type(p['eq']) is list and len(p['eq']) == 2
            ts = [term(t) for t in p['eq']]; assert ts[0][1] == ts[1][1]
            atom = ['eq', [i for i, _ in ts]]
        return ['not', atom] if negative else atom
    return walk(phi, {}, 0)


def verify_certificate(a, b, sig, cert):
    common = {'input_formula_sha256_left': digest(a), 'input_formula_sha256_right': digest(b), 'signature_sha256': digest(sig)}
    x, y = normalized(a, sig), normalized(b, sig)
    rule = cert['rule']
    if rule == 'ALPHA_NORMALIZATION':
        assert canonical(x) == canonical(y)
        expected = {'rule': rule, 'checker_version': 'sb-alpha/1', **common,
                    'canonical_sha256_left': digest(x), 'canonical_sha256_right': digest(y), 'result': 'PROVED_ALPHA_EQ'}
    else:
        x, y = normalized(a, sig, True), normalized(b, sig, True)
        if rule == 'NEGATION_NORMAL_FORM_EQUIVALENCE':
            assert canonical(x) == canonical(y)
            expected = {'rule': rule, 'checker_version': 'sb-nnf/1', **common,
                        'normal_sha256_left': digest(x), 'normal_sha256_right': digest(y), 'result': 'PROVED_NEGATION_NORMAL_FORM_EQ'}
        else:
            assert rule == 'SAME_PREFIX_BOOLEAN_MONOTONICITY'
            def strip(p):
                prefix = []
                while p[0] == 'quant':
                    prefix.append([p[1], p[2]]); p = p[3]
                return prefix, p
            pa, x = strip(x); pb, y = strip(y); assert pa == pb
            atoms = {}
            def collect(p):
                if p[0] in ('pred', 'eq'): atoms[canonical(p)] = p
                elif p[0] == 'not': collect(p[1])
                else:
                    assert p[0] in ('and', 'or')
                    for item in p[1]: collect(item)
            collect(x); collect(y); keys = sorted(atoms); assert len(keys) <= 10
            def val(p, row):
                if p[0] in ('pred', 'eq'): return row[canonical(p)]
                if p[0] == 'not': return not val(p[1], row)
                answers = [val(q, row) for q in p[1]]
                return all(answers) if p[0] == 'and' else any(answers)
            rows = []
            for bits in product((False, True), repeat=len(keys)):
                row = dict(zip(keys, bits)); p, q = val(x, row), val(y, row)
                assert not (p and not q)
                rows.append([list(bits), p, q])
            expected = {'rule': rule, 'checker_version': 'sb-prefix-boolean/2', **common,
                        'prefix_quantifiers_and_sorts': pa, 'matrix_sha256_left': digest(x), 'matrix_sha256_right': digest(y),
                        'atoms': [atoms[k] for k in keys], 'rows_checked': len(rows), 'truth_table_sha256': digest(rows),
                        'equality_treatment': 'INDEPENDENT_BOOLEAN_ATOM_SUFFICIENT_ONLY', 'result': 'PROVED_ENTAILMENT'}
    assert canonical(expected) == canonical(cert)
    return digest(cert)


def evaluate(p, model, env=None):
    if model['world'] == 'open': return None
    env = {} if env is None else env
    if 'pred' in p: return [env[t['var']] for t in p['args']] in model['relations'][p['pred']]
    if 'eq' in p: return env[p['eq'][0]['var']] == env[p['eq'][1]['var']]
    if 'not' in p: return not evaluate(p['not'], model, env)
    if 'and' in p: return all(evaluate(q, model, env) for q in p['and'])
    if 'or' in p: return any(evaluate(q, model, env) for q in p['or'])
    values = [evaluate(p['body'], model, {**env, p['var']: v}) for v in model['domains'][p['sort']]]
    return all(values) if p['quant'] == 'forall' else any(values)


def worlds(sig):
    for size in (1, 2):
        domains = {s: [s + ':' + str(i) for i in range(size)] for s in sorted(sig['sorts'])}
        cells = [(n, list(t)) for n, sorts in sorted(sig['predicates'].items()) for t in product(*(domains[s] for s in sorts))]
        if len(cells) > 16: return
        for bits in product((False, True), repeat=len(cells)):
            rel = {n: [] for n in sorted(sig['predicates'])}
            for (n, row), bit in zip(cells, bits):
                if bit: rel[n].append(row)
            yield {'domains': domains, 'relations': rel, 'world': 'closed'}


def verify_bundle(bundle):
    assert bundle['schema'] == 'semantic-bridge-replay-bundle/1'
    packet, result = bundle['packet'], bundle['result']
    assert digest(packet) == bundle['packet_sha256'] and digest(result) == bundle['result_sha256']
    assert result['LLM_calls'] == 0 and result['execution_permission'] is False
    if bundle['operation'] == 'register':
        assert result['semantic_adjudication'] == 'NOT_EVALUATED'
        assert all(h['source_alignment_status'] in ('PROPOSED', 'LANGUAGE_INSUFFICIENT') for h in result['hypotheses'])
        return {'operation': 'register', 'status': 'PASS', 'hypotheses': len(result['hypotheses'])}
    payload = packet['payload']; batch = payload['batch']; sig = batch['target_signature']
    hs = {h['hypothesis_ref']: h for h in batch['hypotheses']}; certs = set(); cms = 0; decided = 0
    n = result['checks']['model_enumerations']; assert type(n) is int and 0 <= n <= payload['budget'].get('max_models', 512)
    models = list(islice(worlds(sig), n)); assert len(models) == n and len({digest(m) for m in models}) == n
    for edge in result['graph']['relations']:
        a, b = [hs[edge[k]] for k in ['left_ref', 'right_ref']]
        if 'certificate' in edge.get('alpha', {}): certs.add(verify_certificate(a['formula_ast'], b['formula_ast'], sig, edge['alpha']['certificate']))
        for key, left, right, label in [('A_IMPLIES_B', a, b, 'COUNTERMODEL_A_NOT_B'), ('B_IMPLIES_A', b, a, 'COUNTERMODEL_B_NOT_A')]:
            d = edge['directions'][key]
            if d['status'] in ('PROVED_ENTAILMENT', 'PROVED_ALPHA_EQ'):
                certs.add(verify_certificate(left['formula_ast'], right['formula_ast'], sig, d['certificate']))
                assert d['models_checked'] == 0; decided += 1
            elif d['status'] == label:
                cm = next(c for c in edge['countermodels'] if c['status'] == label); model = cm['model']
                assert model['world'] == 'closed' and digest(model) == cm['model_sha256'] == cm['model_ref'] == d['counterexample_ref']
                assert evaluate(left['formula_ast'], model) is True and evaluate(right['formula_ast'], model) is False
                assert all(evaluate(phi, model) is True for phi in a['assumptions'] + b['assumptions'])
                expected = [evaluate(h['formula_ast'], model) for h in [a, b]]; assert expected == cm['truth_vector']
                index = next(i + 1 for i, m in enumerate(models) if digest(m) == digest(model))
                assert d['models_checked'] == index
                for earlier in models[:index - 1]:
                    if all(evaluate(phi, earlier) is True for phi in a['assumptions'] + b['assumptions']):
                        assert not (evaluate(left['formula_ast'], earlier) and not evaluate(right['formula_ast'], earlier))
                cms += 1; decided += 1
            else:
                assert d['status'] in ('UNKNOWN_BOUND', 'NO_COUNTERMODEL_WITHIN_BOUND', 'TYPE_REJECTED')
                assert 'certificate' not in d
                assert d['models_checked'] <= n
        assert edge['status'] != 'PROVED_LOGICAL_EQ' or all(d['status'] in ('PROVED_ENTAILMENT', 'PROVED_ALPHA_EQ') for d in edge['directions'].values())
    coverage = result['checks']['directional_coverage']; requested = len(payload['pairs']) * 2
    assert coverage == {'requested': requested, 'completed': decided, 'undecided': requested - decided}
    for cell in result['scenario_vectors']:
        h = next(h for h in hs.values() if h['client_id'] == cell['client_id'])
        model = next(m['model'] for m in payload['models'] if m['model_ref'] == cell['model_ref'])
        try: normalized(h['formula_ast'], sig); truth = evaluate(h['formula_ast'], model); status = 'UNKNOWN' if truth is None else 'TRUE' if truth else 'FALSE'
        except (KeyError, AssertionError): status = 'ILL_TYPED'
        assert status == cell['formula_truth']
        values = []
        for assumption in h['assumptions']:
            try: normalized(assumption, sig); values.append(evaluate(assumption, model))
            except (KeyError, AssertionError): values.append(None)
        applicability = 'CONTEXT_INCOMPATIBLE' if any(v is False for v in values) else 'UNKNOWN_CONTEXT' if any(v is None for v in values) else 'APPLICABLE'
        assert applicability == cell['applicability']
    assert all(o['status'] == 'OPEN' for h in result['obligations'] for o in h['items'])
    return {'operation': 'analyze', 'status': 'PASS', 'unique_certificates': len(certs), 'countermodels': cms,
            'scenarios': len(result['scenario_vectors']), 'directional_coverage': coverage, 'unique_models': n,
            'source_semantics': 'NOT_EVALUATED'}


def main():
    p = argparse.ArgumentParser(); p.add_argument('bundles', type=Path, nargs='+'); p.add_argument('--output', type=Path, required=True); a = p.parse_args()
    rows = [{'file': str(f), **verify_bundle(json.loads(f.read_text()))} for f in a.bundles]
    report = {'status': 'PASS', 'stdlib_only_no_production_imports': True, 'rows': rows}
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n'); print(json.dumps({'status': 'PASS', 'bundles': len(rows)}))
if __name__ == '__main__': main()
