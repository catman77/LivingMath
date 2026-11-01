"""Replayable isolation, evidence, reverse-map and information-loss boundaries."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest

from semantic_grounding.source import GroundingVault
from semantic_grounding.proposer import propose
from semantic_grounding.critic import critique
from semantic_grounding.process import run_worker
from semantic_grounding.controls import run_controls
from semantic_grounding.formal import formalize, calibration_controls
from artifact_translation.checker import check_translation
from artifact_translation.contract import SourceGraph

ROOT = Path(__file__).resolve().parent.parent / 'semantic_grounding003'


def reveal(case_id):
    v = GroundingVault(ROOT)
    c = next(c for c in v.cases if c['id'] == case_id)
    train = v.packet(c['train_packet'])
    ps = propose(train, c['family'])
    seal = v.seal([{'prediction': h['prediction'], 'target_free': True} for h in ps])
    return v, c, train, v.reveal(c, seal, train), ps


def test_hidden_evidence_requires_committed_seal():
    v = GroundingVault(ROOT)
    c = v.cases[0]
    with pytest.raises(PermissionError):
        v.packet(c['challenge_packet'])
    seal = v.seal([{'target_free': True, 'prediction': 'test'}])
    with pytest.raises(ValueError):
        v.packet(c['challenge_packet'], seal={**seal, 'prediction_count': 99})


def test_mutated_raw_source_rejected_by_original_freeze(tmp_path):
    dest = tmp_path / 'frozen-root'
    dest.mkdir(); shutil.copyfile(ROOT / 'source-freeze.json', dest / 'source-freeze.json')
    shutil.copytree(ROOT / 'frozen', dest / 'frozen')
    p = dest / 'frozen/documents/r4.txt'
    p.write_text('forged source')
    with pytest.raises(ValueError, match='SOURCE_FREEZE_DRIFT'):
        GroundingVault(dest)


def test_real_prerequisite_evidence_separates_chapters_from_operations():
    _, c, train, evidence, _ = reveal('e1-order')
    r = critique(train, evidence, c['family'])
    assert r['label'] == 'ORDERED'
    assert r['evidence_kind'] == 'EXPLICIT_OPERATIONAL_PREREQUISITE'
    assert r['status'] == 'SOURCE_INTERNAL_SUPPORT'
    assert critique(train, None, c['family'])['label'] == 'UNRESOLVED'


def test_old_body_spirit_reversal_and_gate6_remain_unresolved():
    for case in ['e1-role-identity', 'e1-gate6']:
        _, c, train, evidence, _ = reveal(case)
        assert critique(train, evidence, c['family'])['label'] == 'UNRESOLVED'
    assert calibration_controls()[0]['evidence']['with_premise']['counterexample']['state'] == 1


def test_two_term_senses_do_not_identify_two_specific_mentions():
    _, c, train, evidence, _ = reveal('e1-scope')
    result = critique(train, evidence, c['family'])
    assert result['label'] == 'UNRESOLVED'
    assert result['distinctions']['reference_identity'] == 'UNRESOLVED'


def test_all_declared_adversarial_controls_are_executed():
    rows = run_controls(GroundingVault(ROOT))
    assert len(rows) >= 12
    assert all(r['passed'] for r in rows), [r for r in rows if not r['passed']]


def test_actual_worker_isolation_and_distinct_imports():
    _, c, train, evidence, _ = reveal('e1-order')
    p = asyncio.run(run_worker('propose', {'packet': train.model_dump(), 'family': c['family'], 'project': 'LM_QA_GROUNDING003'}))
    q = asyncio.run(run_worker('critique', {'train': train.model_dump(), 'challenge': evidence.model_dump(), 'family': c['family'], 'project': 'LM_QA_GROUNDING003'}))
    for response in [p, q]:
        assert response['isolation']['probes'] == {'file': 'DENIED', 'socket': 'DENIED'}
        assert response['isolation']['forbidden_modules_loaded'] == []


def test_worker_rejects_expected_label_or_target_result():
    _, c, train, evidence, _ = reveal('e1-order')
    for key in ['expected_label', 'target_result', 'proposal_rationale']:
        with pytest.raises(ValueError):
            asyncio.run(run_worker('critique', {'train': train.model_dump(), 'challenge': evidence.model_dump(),
                'family': c['family'], 'project': 'LM_QA_GROUNDING003', key: 'force success'}))


def test_guard_proof_cannot_pass_as_novel_source_law():
    _, c, train, evidence, hs = reveal('e1-order')
    r = critique(train, evidence, c['family'])
    h = next(h for h in hs if h['prediction']['label'] == r['label'])
    f = formalize(h, r)
    assert f['guard_law']['with_premise']['status'] == 'proved'
    assert f['guard_law']['without_premise']['status'] == 'refuted'
    assert f['scientific_law_status'] == 'FAIL_TARGET_TAUTOLOGY'
    assert f['source_semantics_proved'] is False
    assert f['proof_status'] == 'unverified'


def test_unresolved_source_cannot_enter_formalization():
    _, c, train, evidence, hs = reveal('e2-anaphora')
    r = critique(train, evidence, c['family'])
    with pytest.raises(ValueError, match='INDEPENDENT_SOURCE_BINDING_REQUIRED'):
        formalize(hs[0], r)


def test_context_review_cannot_be_reused_for_foreign_source_or_rejected_H():
    _, c, train, evidence, hs = reveal('e1-order')
    r = critique(train, evidence, c['family'])
    wrong = deepcopy(r); wrong['train_packet_sha256'] = '0' * 64
    selected = next(h for h in hs if h['prediction']['label'] == r['label'])
    with pytest.raises(ValueError, match='ANOTHER_SOURCE'):
        formalize(selected, wrong)
    wrong = deepcopy(r); wrong['reason'] = 'forged justification'
    with pytest.raises(ValueError, match='HASH_DRIFT'):
        formalize(selected, wrong)
    rejected = next(h for h in hs if h['prediction']['label'] != r['label'])
    with pytest.raises(ValueError, match='REJECTS_THIS_READING'):
        formalize(rejected, r)


def test_dropped_source_role_and_provenance_fail_existing_reverse_checker():
    _, c, train, evidence, hs = reveal('s03')
    r = critique(train, evidence, c['family'])
    f = formalize(next(h for h in hs if h['prediction']['label'] == r['label']), r)
    bad = deepcopy(f['candidate'])
    keys = list(bad['mapping']); bad['mapping'][keys[1]] = bad['mapping'][keys[0]]
    assert check_translation(SourceGraph.model_validate(f['source_graph']), bad)['status'] == 'FAIL_FIDELITY'
    bad = deepcopy(f['candidate']); bad['network']['species'][0]['source_refs'] = ['invented']
    assert check_translation(SourceGraph.model_validate(f['source_graph']), bad)['status'] == 'FAIL_FIDELITY'


def test_real_sample_has_no_fabricated_external_annotations():
    cases = json.loads((ROOT / 'frozen/decisions.json').read_text())
    assert 12 <= len(cases) <= 20
    assert sum(c['hard_negative'] for c in cases) >= 4
    assert all(c['external_annotations'] == [] for c in cases)
    assert all(c['control_expected_label'] is None for c in cases if not c['synthetic'])
