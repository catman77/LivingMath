"""Frozen four-arm intervention. No provider, network, lexical or gold oracle."""
import copy
import random
import time
from collections import deque
from ..core import digest
from ..formal_bridge.fol import typecheck
from ..symbolic.state import require
from .decoder import decode, build_move, replay_bundle
from .finite_relations import relation

ARMS = ('NO_MOVE', 'REAL_TRACE', 'SHAM_ORDER', 'PRIMITIVE_CLOSURE')
DEFAULT_CLASS = {'domain_sizes': [1, 2], 'max_models': 530, 'max_relation_cells': 9}


def count_nodes(ast) -> int:
    if isinstance(ast, dict):
        return 1 + sum(count_nodes(v) for v in ast.values())
    if isinstance(ast, list):
        return sum(count_nodes(v) for v in ast)
    return 0


def outer_spine(ast: dict) -> tuple[list, dict]:
    spine = []
    while set(ast) == {'quant', 'var', 'sort', 'body'}:
        spine.append({k: v for k, v in ast.items() if k != 'body'})
        ast = ast['body']
    return spine, ast


def primitive_successors(ast: dict):
    """Registry reads AST only. Names/paths are data, never language heuristics."""
    spine, body = outer_spine(ast)
    for index in range(len(spine) - 1):
        permutation = list(range(len(spine)))
        permutation[index], permutation[index + 1] = permutation[index + 1], permutation[index]
        out = copy.deepcopy(body)
        for i in reversed(permutation):
            out = {**spine[i], 'body': out}
        yield out, {'operator': 'SWAP_ADJACENT_OUTER_QUANTIFIERS', 'index': index, 'cost': 1}
    names = set()
    binders = []
    def walk(node, path):
        if isinstance(node, dict):
            if isinstance(node.get('var'), str):
                names.add(node['var'])
            if 'quant' in node:
                binders.append((path, node['var']))
            for k, v in node.items():
                walk(v, path + [k])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, path + [i])
    walk(ast, [])
    fresh = next('_alpha' + str(i) for i in range(len(names) + 1) if '_alpha' + str(i) not in names)
    for path, old in binders:
        out = copy.deepcopy(ast)
        node = out
        for key in path:
            node = node[key]
        node['var'] = fresh
        def rename(value):
            if isinstance(value, list):
                return [rename(x) for x in value]
            if not isinstance(value, dict):
                return value
            if value.get('quant') and value.get('var') == old:
                return value
            return {k: fresh if k == 'var' and v == old else rename(v) for k, v in value.items()}
        node['body'] = rename(node['body'])
        yield out, {'operator': 'ALPHA_RENAME_BINDER', 'path': path, 'old': old, 'new': fresh, 'cost': 1}


def check_primitive_path(base: dict, candidate: dict, steps: list, signature: dict) -> bool:
    current = base
    for step in steps:
        matches = [(out, op) for out, op in primitive_successors(current) if op == step['primitive']]
        if len(matches) != 1 or digest(current) != step['before_ast_sha256']:
            return False
        current = matches[0][0]
        if digest(current) != step['after_ast_sha256'] or typecheck(current, signature)['status'] != 'TYPED':
            return False
    return digest(current) == digest(candidate)


def arm_candidates(base_proposals: list, signature: dict, trace: dict | None,
                   arm: str, policy: dict, tick) -> dict:
    cap = policy['max_candidates_per_source']
    retained = []
    seen = set()
    attempts = []
    queue = deque()
    def retain(ast, base, path, origin, move=None):
        if digest(ast) in seen:
            return
        if count_nodes(ast) > policy['max_ast_nodes'] or typecheck(ast, signature)['status'] != 'TYPED':
            return
        seen.add(digest(ast))
        retained.append({'formula_ast': ast, 'candidate_ast_sha256': digest(ast),
                         'candidate_base_ast_sha256': digest(base), 'primitive_derivation': path,
                         'primitive_cost': len(path) if path is not None else None,
                         'origin_status': origin, 'structural_move': move,
                         'type_status': 'TYPED', 'semantic_alignment_status': 'PROPOSED',
                         'human_licensing': 'HUMAN_NOT_EVALUATED', 'execution_permission': False})
    for b in base_proposals:
        retain(b['formula_ast'], b['formula_ast'], [], 'SOURCE_BOUND_CHECKED')
        queue.append((b['formula_ast'], b['formula_ast'], []))
    require(len(retained) <= cap, 'BASE_CANDIDATE_BOUND')
    generated = []
    if arm in ('REAL_TRACE', 'SHAM_ORDER'):
        require(trace is not None, 'UNBACKED_ORIGIN')
        intervention = copy.deepcopy(trace)
        if arm == 'SHAM_ORDER':
            random.Random(policy['sham_seed']).shuffle(intervention['source_order'])
        for b in base_proposals:
            generated.append((b, intervention))
    complete = True
    for slot in range(cap):
        tick()
        status = 'NOOP_PADDING'
        if len(retained) >= cap:
            complete = False
            status = 'CANDIDATE_CEILING'
        elif arm in ('REAL_TRACE', 'SHAM_ORDER') and slot < len(generated):
            b, intervention = generated[slot]
            move = build_move(b['formula_ast'], signature, b['binder_links'], intervention, placebo=False)
            status = 'UNDECODABLE_FRAME'
            if move:
                move['origin_status'] = 'SHAM_NOT_EVIDENCE' if arm == 'SHAM_ORDER' else 'TRACE_LINK_CHECKED'
                if arm == 'SHAM_ORDER':
                    move['control'] = 'SINGLE_DECODER_ORDER_SHUFFLE'
                    move['sham_seed'] = policy['sham_seed']
                    move['original_source_order_sha256'] = digest(trace['source_order'])
                    move['decoder_source_order_sha256'] = digest(intervention['source_order'])
                retain(move['after_ast'], b['formula_ast'], None, move['origin_status'], move)
                status = 'TYPED_MOVE'
        elif arm == 'PRIMITIVE_CLOSURE':
            if not generated:
                while queue and not generated:
                    current, root, path = queue.popleft()
                    if len(path) < policy['max_primitive_depth']:
                        for out, primitive in primitive_successors(current):
                            generated.append((out, current, root, path, primitive))
            if generated:
                out, before, root, path, primitive = generated.pop(0)
                step = {'primitive': primitive, 'before_ast_sha256': digest(before), 'after_ast_sha256': digest(out)}
                next_path = path + [step]
                if digest(out) not in seen:
                    require(check_primitive_path(root, out, next_path, signature), 'REJECTED_PROVENANCE')
                    retain(out, root, next_path, 'PRIMITIVE_CONSTRUCTION_CHECKED')
                    queue.append((out, root, next_path))
                status = 'PRIMITIVE_ATTEMPT'
        attempts.append({'slot': slot, 'status': status})
    if arm == 'PRIMITIVE_CLOSURE' and (generated or any(len(path) < policy['max_primitive_depth'] for _, _, path in queue)):
        complete = False
    return {'candidates': retained[:cap], 'attempts': attempts, 'attempt_slots': cap,
            'search_complete_within_depth': complete, 'candidate_ceiling': cap,
            'provenance_claim': 'SHAM_NOT_EVIDENCE' if arm == 'SHAM_ORDER' else None}


def redecode(bundle: dict, selections: list, structural: dict, arms: list, policy: dict) -> dict:
    started = time.thread_time()
    deadline = started + policy['max_cpu_ms'] / 1000
    def tick():
        if time.thread_time() >= deadline:
            raise TimeoutError('CPU_BOUND')
    require(replay_bundle(bundle)['status'] == 'REPLAY_MATCH', 'REJECTED_PROVENANCE')
    receipt = bundle['receipt']
    model_class = policy.get('model_class', DEFAULT_CLASS)
    outputs = []
    # Each arm gets the same reserved share. Replay/validation consumes the
    # common budget first; one expensive arm cannot consume another's share.
    share = max(0, deadline - time.thread_time()) / (len(selections) * len(arms))
    for index in selections:
        item = bundle['items'][index]
        base = decode(item['packet'], item['signature'], item['answer'], receipt, [],
                      {**bundle['policy'], 'mode': 'source_only', 'max_candidates': 8})['candidates']
        require(all(count_nodes(b['formula_ast']) <= policy['max_ast_nodes'] for b in base), 'AST_BOUND')
        require(len(base) <= policy['max_candidates_per_source'], 'BASE_CANDIDATE_BOUND')
        trace_list = structural.get(str(index), [])
        trace = trace_list[0] if trace_list else None
        record = {'source_item_index': index, 'source_ref': item['source_ref'],
                  'source_sha256': item['packet']['source']['sha256'], 'signature': item['signature'],
                  'candidate_base_ast_sha256': [digest(b['formula_ast']) for b in base],
                  'base_proposals_sha256': digest(base), 'source_packet_sha256': digest(item['packet']),
                  'selected_trace_sha256': trace['trace_sha256'] if trace else None, 'arms': {}}
        for arm in arms:
            before = time.thread_time()
            arm_deadline = min(deadline, before + share)
            def arm_tick():
                if time.thread_time() >= arm_deadline:
                    raise TimeoutError('CPU_BOUND')
            try:
                candidates = arm_candidates(base, item['signature'], trace, arm, policy, arm_tick)
                roots = {digest(b['formula_ast']): b['formula_ast'] for b in base}
                for c in candidates['candidates']:
                    c['finite_relation'] = relation(roots[c['candidate_base_ast_sha256']], c['formula_ast'], item['signature'], model_class, arm_tick)
                candidates['status'] = 'COMPLETED'
            except TimeoutError:
                candidates = {'status': 'UNKNOWN_BOUND', 'reason': 'CPU_BOUND', 'candidates': [], 'attempt_slots': policy['max_candidates_per_source'], 'attempts': [], 'search_complete_within_depth': False}
            candidates['CPU_ms'] = (time.thread_time() - before) * 1000
            candidates['CPU_ceiling_ms'] = share * 1000
            candidates['base_proposals_sha256'] = digest(base)
            candidates['provider_receipt_digest'] = digest(receipt)
            candidates['model_calls_delta'] = 0
            candidates['network_calls'] = 0
            record['arms'][arm] = candidates
        no_move = {digest(b['formula_ast']) for b in base}
        real = {c['candidate_ast_sha256'] for c in record['arms'].get('REAL_TRACE', {}).get('candidates', [])}
        closure = {c['candidate_ast_sha256']: c for c in record['arms'].get('PRIMITIVE_CLOSURE', {}).get('candidates', [])}
        new = real - no_move
        incremental = new - set(closure)
        comparable = base and all(record['arms'].get(a, {}).get('status') == 'COMPLETED' for a in ('NO_MOVE', 'REAL_TRACE', 'PRIMITIVE_CLOSURE'))
        status = ('NO_BASE_PROPOSALS' if not base else 'UNKNOWN_BOUND' if not comparable else
                  'NO_INCREMENTAL_STRUCTURAL_EXPRESSIVITY_ON_BOUND' if not incremental else 'STRUCTURAL_CANDIDATES_OUTSIDE_PRIMITIVE_SEARCH_ON_BOUND')
        record.update(new_structural=sorted(new) if comparable else None, nontrivial_structural=sorted(incremental) if comparable else None,
                      incremental_status=status,
                      semantic_licensing='HUMAN_NOT_EVALUATED')
        for c in record['arms'].get('REAL_TRACE', {}).get('candidates', []):
            match = closure.get(c['candidate_ast_sha256'])
            if match:
                root = next(b['formula_ast'] for b in base if digest(b['formula_ast']) == match['candidate_base_ast_sha256'])
                require(check_primitive_path(root, c['formula_ast'], match['primitive_derivation'], item['signature']), 'REJECTED_PROVENANCE')
                c['primitive_reproduction'] = {'status': 'PRIMITIVE_CLOSURE_REPRODUCED', 'cost': match['primitive_cost'], 'derivation': match['primitive_derivation'], 'base_ast_sha256': match['candidate_base_ast_sha256']}
        outputs.append(record)
    return {'schema': 'nl-frozen-counterfactual/1', 'items': outputs,
            'invariants': {'provider_request_equal': True, 'raw_output_equal': True, 'base_ast_equal': True,
                           'provider_request_sha256': receipt['request_sha256'], 'provider_receipt_digest': digest(receipt),
                           'raw_output_sha256': receipt['raw_output_sha256'], 'model_calls_delta': 0, 'network_calls': 0},
            'policy': policy, 'CPU_ms': (time.thread_time() - started) * 1000,
            'semantic_alignment_status': 'PROPOSED', 'human_licensing': 'HUMAN_NOT_EVALUATED',
            'execution_permission': False}
