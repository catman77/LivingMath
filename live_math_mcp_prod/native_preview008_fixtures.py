"""QA-only detached fixtures. Never imported by the preview server or worker."""
import copy
import json
from pathlib import Path
import sqlite3

from normalizer import digest
from normalization_oracle import materialize
from native_preview008_contract import ADAPTER_ID

ORIGINAL007 = Path(__file__).resolve().parents[1] / 'docs/qa/LM-LIVE-MATH-CONSTRUCTIVE-007/20261027T032333888048Z'


def native_request(world: dict, left=None, right=None, mode='constructive') -> dict:
    q, refs = world['query'], world['refs']
    root = next(e for e in world['history']['tables']['events'] if e['id'] == int(refs['root'].split(':')[1]))
    spec = json.loads(root['content'])['source_spec']
    question = {'root_event_id': root['id'],
                'left_history_id': int((left or refs['h0']).split(':')[1]),
                'right_history_id': int((right or refs['h1']).split(':')[1]), 'mode': mode}
    if world['certificate_ref']:
        question['certificate_event_id'] = int(world['certificate_ref'].split(':')[1])
    return {'project': q['project'], 'active_frontier_id': q['move']['active_frontier_id'],
            'active_frontier_version': q['version'],
            'source_event_ids': [e['id'] for e in world['history']['tables']['events']],
            'source_adapter_id': ADAPTER_ID,
            'source_bindings': [{'event_id': e['id'], 'sha256': digest(e)} for e in world['history']['tables']['events']],
            'observer': spec['observer'], 'question': question, 'budget': {}}


def normalize_request(world: dict, level='C2') -> dict:
    return {'project': world['query']['project'], 'focus': 'source-certified interpretation',
            'source_event_ids': [e['id'] for e in world['history']['tables']['events']],
            'query_scope': {'level': level, 'candidates': [world['query']]}, 'budget': {}}


def materialize_copy(world: dict, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=False)
    source = folder / 'fixture-source.sqlite3'
    materialize(world['history'], source)
    destination = folder / 'preview.sqlite3'
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)
    destination.chmod(0o600)
    return destination


def changed(world: dict, fault: str) -> dict:
    w = copy.deepcopy(world)
    rows = w['history']['tables']['events']
    root = next(e for e in rows if 'event:' + str(e['id']) == w['refs']['root'])
    law = next((e for e in rows if 'event:' + str(e['id']) == w['certificate_ref']), None)
    body = json.loads(root['content'])
    spec = body['source_spec']
    if fault == 'fresh':
        p = spec['parameters']
        if w['family'] == 'affine':
            p.update(modulus=17, coefficients=[0, 2, 4, 6, 8, 10, 1, 3])
            spec['current_observation'] = 3
        elif w['family'] == 'permutation':
            p['permutations'][1] = [0, 3, 2, 1, 4]
        else:
            p['initial'] = list('llmllnlo')
            spec['current_observation'] = 'l'
        w['id'] = 'F' + w['id'][1:]
        w['held_out'] = True
    elif fault == 'labels':
        names = {a: 'display_' + str(i) for i, a in enumerate(spec['parameters']['actions'])}
        spec['parameters']['actions'] = [names[a] for a in spec['parameters']['actions']]
        for t in spec['tests']:
            t['suffix'] = [names[a] for a in t['suffix']]
        for e in rows:
            data = json.loads(e['content'])
            if 'word' in data:
                data['word'] = [names[a] for a in data['word']]
                e['content'] = json.dumps(data, sort_keys=True)
    elif fault == 'long_suffix':
        spec['tests'][0]['suffix'] *= 3
    elif fault == 'invalid_suffix':
        spec['tests'][0]['suffix'] = ['not_installed']
    elif fault == 'source_code':
        spec['parameters']['python'] = 'raise RuntimeError("never execute")'
    elif fault == 'point_germ':
        data = json.loads(rows[0]['content']); data['representation'] = 'analytic_germ'
        rows[0]['content'] = json.dumps(data)
    elif fault == 'guard_false':
        data = json.loads(law['content']); data['source_certificate']['guard']['total_admissibility'] = False
        law['content'] = json.dumps(data)
    elif fault == 'wrong_law':
        data = json.loads(law['content']); data['source_certificate']['kind'] = 'commutative_magic'
        law['content'] = json.dumps(data)
    elif fault == 'partial_law':
        data = json.loads(law['content']); data['source_certificate']['coverage'] = []
        law['content'] = json.dumps(data)
    elif fault == 'stale_law':
        data = json.loads(law['content']); data['source_certificate']['version'] += 1
        law['content'] = json.dumps(data)
    elif fault == 'closed':
        for v in w['history']['tables']['research_obligation_versions']:
            data = json.loads(v['payload_json']); data['status'] = 'CLOSED'; v['payload_json'] = json.dumps(data)
    else:
        raise ValueError(fault)
    root['content'] = json.dumps(body, sort_keys=True)
    if law:
        data = json.loads(law['content']); data['source_certificate']['source_hash'] = digest(root)
        law['content'] = json.dumps(data, sort_keys=True)
    return w
