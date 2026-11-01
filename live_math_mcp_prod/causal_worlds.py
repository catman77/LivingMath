"""Precommitted finite sources; hidden semantic relations never enter prompts."""
import hashlib
import json
import random

SEEDS = (42101, 42109, 42131)
MODES = ('M0', 'M1', 'M2', 'M2-no-audit', 'M3', 'M4')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def world(index, repeat):
    rng = random.Random(SEEDS[repeat] + index * 1009)
    def name():
        return 'n' + str(rng.randrange(100000, 999999))
    kind = ('words', 'graph', 'table', 'rewrite')[index // 3]
    offset = index % 3
    nodes = [name() for _ in range(4)]
    if kind == 'words':
        source = dict(zip(nodes, ['ab' * (offset + 1), 'aab', 'abba', 'b']))
        observable = 'length'
    elif kind == 'graph':
        source = {nodes[0]: [nodes[1], nodes[2]], nodes[1]: [nodes[2]],
                  nodes[2]: [], nodes[3]: nodes[:offset + 1]}
        observable = 'out_degree'
    elif kind == 'table':
        source = dict(zip(nodes, [2 + offset, 3, 4, 1]))
        observable = 'value'
    else:
        source = dict(zip(nodes, ['aba' * (offset + 1), 'aab', 'abba', 'b']))
        observable = 'length_after_simultaneous_a_to_bb'
    source_id = name()
    premises = {'x': name(), 'y': name(), 'z': name(), 'old': name(), 'other': name()}
    w = {'index': index, 'repeat': repeat, 'seed': SEEDS[repeat], 'kind': kind, 'nodes': nodes,
         'source_id': source_id, 'source_version': 2, 'source': source, 'observable': observable,
         'premises': premises, 'representation': 'finite_source:' + digest([kind, source]),
         'scope': 'Read-only ' + observable + ' on source ' + source_id + ' version 2; at most four listed inputs.',
         'mechanism': 'finite_source_observation', 'labels': {k: name() for k in range(12)}}
    values = [execute(w, node) for node in nodes]
    w['values'] = values
    # Definitions are observations/claims, not pre-labelled candidate categories.
    events = {
        'source': {'kind': 'qa_source', 'status': 'observation', 'content': {'source_id': source_id,
            'version': 2, 'kind': kind, 'inputs': source, 'observable': observable,
            'rule': 'Replace each a with bb simultaneously once' if kind == 'rewrite' else 'Direct finite source reading'}},
        'x': {'kind': 'hypothesis', 'status': 'hypothesis', 'content': {'statement_id': premises['x'],
            'source_id': source_id, 'input_id': nodes[0], 'observable': observable, 'asserted_value': values[0] + 1,
            'grounds': 'A reported aggregate has no retained item-by-item calculation.'}},
        'y': {'kind': 'hypothesis', 'status': 'hypothesis', 'content': {'statement_id': premises['y'],
            'source_id': source_id, 'input_id': nodes[1], 'observable': observable, 'asserted_value': values[1] + 1,
            'grounds': 'An item-wise comparison was proposed but no result was retained.'}},
        'known': {'kind': 'experiment', 'status': 'experiment', 'content': {'source_id': source_id,
            'input_id': nodes[3], 'observable': observable, 'measured_value': values[3],
            'scope': 'Only this input; other inputs were not measured.'}},
        'counter': {'kind': 'counterexample', 'status': 'counterexample', 'content': {'statement_id': premises['old'],
            'source_id': source_id, 'input_id': nodes[3], 'observable': observable,
            'asserted_value': values[3] + 2, 'measured_value': values[3],
            'scope': 'This point comparison only; no statement about all other inputs.'}},
        'archive': {'kind': 'observation', 'status': 'observation', 'content': {'source_id': source_id,
            'version': 1, 'view': 'Aggregate from version 1', 'replacement_version': 2}},
        'diagnostic': {'kind': 'observation', 'status': 'observation', 'content': {'source_id': source_id,
            'statement_id': premises['old'], 'question': 'Which item-level trace explains the recorded discrepancy?',
            'ground': 'Use the discrepancy as data, without assuming the rejected equality.'}},
        'other': {'kind': 'failed_check', 'status': 'experiment', 'content': {'source_id': name(),
            'statement_id': premises['other'], 'asserted_value': 3, 'measured_value': 2,
            'scope': 'A distinct source, with no link to the listed inputs.'}},
        'conflict': {'kind': 'experiment', 'status': 'experiment', 'content': {'source_id': source_id,
            'input_id': nodes[3], 'observable': observable, 'measured_value': values[3] + 1,
            'record': 'An independent report for the same input, source and version; no reconciliation recorded.'}},
    }
    order = [k for k in events if k != 'source']
    rng.shuffle(order)
    w.update(events=events, event_order=['source'] + order)
    obligations = ['measure', 'archive', 'closed', 'diagnose']
    rng.shuffle(obligations)
    w['obligation_order'] = obligations
    target = 1 if repeat == 2 else 0
    w['feedback'] = {'input_id': nodes[target], 'premise_id': premises['y' if target else 'x'],
        'asserted_value': values[target] + 1, 'measured_value': values[target],
        'label': 'failure' if repeat == 1 else 'measurement',
        'text': 'A retained item comparison differs from the reported value.'}
    w['oracle'] = {'version': '1.0', 'source_id': source_id, 'version_id': 2,
        'depends_on': {premises['x']: [nodes[0]], premises['y']: [nodes[1]], premises['z']: [nodes[2]],
                       premises['old']: [nodes[3]], premises['other']: ['distinct_source']},
        'contradicts_initial': [premises['old']], 'contradicts_feedback': [w['feedback']['premise_id']],
        'preserves': [nodes[2]], 'scope': w['scope'], 'known_inputs': [nodes[3]],
        'values': dict(zip(nodes, values)), 'source_hash': digest(source),
        'point_evidence_does_not_imply': 'all_source_inputs', 'feedback_input': nodes[target]}
    return w


def execute(w, node):
    value = w['source'][node]
    if w['kind'] == 'table':
        return value
    if w['kind'] == 'rewrite':
        return len(value.replace('a', 'bb'))
    return len(value)


def public_definition(w):
    return {k: v for k, v in w.items() if k not in {'oracle', 'values', 'feedback'}}
