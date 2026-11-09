"""Real MCP PATCH002 acceptance, exact receipts and independently checked finite data."""
import argparse
import asyncio
import base64
import copy
import hashlib
import json
import sys
from itertools import permutations
from pathlib import Path

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'live_math_mcp_prod'))
from dav_acceptance import TappedStream
from semantic_bridge002_verify import verify_bundle, digest


async def main(a):
    out = a.output
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    save = lambda name, v: (out / name).write_text(json.dumps(v, ensure_ascii=False, indent=2) + '\n')
    checks, runs, receipts, evidence = [], [], [], []
    fixtures = json.loads((ROOT / 'docs/SEMANTIC_BRIDGE_PATCH002_20261109/fixtures/PATCH002_CASES.json').read_text())
    cases = {c['id']: c for c in fixtures['logical_cases']}

    def check(name, ok, **detail):
        checks.append({'name': name, 'status': 'PASS' if ok else 'FAIL', 'evidence': 'REAL_MCP_EXECUTED', **detail})
        save('checks.json', checks)
        assert ok, (name, detail)

    headers = {'Host': 'livingmath.example'} if a.loopback else {}
    async with httpx.AsyncClient(headers=headers, timeout=180) as http:
        async with streamable_http_client(a.endpoint, http_client=http) as (rd, wr, _):
            async with ClientSession(TappedStream(rd, out / 'wire.jsonl', 'server_to_client'), TappedStream(wr, out / 'wire.jsonl', 'client_to_server')) as c:
                save('initialize.json', (await c.initialize()).model_dump(mode='json'))
                tools = (await c.list_tools()).model_dump(mode='json'); save('tools.json', tools)
                old = {t['name']: t for t in json.loads(a.baseline.read_text())['tools']}
                now = {t['name']: t for t in tools['tools']}
                check('G0 all102 complete tool contracts preserved', len(now) == len(old) == 102 and now == old)

                async def call(tool, args, error=False):
                    response = await c.call_tool(tool, args)
                    item = {'tool': tool, 'arguments': args, 'response': response.model_dump(mode='json')}
                    receipts.append(item)
                    with (out / 'transcript.jsonl').open('a') as f: f.write(json.dumps(item, ensure_ascii=False) + '\n')
                    value = response.structuredContent or json.loads(response.content[0].text)
                    assert bool(response.isError) == error, (tool, value)
                    return value.get('data', value)

                async def page(ref, project=None, view='bundle', limit=48):
                    offset, parts = 0, []
                    while True:
                        value = await call('semantic_bridge_inspect', {'project': project or a.project, 'batch_or_run_ref': ref, 'view': view, 'offset': offset, 'limit': limit})
                        parts.append(base64.b64decode(value['data']))
                        if value['next_offset'] is None: break
                        offset = value['next_offset']
                    raw = b''.join(parts)
                    assert hashlib.sha256(raw).hexdigest() == value['sha256']
                    return json.loads(raw)

                async def register(label, source, args):
                    stored = await call('formal_store', {'project': a.project, 'request_key': a.tag + ':' + label + ':source', 'kind': 'source', 'data': source})
                    q = copy.deepcopy(args)
                    q.update(project=a.project, request_key=a.tag + ':' + label + ':register', source_ref=stored['stored_object_ref'])
                    reg = await call('semantic_bridge_register', q)
                    check(label + ' register completed/no grant', reg['status'] == 'COMPLETED' and reg['execution_permission'] is False)
                    bundle = await page(reg['run_ref']); save(label + '-register.json', bundle)
                    check(label + ' independent registration', verify_bundle(bundle)['status'] == 'PASS')
                    runs.append({'label': label + '-register', **reg})
                    return reg, q

                async def analyze(label, reg, pairs, models=None, budget=32, scenario_origin='HUMAN_PROVIDED'):
                    q = {'project': a.project, 'request_key': a.tag + ':' + label, 'batch_ref': reg['batch_ref'], 'pairs': pairs, 'model_refs': models or [], 'scenario_origin': scenario_origin, 'budget': {'max_models': budget}}
                    run = await call('semantic_bridge_analyze', q)
                    check(label + ' analysis completed', run['status'] == 'COMPLETED')
                    bundle = await page(run['run_ref']); save(label + '-analyze.json', bundle)
                    independently = verify_bundle(bundle)
                    check(label + ' independent certificates/countermodels/scenarios', independently['status'] == 'PASS', **independently)
                    result = bundle['result']
                    check(label + ' no semantic license or grant', result['source_alignment_status'] == 'PROPOSED' and result['checks']['semantic_adjudication'] == 'NOT_EVALUATED' and result['LLM_calls'] == 0 and result['execution_permission'] is False)
                    runs.append({'label': label, **run})
                    evidence.append({'label': label, 'run_ref': run['run_ref'], 'result_sha256': run['result_sha256'], 'coverage': result['checks']['directional_coverage'], 'models_total': result['checks']['model_enumerations'], 'pairs': result['graph']['relations'], 'independent_verification': independently})
                    return result, run

                def arguments(case, extra=None):
                    text = case.get('source', 'Original synthetic Boolean/quantifier QA source.')
                    source = {'text_utf8': text, 'sha256': hashlib.sha256(text.encode()).hexdigest(), 'spans': [], 'context_refs': [], 'rights': 'Original synthetic test; permission for this QA.'}
                    link = {'byte_utf8': [0, len(text.encode())], 'literal': text}
                    obligations = [{'id': 'referent', 'kind': 'ANAPHORA', 'description': 'Who is the reported subject? Engineer/analyst alternatives OPEN; differentiating scenario: messages disagree.', 'status': 'OPEN', 'source_links': [link]}, {'id': 'factivity', 'kind': 'LEXICAL_ASSUMPTION', 'description': 'RISK_FACTIVITY_LEAK: message of an error may be true while actual error is false; Message predicate remains an external PROPOSED interpretation.', 'status': 'OPEN', 'source_links': [link]}] if case['id'].startswith('T4') else []
                    args = {'expected_source_sha256': source['sha256'], 'target_signature': case['signature'], 'hypotheses': [{'client_id': name, 'language': 'FOL_V1', 'formula_ast': phi, 'assumptions': [], 'source_links': [link], 'construction_trace': [{'origin': 'provided frozen fixture', 'note': 'Client semantic audit; no human adjudication or causal uplift measurement'}], 'obligations': copy.deepcopy(obligations)} for name, phi in {**case['formulas'], **(extra or {})}.items()]}
                    return source, args

                def directed(result):
                    values = {}
                    for edge in result['graph']['relations']:
                        x, y = edge['client_ids']
                        for key, left, right in [('A_IMPLIES_B', x, y), ('B_IMPLIES_A', y, x)]:
                            d = edge['directions'][key]; status = 'COUNTERMODEL' if d['status'].startswith('COUNTERMODEL_') else d['status']
                            values[left, right] = (status, d['models_checked'], d['counterexample_ref'])
                    return values

                await call('assurance_project_new', {'project': a.project, 'request_key': 'init'})
                t4 = cases['T4_existence_projection']; source, args = arguments(t4)
                reg, regq = await register('T4', source, args)
                fwd, fwd_run = await analyze('T4-forward32', reg, [['HmsgE', 'Hskeleton']])
                rev, _ = await analyze('T4-reverse32', reg, [['Hskeleton', 'HmsgE']])
                d = fwd['graph']['relations'][0]['directions']
                check('G1 projection exact/zero models', d['A_IMPLIES_B']['status'] == 'PROVED_ENTAILMENT' and d['A_IMPLIES_B']['models_checked'] == 0)
                check('G3 reverse countermodel within32 and swap invariant', directed(fwd) == directed(rev) and d['B_IMPLIES_A']['status'] == 'COUNTERMODEL_B_NOT_A' and d['B_IMPLIES_A']['models_checked'] <= 32)
                pairs = [['HmsgE', 'Hskeleton'], ['HmsgBoth', 'HmsgE'], ['HmsgE', 'HmsgA']]
                expected = None
                for i, order in enumerate(permutations(pairs)):
                    result, _ = await analyze('T4-permutation' + str(i), reg, list(order))
                    values = directed(result)
                    if expected is None: expected = values
                    check('G3 actual pair permutation ' + str(i), values == expected and result['checks']['directional_coverage']['completed'] == 6)
                heavy = copy.deepcopy(t4['formulas']['Hskeleton']); heavy['quant'] = 'forall'
                reverse = {'quant': 'exists', 'var': heavy['body']['var'], 'sort': heavy['body']['sort'], 'body': {'quant': 'forall', 'var': heavy['var'], 'sort': heavy['sort'], 'body': copy.deepcopy(heavy['body']['body'])}}
                source, args = arguments(t4, {'HeavyA': heavy, 'HeavyB': reverse}); heavy_reg, _ = await register('T4-heavy', source, args)
                heavy_pairs = [['HeavyA', 'HeavyB'], ['HmsgE', 'Hskeleton'], ['HmsgBoth', 'HmsgE']]
                for budget in (32, 64):
                    x, _ = await analyze('heavy-forward' + str(budget), heavy_reg, heavy_pairs, budget=budget)
                    y, _ = await analyze('heavy-reverse' + str(budget), heavy_reg, [list(reversed(p)) for p in reversed(heavy_pairs)], budget=budget)
                    check('G3 heavy fairness and swap ' + str(budget), directed(x) == directed(y) and all(e['summary']['completed'] == 2 for e in x['graph']['relations'][1:]) and x['checks']['model_enumerations'] == budget)
                    check('G5 open directions honestly aggregated ' + str(budget), x['status'] == 'CHECKED_WITH_OPEN_DIRECTIONS' and x['checks']['directional_coverage']['undecided'] > 0)
                # Adversarial valid 14-quantifier formulas: model fairness alone is insufficient.
                sig = {'sorts': ['s'], 'predicates': {'P': ['s'], 'Q': ['s']}}
                p = {'pred': 'P', 'args': [{'var': 'x0'}]}; q = {'pred': 'Q', 'args': [{'var': 'x0'}]}
                per = {'quant': 'forall', 'var': 'x0', 'sort': 's', 'body': {'or': [p, q]}}
                global_ = {'or': [{'quant': 'forall', 'var': 'x0', 'sort': 's', 'body': p}, {'quant': 'forall', 'var': 'x0', 'sort': 's', 'body': q}]}
                def costly(first):
                    phi = {'or': [p, {'not': p}]}
                    for i in reversed(range(14)): phi = {'quant': first if i == 0 else 'forall', 'var': 'x' + str(i), 'sort': 's', 'body': phi}
                    return phi
                costcase = {'id': 'cost-heavy', 'signature': sig, 'formulas': {'HeavyAll': costly('forall'), 'HeavySome': costly('exists'), 'Per': per, 'Global': global_}}
                source, args = arguments(costcase); costreg, _ = await register('cost-heavy', source, args)
                for budget in (32, 64):
                    result, _ = await analyze('cost-fairness' + str(budget), costreg, [['HeavyAll', 'HeavySome'], ['Per', 'Global']], budget=budget)
                    heavy_edge, cheap_edge = result['graph']['relations']
                    check('G3 cost-heavy local bound cannot starve cheap counterexample ' + str(budget), heavy_edge['search_halt_reason'].startswith('PAIR_') and cheap_edge['directions']['A_IMPLIES_B']['status'] == 'COUNTERMODEL_A_NOT_B' and cheap_edge['directions']['A_IMPLIES_B']['models_checked'] == 11 and result['checks']['total_steps'] <= 100000)
                for name, case in cases.items():
                    if name.startswith('T4'): continue
                    source, args = arguments(case); row, _ = await register(name, source, args)
                    pairs, seen = [], set()
                    for direction in case['directions']:
                        pair = [direction['left'], direction['right']]; key = tuple(sorted(pair))
                        if key not in seen: pairs.append(pair); seen.add(key)
                    result, _ = await analyze(name, row, pairs, budget=64)
                    if name in ('T2_quantifier_negation', 'boolean_commutativity'):
                        check('G2/G5 exact equivalence ' + name, result['graph']['relations'][0]['status'] == 'PROVED_LOGICAL_EQ' and result['graph']['relations'][0]['model_enumerations'] == 0)
                    if name == 'T3_forall_distributivity_trap':
                        check('G4 finite exhaustion not theorem', result['graph']['relations'][0]['directions']['B_IMPLIES_A']['status'] == 'NO_COUNTERMODEL_WITHIN_BOUND' and result['status'] == 'CHECKED_WITH_OPEN_DIRECTIONS')
                # Distinguish a message from a fact in a declared control model, without semantic licensing.
                factcase = copy.deepcopy(t4); factcase['signature']['predicates']['WrongEngineer'] = ['engineer']
                fact = copy.deepcopy(factcase['formulas']['HmsgE']); fact['body']['body']['and'][1] = {'pred': 'WrongEngineer', 'args': [{'var': fact['var']}]}
                source, args = arguments(factcase, {'Hfact': fact}); factreg, _ = await register('factivity', source, args)
                model = {'world': 'closed', 'domains': {'engineer': ['e'], 'analyst': ['a']}, 'relations': {'Said': [['e', 'a']], 'MessageEngineerWrong': [['e', 'a']], 'MessageAnalystWrong': [], 'WrongEngineer': []}}
                stored = await call('formal_store', {'project': a.project, 'request_key': a.tag + ':factivity-model', 'kind': 'model', 'data': model})
                result, _ = await analyze('factivity-control', factreg, [['HmsgE', 'Hfact']], [stored['stored_object_ref']], budget=64)
                cells = {v['client_id']: v for v in result['scenario_vectors']}
                check('G7 message TRUE/fact FALSE; alternatives remain PROPOSED OPEN', cells['HmsgE']['formula_truth'] == 'TRUE' and cells['Hfact']['formula_truth'] == 'FALSE' and all(v['source_alignment_status'] == 'PROPOSED' and all(o['status'] == 'OPEN' for o in v['obligations']) for v in cells.values()))
                # Reissue original inputs only in the separate QA namespace; never modify the real EXP02 project.
                original_manifest = json.loads((ROOT / 'docs/SEMANTIC_BRIDGE_PATCH002_20261109/reference/MCP_RUNS_EXP02.json').read_text())
                historical_cells = 0
                for name, previous in original_manifest['runs'].items():
                    original_reg = json.loads((a.historical / (name + '-register.json')).read_text())
                    original_analysis = json.loads((a.historical / (name + '-analyze.json')).read_text())
                    payload = original_reg['packet']['payload']; reg2, _ = await register('EXP02-' + name, payload['source'], payload['arguments'])
                    payload = original_analysis['packet']['payload']; model_refs = []
                    for i, m in enumerate(payload['models']):
                        stored = await call('formal_store', {'project': a.project, 'request_key': a.tag + ':EXP02-' + name + '-model' + str(i), 'kind': 'model', 'data': m['model']}); model_refs.append(stored['stored_object_ref'])
                    old_h = {h['hypothesis_ref']: h['client_id'] for h in payload['batch']['hypotheses']}
                    pairs = [[old_h[x], old_h[y]] for x, y in payload['pairs']]
                    result, _ = await analyze('EXP02-' + name, reg2, pairs, model_refs, budget=payload['budget']['max_models'], scenario_origin=payload['models'][0]['origin'])
                    def projection(rows):
                        return [{k: v for k, v in row.items() if k != 'hypothesis_ref'} for row in rows]
                    check('G6 exact original scenario vectors ' + name, projection(result['scenario_vectors']) == projection(original_analysis['result']['scenario_vectors']))
                    historical_cells += len(result['scenario_vectors'])
                    prior = await page(previous['analysis_run_ref'], project=original_manifest['project'])
                    check('G9 old immutable result retained ' + name, prior == original_analysis)
                    rejected = await call('semantic_bridge_replay', {'project': original_manifest['project'], 'run_ref': previous['analysis_run_ref'], 'expected_result_sha256': previous['analysis_result_sha256']}, error=True)
                    check('G9 historical binding fail closed ' + name, rejected['error']['code'] == 'KERNEL_BINDING_UNAVAILABLE')
                    if name == 'T6':
                        check('G7 T6 temporal gap remains OPEN', any(h['type_status'] == 'LANGUAGE_INSUFFICIENT' for h in payload['batch']['hypotheses']) and all(o['status'] == 'OPEN' for h in result['obligations'] for o in h['items']))
                check('G6 all77 original cells retained', historical_cells == 77)
                # Repeats cannot create a new operation; full small pages reconstruct exactly.
                check('G8 request idempotency', (await call('semantic_bridge_register', regq)) == reg)
                original = await page(fwd_run['run_ref']); check('G8 1KiB pages exact', await page(fwd_run['run_ref'], limit=1) == original)
                replay_receipts = []
                for row in runs:
                    response = await call('semantic_bridge_replay', {'project': a.project, 'run_ref': row['run_ref'], 'expected_result_sha256': row['result_sha256']})
                    check('G9 real replay ' + row['label'], response['status'] == 'REPLAY_MATCH')
                    replay_receipts.append(response)
                    m = row['metrics']
                    check('G8 original CPU/wall/RAM ' + row['label'], m['job_cpu_s'] <= 5 and m['worker_wall_s'] <= 6 and m['max_rss_kib'] * 1024 <= 512 * 1024 * 1024)
                health = await call('service_health', {}); status = await call('bridge_system_status', {})
                check('G0 live version healthy/noauth', health['version'] == 'v0.4.15-developer-preview' and health['authentication'] == 'none' and health['audit']['ok'] and health['sqlite_integrity'] == 'ok')
                check('G10 actual opt-in capabilities/no LLM or source adjudication', status['contextual_semantic_bridge']['version'] == 'semantic-bridge-patch002/1' and status['contextual_semantic_bridge']['LLM_calls'] == 0 and status['contextual_semantic_bridge']['semantic_adjudication'] == 'NOT_EVALUATED')
                save('service_health.json', health); save('bridge_system_status.json', status)
                save('REPLAY_RECEIPTS.json', replay_receipts); save('MCP_RECEIPTS.json', receipts); save('LIVE_RUNS.json', runs)
                save('DIRECTIONAL_EVIDENCE.json', evidence)
                save('SEMANTIC_REVIEW_PROVENANCE.json', {'status': 'CLIENT_PROTOCOL_AND_SYNTHETIC_CONTROL_ONLY', 'human_adjudication': 'NOT_EVALUATED', 'causal_LLM_uplift': 'NOT_MEASURED', 'source_alignment': 'PROPOSED', 'factivity_control': 'Declared message TRUE/fact FALSE model; no Russian author-intent inference', 'original_EXP02_cells_recomputed': historical_cells})
                save('result.json', {'status': 'PASS', 'checks': len(checks), 'runs': len(runs), 'actual_tools': len(now), 'historical_cells': historical_cells, 'model_calls': 0, 'execution_permission': False})
                print('PATCH002_MCP_ACCEPTANCE_PASS', len(checks), len(runs), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--endpoint', required=True); p.add_argument('--loopback', action='store_true'); p.add_argument('--baseline', type=Path, required=True); p.add_argument('--historical', type=Path, required=True); p.add_argument('--output', type=Path, required=True); p.add_argument('--project', required=True); p.add_argument('--tag', required=True)
    asyncio.run(main(p.parse_args()))
