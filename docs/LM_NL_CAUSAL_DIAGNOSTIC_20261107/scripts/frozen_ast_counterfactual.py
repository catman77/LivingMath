#!/usr/bin/env python3
"""Independent, no network/LLM, frozen AST counterfactual diagnostic.

Read SHA-frozen reference fixtures from the last deliverable, verify that
White Star B's candidate AST hashes can be reproduced via ONE primitive
quantifier-spine swap on the *same* base AST, without any White Star data.

Not a live production provider-receipt replay; ref ASTs are assistant-authored
precommitted fixtures whose hashes happen to match the prior live candidates.
"""
import argparse, copy, hashlib, itertools, json, pathlib, zipfile


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def digest(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def swap_first_two_binders(ast):
    q1, inner = copy.deepcopy(ast), ast.get('body', {})
    if q1.get('quant') != 'forall' or inner.get('quant') != 'exists':
        raise ValueError('fixture must be a forall-exists quantifier spine')
    out = copy.deepcopy(inner)
    first = {k: v for k, v in q1.items() if k != 'body'}
    second = {k: v for k, v in out.items() if k != 'body'}
    return {**second, 'body': {**first, 'body': copy.deepcopy(out['body'])}}


def truth(ast, env, d1, d2, relation):
    if 'quant' in ast:
        domain = d1 if ast['sort'] == relation['sort1'] else d2
        vals = [truth(ast['body'], {**env, ast['var']: v}, d1, d2, relation) for v in domain]
        if ast['quant'] == 'forall':
            return all(vals)
        if ast['quant'] == 'exists':
            return any(vals)
        raise ValueError('unknown quantifier')
    if 'var' in ast:
        return env[ast['var']]
    if 'pred' in ast:
        if ast['pred'] != relation['name']:
            raise ValueError('unexpected predicate')
        x,y = [truth(term, env, d1, d2, relation) for term in ast['args']]
        return (x,y) in relation['pairs']
    if 'and' in ast: return all(truth(x, env, d1, d2, relation) for x in ast['and'])
    if 'or' in ast: return any(truth(x, env, d1, d2, relation) for x in ast['or'])
    if 'not' in ast: return not truth(ast['not'], env, d1, d2, relation)
    if 'eq' in ast: return truth(ast['eq'][0], env, d1, d2, relation) == truth(ast['eq'][1], env, d1, d2, relation)
    raise ValueError('unknown node')


def models_difference(a, b, sig):
    pred, sorts = next(iter(sig['predicates'].items()))
    disagreements = 0
    total = 0
    example = None
    for n in (1,2,3):
        D = range(n)
        pairs = list(itertools.product(D,D))
        for bits in range(1 << (n*n)):
            rel = {'name':pred, 'sort1':sorts[0], 'pairs':{p for j,p in enumerate(pairs) if (bits>>j)&1}}
            t1 = truth(a,{},D,D,rel)
            t2 = truth(b,{},D,D,rel)
            total += 1
            if t1 != t2:
                disagreements += 1
                if example is None:
                    example = {'domain_size_each':n, 'relation_pairs':sorted([list(p) for p in rel['pairs']]), 'narrow_truth':t1, 'wide_truth':t2}
    return total, disagreements, example


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source-zip', default=None, help='Optional original evidence ZIP; by default use bundled fixtures')
    ap.add_argument('--out', default=str(pathlib.Path(__file__).resolve().parents[1] / 'results' / 'frozen_ast_counterfactual.json'))
    args=ap.parse_args()
    if args.source_zip:
        with zipfile.ZipFile(args.source_zip) as z:
            root='LM_NL_INDEPENDENT_EVAL_20261107/'
            gold=json.loads(z.read(root+'GOLD_AMBIGUOUS_PRECOMMITTED.json'))
            scores=json.loads(z.read(root+'AMBIGUITY_SCORES_PARTIAL.json'))
    else:
        root=pathlib.Path(__file__).resolve().parents[1] / 'fixtures'
        gold=json.loads((root/'GOLD_AMBIGUOUS_PRECOMMITTED.json').read_text(encoding='utf-8'))
        scores=json.loads((root/'AMBIGUITY_SCORES_PARTIAL.json').read_text(encoding='utf-8'))
    by_id={row['id']:row for row in scores['source_rows']}
    rows=[]
    for ex in gold['corpus']:
        if ex['id']=='U26': continue  # invalid original oracle, frozen and excluded
        narrow, original_wide=ex['allowed_formulae']
        sw=swap_first_two_binders(narrow)
        row=by_id[ex['id']]
        nsha=digest(narrow); wsha=digest(sw)
        if nsha != row['narrow_ast_sha256_A_and_B']:
            raise AssertionError(f'Base AST SHA does not match live source-only B candidate for {ex["id"]}')
        if wsha != row['wide_ast_sha256_B']:
            raise AssertionError(f'Deterministic swap fails to match actual B candidate SHA for {ex["id"]}')
        if wsha != digest(original_wide):
            raise AssertionError(f'Deterministic swap differs from precommitted wide gold for {ex["id"]}')
        models,disagreements,countermodel=models_difference(narrow,sw,ex['signature'])
        assert models==530 and disagreements==176,(ex['id'],models,disagreements)
        rows.append({'id':ex['id'],'source':ex['text'],'base_ast_sha256':nsha,'white_star_B_wide_sha256':row['wide_ast_sha256_B'],'frozen_base_swap_sha256':wsha,'matched_exactly':True,'models_checked':models,'models_distinguishing':disagreements,'countermodel':countermodel})
    output={'schema':'lm-frozen-ast-counterfactual/1','status':'PASS','run_mode':'LOCAL_DETERMINISTIC_NO_LLM_NO_WHITE_STAR', 'scope':'narrow base AST originally authored in precommit and hash-matched to actual prior source-only model output; not a frozen production provider receipt', 'number_of_cases':len(rows), 'swapped_candidates_matching_actual_B':sum(x['matched_exactly'] for x in rows),'runtime_LLM_calls':0,'runtime_white_star_calls':0,'oracle_U26_status':'EXCLUDED_INVALID_PRECOMMITTED_ORACLE', 'rows':rows}
    path=pathlib.Path(args.out);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"{output['status']} {len(rows)}/{len(rows)} wide candidate SHA match via plain quantifier swap; LLM=0; White Star=0")
    for r in rows: print(r['id'],r['models_distinguishing'],'/',r['models_checked'],r['frozen_base_swap_sha256'][:20])


if __name__=='__main__':main()
