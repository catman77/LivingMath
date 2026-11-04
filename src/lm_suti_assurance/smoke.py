"""Five fixed manual cases, no inference service or model dependency."""
import json
import tempfile
from pathlib import Path
from .core import canonical, digest
from .service import Service
from .bundle import export_bundle, replay

POLICY = {'schema': 'lm-suti.assurance.publication-policy/0.1',
          'audiences': ['private', 'reviewers', 'public'], 'allow_source_bytes': True,
          'reason': 'Explicit publication of these supplied generated acceptance examples only.'}
TAG = 'symseq.assurance.proposal-delta.v1'
CASES = [('F1', {'intent': 'PROPOSE', 'kind': 'FINITE_TRACE', 'trace': [0]*6, 'strength': 'ENTAILED'}, 'REJECTED'),
         ('C1', {'intent': 'PROPOSE', 'kind': 'BOUNDED_PROPERTY', 'property': 'PRESERVES_POPCOUNT'}, 'CHECKED_FINITE'),
         ('S1', {'intent': 'PROPOSE', 'kind': 'SOURCE_PROJECTION', 'relation': 'LOSS_DETECTED'}, 'SOURCE_ATTESTED'),
         ('U1', {'intent': 'PROPOSE', 'kind': 'EMPIRICAL_HYPOTHESIS', 'text': 'An unmeasured intervention might help.'}, 'UNKNOWN')]


def populate(service, project='pilot', output=None):
    tasks = json.loads((Path(__file__).parent / 'examples/FROZEN_CORPUS.json').read_text())
    sources = json.loads((Path(__file__).parent / 'examples/SOURCE_SNAPSHOTS.json').read_text())
    service.new(project, 'project.new')
    results = []
    steps = 0
    for tid, delta, expected in CASES:
        task = tasks[tid]
        for sid in task['source_ids']:
            service.source(project, sources[sid], POLICY, 'source.' + sid)
            steps += 1
        t = service.task(project, {'schema': 'lm-suti.assurance.task/0.1', 'project': project, 'task': task}, 'task.' + tid)
        service.review(project, t['task_ref'], 'QA_OPERATOR', 'Automated acceptance: exact supplied scope/assumptions; not external human review.', 'review.' + tid)
        a = {'schema': 'lm-suti.assurance.candidate/0.1', 'project': project, 'task_ref': t['task_ref'],
             'format': 'delta', 'raw': canonical({'schema': TAG, **delta})}
        c = service.candidate(project, a, 'candidate.' + tid)
        check = service.check(project, c['candidate_ref'], 'direct', 'check.' + tid)
        steps += 4
        results.append({'case': tid, 'expected': expected, **check, 'pass': check['status'] == expected})
        if tid == 'C1':
            checked = service.workspace(project).get(check['check_ref'])
            raw = checked['candidate'];raw['scope'] = {**raw['scope'], 'input_domain': [0, 31]}
            a2 = {**a, 'format': 'candidate', 'raw': canonical(raw), 'supersedes': c['candidate_ref']}
            c2 = service.candidate(project, a2, 'candidate.scope-drift')
            d = service.check(project, c2['candidate_ref'], 'direct', 'check.scope-drift')
            results.append({'case': 'scope-drift', 'expected': 'REJECTED', **d,
                            'pass': d['status'] == 'REJECTED' and d['reason_code'] == 'FROZEN_SCOPE_CHANGED'})
            steps += 2
    raw, manifest = export_bundle(service.workspace(project), 'reviewers')
    direct = replay(raw, 'direct'); compiled = replay(raw, 'compiled')
    if output:
        Path(output).mkdir(parents=True, exist_ok=True)
        (Path(output)/'pilot.zip').write_bytes(raw)
    return {'status': 'PASS' if all(r['pass'] for r in results) and direct['logical_digest'] == compiled['logical_digest'] else 'FAIL',
            'cases': results, 'manual_adapter': 'NO_MODEL_USED', 'automated_QA_not_external_human': True,
            'source_to_bundle_operations': steps + 1, 'direct': direct, 'compiled': compiled,
            'bundle_sha256': __import__('hashlib').sha256(raw).hexdigest(), 'manifest': manifest}


def run():
    with tempfile.TemporaryDirectory() as temporary:
        return populate(Service(Path(temporary)/'state'))
