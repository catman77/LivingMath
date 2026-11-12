"""Real isolated primitive + independent coverage, journal and adversarial checks."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from lm_suti_assurance.core import canonical, digest
from lm_suti_assurance.errors import AssuranceError
from lm_suti_assurance.service import Service
from lm_suti_assurance.white_star.contracts import VENDOR, preflight
from lm_suti_assurance.white_star.pool import prepare
from lm_suti_assurance.completeness.contracts import SCOPE, kernel_binding
from lm_suti_assurance.completeness.executor import Executor
from lm_suti_assurance.completeness.service import CoverageService
from lm_suti_assurance.completeness.verify import verify_plan


def request():
    return json.loads((VENDOR/'fixtures/original_request.json').read_text())


@pytest.fixture(scope='module')
def pool():
    assert prepare()['ready']
    executor = Executor()
    assert executor.status()['ready'], executor.status()
    yield executor
    executor.close()


@pytest.fixture
def setup(tmp_path, pool):
    root = tmp_path/'state'
    Service(root).new('qa', 'init')
    service = CoverageService(root, pool)
    q = request()
    created = service.plan('qa', 'plan', q, SCOPE)
    return service, created, q


def load(s, ref):
    w = s.base.workspace('qa')
    with w.locked():
        return s._load(w, ref, w.history())[0]


def reseal(p):
    for i, r in enumerate(p['obligations']):
        r['obligation'] = i
        r.pop('task_id', None)
        r['task_id'] = digest([p['scope_id'], r])
    p.pop('plan_sha256', None)
    p['plan_sha256'] = digest(p)


def test_complete_geometry_bounds_and_provenance(setup):
    s, start, q = setup
    p = load(s, start['plan_ref'])
    check = verify_plan(q, p, kernel_binding()['sha256'])
    pairs = {tuple(r['pair']) for r in p['obligations']}
    assert check['targets'] == 8*len(pairs) == start['total_count']
    assert all(r['witness_origin'] == 'CONSTRUCTED_CERTIFIED_WITNESS' and r['prefix_was_executed'] is False for r in p['obligations'])
    assert all(sum(r['witness']) <= p['witness_l1_bound'] for r in p['obligations'])
    assert start['compute_complete'] is False and start['delivery_acked'] is False


@pytest.mark.parametrize('mutation', ['view', 'alias', 'coordinates', 'float_coordinates', 'source', 'target', 'omitted', 'origin', 'atlas'])
def test_resealed_forgery_and_missing_target_rejected(setup, mutation):
    s, start, q = setup
    p = load(s, start['plan_ref'])
    row = p['obligations'][0]
    if mutation == 'view': row['view'] = len(p['atlas']['charts'])
    if mutation == 'alias': row['alias_index'] = len(row['aliases'])
    if mutation == 'coordinates': row['coordinates'][0] += 1
    if mutation == 'float_coordinates': row['coordinates'][0] = float(row['coordinates'][0])
    if mutation == 'source': row['source_sha256'] = '0'*64
    if mutation == 'target': row['target']['dominance'] = 'FALSE'
    if mutation == 'omitted': p['obligations'].pop(); p['total_count'] -= 1
    if mutation == 'origin': row['witness_origin'] = 'CAT_DISCOVERY'
    if mutation == 'atlas': p['atlas']['charts'][0]['matrix'][0] += 1
    reseal(p)
    with pytest.raises(AssuranceError): verify_plan(q, p, kernel_binding()['sha256'])


def test_complete_resume_export_ack_replay(setup):
    s, start, _ = setup
    current = s.advance('qa', start['plan_ref'], 'zero', start['cursor'], 0)
    assert current['status'] == 'PARTIAL' and current['computed_count'] == 0
    chunks = 0
    while not current['compute_complete']:
        args = ('qa', start['plan_ref'], f'work-{chunks}', current['cursor'], 7)
        got = s.advance(*args)
        w = s.base.workspace('qa'); before = (w.path/'journal.jsonl').read_bytes()
        assert s.advance(*args) == got
        assert (w.path/'journal.jsonl').read_bytes() == before
        s = CoverageService(s.base.root, s.executor)  # fresh instance, journal restore
        current = got; chunks += 1
    assert current['export_available'] and not current['delivery_acked']
    records, offset = [], 0
    while True:
        page = s.inspect('qa', start['plan_ref'], 'records', offset, 64)
        assert digest(page['records']) == page['page_sha256']
        records += page['records']
        if page['next_cursor'] is None: break
        offset = page['next_cursor']
    assert len(records) == len({r['work_unit_key'] for r in records}) == start['total_count']
    assert digest(records) == current['export_sha256']
    assert all(r['integer_projection_checked'] and r['execution_permission'] is False for r in records)
    page = s.replay('qa', start['plan_ref'], 0, 128)
    assert page['checked_count'] == len(records)
    ack = {'export_sha256': digest(records), 'record_count': len(records), 'client_id': 'pytest'}
    final = s.inspect('qa', start['plan_ref'], 'delivery', acknowledgement=ack, request_key='ack')
    assert final['delivery_acked']
    assert s.inspect('qa', start['plan_ref'], 'delivery', acknowledgement=ack, request_key='ack') == final


def test_cursor_cannot_skip_or_change_scope(setup):
    s, start, _ = setup
    for bad in [{**start['cursor'], 'index': 1}, {**start['cursor'], 'prefix_sha256': '1'*64}, {**start['cursor'], 'plan_ref': '1'*64}]:
        with pytest.raises(AssuranceError, match='CURSOR_PREFIX_MISMATCH'):
            s.advance('qa', start['plan_ref'], 'forged', bad, 1)
    good = s.advance('qa', start['plan_ref'], 'work', start['cursor'], 1)
    with pytest.raises(AssuranceError, match='CURSOR_PREFIX_MISMATCH'):
        s.advance('qa', start['plan_ref'], 'stale', start['cursor'], 1)
    with pytest.raises(AssuranceError, match='REQUEST_KEY_CONFLICT'):
        s.advance('qa', start['plan_ref'], 'work', good['cursor'], 1)


def test_project_isolation_and_source_tamper(setup):
    s, start, q = setup
    s.base.new('other', 'new')
    with pytest.raises(AssuranceError, match='PLAN_NOT_FOUND'): s.inspect('other', start['plan_ref'])
    with pytest.raises(AssuranceError, match='PROJECT_NOT_FOUND'): s.plan('missing', 'new', q, SCOPE)
    q['encoding']['source']['text'] += 'tamper'
    with pytest.raises(AssuranceError, match='SOURCE_MISMATCH'): s.plan('qa', 'bad', q, SCOPE)


def test_base_rejected_collinear_and_multi_alias_preserved(setup):
    s, _, q = setup
    q['atlas_profile'] = 'base_v1'
    with pytest.raises(AssuranceError, match='COVERAGE_REQUIRES_CJ_V1'): s.plan('qa', 'base', q, SCOPE)
    q['atlas_profile'] = 'cj_v1'
    # Distinct vectors, rotated coincidences create real numerical aliases.
    for c, v in zip(q['encoding']['concepts'], ([1,0], [0,1], [-1,0], [0,-1])):
        c['coordinates'] = v
    q['encoding']['protocol']['candidates_per_step'] = 1
    out = s.plan('qa', 'aliases', q, SCOPE)
    plan = load(s, out['plan_ref'])
    assert any(len(c['aliases']) > 1 for c in plan['atlas']['charts'])
    assert plan['atlas']['omitted_collinear_pairs']
    assert out['total_count'] < 8*len(q['encoding']['concepts'])*(len(q['encoding']['concepts'])-1)//2
    verify_plan(q, plan, kernel_binding()['sha256'])


def test_invalid_projection_leaves_open_obligation(setup):
    s, start, _ = setup
    real = s.executor
    class Broken:
        def run(self, packet):
            result = real.run(packet)
            result['data']['records'][0]['coordinates'][0] += 1
            return result
    s.executor = Broken()
    failed = s.advance('qa', start['plan_ref'], 'broken', start['cursor'], 2)
    assert failed['status'] == 'ERROR' and failed['computed_count'] == 0
    assert failed['error']['unclosed_obligation'] == 0
    s.executor = real
    retry = s.advance('qa', start['plan_ref'], 'retry', failed['cursor'], 2)
    assert retry['computed_count'] == 2


def test_concurrent_identical_request_has_one_commit(setup):
    s, start, _ = setup
    args = ('qa', start['plan_ref'], 'parallel', start['cursor'], 2)
    with ThreadPoolExecutor(2) as pool:
        replies = list(pool.map(lambda _: s.advance(*args), range(2)))
    assert replies[0] == replies[1]
    w = s.base.workspace('qa')
    assert sum(r['action'] == 'coverage.advance' for r in w.history()) == 1


def test_delivery_requires_complete_exact_digest(setup):
    s, start, _ = setup
    ack = {'export_sha256': '0'*64, 'record_count': start['total_count'], 'client_id': 'pytest'}
    with pytest.raises(AssuranceError, match='DELIVERY_ACK_MISMATCH'):
        s.inspect('qa', start['plan_ref'], 'delivery', acknowledgement=ack, request_key='bad-ack')
    assert s.inspect('qa', start['plan_ref'])['delivery_acked'] is False


def test_safe_bound_backend_exact_integers(setup):
    s, _, q = setup
    for c, v in zip(q['encoding']['concepts'], ([1000000,999999], [999999,999998], [-999999,1000000], [0,1])):
        c['coordinates'] = v
    out = s.plan('qa', 'large', q, SCOPE)
    result = s.advance('qa', out['plan_ref'], 'large-run', out['cursor'], 128)
    assert result['compute_complete'] and result['error'] is None
    assert s.replay('qa', out['plan_ref'], 0, 128)['status'] == 'REPLAY_MATCH'
