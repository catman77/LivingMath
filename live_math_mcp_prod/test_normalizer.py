import copy
import json
from pathlib import Path

import pytest
import jsonschema

from normalizer import Budget, ContextNormalizer, SCHEMA_PATH, digest, normalize_context, reconstruct_context
from normalization_worlds import create_world
from normalization_oracle import expected, materialize, run_audit, audit_projection


@pytest.fixture
def world(tmp_path):
    return create_world(tmp_path / 'world.sqlite3', 0)


def test_independent_expected_rules_cover_every_registered_candidate(world, tmp_path):
    store = materialize(world['history'], tmp_path / 'audit.sqlite3')
    for candidate in world['candidates']:
        actual = run_audit(store, candidate)
        predicted = expected(candidate)
        assert actual['status'] == 'AUDITED'
        assert actual['report']['verdict'] == predicted['verdict']
        assert sorted(actual['report']['warnings']) == predicted['codes'], candidate['id']
        assert actual['report']['proof_status'] == predicted['proof_status']


def test_determinism_exact_source_and_separate_zero_concepts(world):
    h, dq = world['history'], world['candidates']
    a = normalize_context(h, 'zero', dq, 'C2')
    b = normalize_context(h, 'zero', dq, 'C2')
    assert a == b and a['status'] == 'COMPLETE'
    originals = {e['id']: e for e in h['tables']['events']}
    zeros = [c for c in a['concepts'] if c['surface_forms'][0]['text'] == 'zero']
    assert len(zeros) == 3 and len({c['concept_id'] for c in zeros}) == 3
    for c in a['concepts']:
        e = originals[c['source_record']['id']]
        assert c['source_record'] == e and c['input_hashes'] == [digest(e)]
        for form in c['surface_forms']:
            pos = form['span']
            assert e[pos['field']][pos['start']:pos['end']] == form['raw_literal']
        assert c['confidence']['truth_probability'] is None
        assert all(not r['substitution_allowed'] for r in c['relations'])
    assert all(not x['substitution_allowed'] for x in a['interpretations'])
    assert {c['representation'] for c in zeros} == {'point_value', 'analytic_germ'}


def test_opaque_duplicate_keys_and_verification_claims_are_not_laundered(world):
    h = copy.deepcopy(world['history'])
    root = h['tables']['events'][0]
    root['content'] = '{"statement":"a","statement":"b"}'
    root['status'] = 'verified'
    view = normalize_context(h, 'zero', world['candidates'], 'C1')
    node = next(c for c in view['concepts'] if c['source_record']['id'] == root['id'])
    assert node['claim_type'] == 'UNKNOWN' and node['epistemic_status'] == 'unverified'
    assert node['unknowns'] and node['source_record']['content'] == root['content']


def test_cache_invalidates_event_scope_obligation_and_normalizer_versions(world, monkeypatch):
    import normalizer
    h, dq = world['history'], world['candidates'];cache = ContextNormalizer()
    initial = cache.normalize(h, 'zero', dq)
    assert cache.normalize(h, 'zero', dq) == initial and len(cache.cache) == 1
    changed = copy.deepcopy(h);changed['tables']['events'][0]['content'] += ' '
    assert cache.normalize(changed, 'zero', dq)['input_digest'] != initial['input_digest']
    changed = copy.deepcopy(h);changed['tables']['research_obligation_versions'][0]['payload_json'] += ' '
    assert cache.normalize(changed, 'zero', dq)['input_digest'] != initial['input_digest']
    monkeypatch.setattr(normalizer, 'VERSION', 'future-version')
    assert cache.normalize(h, 'zero', dq)['normalizer_version'] == 'future-version'
    assert len(cache.cache) == 4


def test_partial_budget_missing_source_foreign_binding_and_c4_fail_closed(world):
    h, dq = world['history'], world['candidates']
    small = normalize_context(h, 'zero', dq, 'C3', Budget(max_output_bytes=4096, max_tokens=1024))
    assert small['status'] == 'INSUFFICIENT_CONTEXT' and small['audit_context'] is None
    missing = copy.deepcopy(h)
    missing['tables']['events'] = [e for e in missing['tables']['events'] if e['id'] != world['events']['adverse']]
    assert normalize_context(missing, 'zero', dq)['status'] == 'INSUFFICIENT_CONTEXT'
    foreign = copy.deepcopy(h);foreign['tables']['events'][0]['project'] = 'OTHER'
    with pytest.raises(ValueError, match='Cross-project'):
        normalize_context(foreign, 'zero', dq)
    explanation = normalize_context(h, 'zero', dq, 'C4')
    assert explanation['status'] == 'EXPLANATION_ONLY'
    assert audit_projection(None, explanation, dq[0], h)['status'] == 'INSUFFICIENT_CONTEXT'


def test_actual_audit_equivalence_and_tamper_refusal(world, tmp_path):
    h, dq = world['history'], world['candidates']
    full = materialize(h, tmp_path / 'full.sqlite3')
    view = normalize_context(h, 'zero', dq, 'C2')
    projected = materialize(view['audit_context'], tmp_path / 'projected.sqlite3')
    for a in dq:
        assert run_audit(full, a) == audit_projection(projected, view, a, h)
    broken = copy.deepcopy(view)
    broken['audit_context']['tables']['events'] = [e for e in broken['audit_context']['tables']['events'] if e['id'] != world['events']['adverse']]
    broken['certificate']['context_digest'] = digest(broken['audit_context'])
    assert audit_projection(projected, broken, dq[0], h)['status'] == 'INSUFFICIENT_CONTEXT'
    altered = copy.deepcopy(dq[0]);altered['move']['proposed_operation']['testable_consequence'] = 'Unregistered claim'
    assert audit_projection(projected, view, altered, h)['status'] == 'INSUFFICIENT_CONTEXT'


def test_strict_schema_rejects_normalizer_claim_of_verification(world):
    view = normalize_context(world['history'], 'zero', world['candidates'])
    view['proof_status'] = 'verified'
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(view, json.loads(SCHEMA_PATH.read_text()))


def test_source_bound_refuses_before_extracting_any_claims(world):
    result = normalize_context(world['history'], 'zero', world['candidates'], 'C1', Budget(max_events=1))
    assert result['status'] == 'INSUFFICIENT_CONTEXT'
    assert result['concepts'] == [] and result['audit_context'] is None and result['source_catalog'] == {}


def test_cache_storage_remains_bounded_and_returns_detached_values(world):
    cache = ContextNormalizer()
    for i in range(10):
        value = cache.normalize(world['history'], 'zero ' + str(i), world['candidates'])
        value['concepts'].clear()
    assert len(cache.cache) <= 8
    assert cache.normalize(world['history'], 'zero 9', world['candidates'])['concepts']


def test_lazy_source_roundtrip_and_source_version_drift(world):
    h = world['history'];v = normalize_context(h, 'zero', world['candidates'], 'C2')
    assert v['loss_ledger']
    recovered = reconstruct_context(v, h)
    assert len(recovered['tables']['events']) == len(h['tables']['events'])
    assert digest(recovered) == v['input_digest']
    changed = copy.deepcopy(h);changed['tables']['events'][-1]['content'] += ' '
    with pytest.raises(ValueError, match='Source changed'):
        reconstruct_context(v, changed)


def test_closed_obligations_never_appear_as_open(world):
    view = normalize_context(world['history'], 'zero', world['candidates'], 'C1')
    assert all(o['status'] in {'OPEN', 'TESTING'} for c in view['concepts'] for o in c['open_obligations'])


def test_foreign_candidate_project_cannot_receive_a_completeness_certificate(world):
    dq=copy.deepcopy(world['candidates']);dq[0]['project']='FOREIGN'
    view=normalize_context(world['history'],'zero',dq,'C2')
    assert view['status']=='INSUFFICIENT_CONTEXT' and not view['coverage']['auditable']
