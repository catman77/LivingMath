import json
import hashlib

import pytest

from causal_finalize import finalize, postrun_oracle_preserved


def test_partial_matrix_cannot_be_reported_complete_or_touch_the_database(tmp_path):
    (tmp_path / 'model_outputs.jsonl').write_text(json.dumps({'id': 'w00-r0-M0-t0'}) + '\n')
    with pytest.raises(RuntimeError, match='incomplete or duplicated'):
        finalize(tmp_path)
    assert list(tmp_path.iterdir()) == [tmp_path / 'model_outputs.jsonl']


def test_duplicate_outcomes_are_not_silently_collapsed_into_a_pass(tmp_path):
    row = json.dumps({'id': 'w00-r0-M0-t0'}) + '\n'
    (tmp_path / 'model_outputs.jsonl').write_text(row + row)
    with pytest.raises(RuntimeError, match='incomplete or duplicated'):
        finalize(tmp_path)


def postrun_fixture(tmp_path):
    source = tmp_path / 'live_math_mcp_prod'
    source.mkdir()
    (source / 'causal_oracle.py').write_text('new QA rules')
    (tmp_path / 'causal_oracle-frozen-1.1.py').write_text('old frozen rules')
    (tmp_path / 'model_outputs.jsonl').write_text('untouched historical outcomes')
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    before = digest(tmp_path / 'causal_oracle-frozen-1.1.py')
    manifest = {'matrix_completed_before_patch': True, 'new_model_calls_after_patch': 0,
        'matrix_scores_replaced': False, 'before_file_sha256': before,
        'after_file_sha256': digest(source / 'causal_oracle.py'),
        'primary_jsonl_sha256': digest(tmp_path / 'model_outputs.jsonl')}
    (tmp_path / 'postrun-oracle-fix.json').write_text(json.dumps(manifest))
    return [{'metrics': {'scorer_version': '1.1'}}] * 432, {'live_math_mcp_prod/causal_oracle.py': before}


def test_later_qa_patch_can_preserve_the_complete_historical_matrix(tmp_path):
    rows, frozen = postrun_fixture(tmp_path)
    assert postrun_oracle_preserved(tmp_path, tmp_path, rows, frozen)
    assert not postrun_oracle_preserved(tmp_path, tmp_path, rows[:-1], frozen)


def test_later_patch_manifest_cannot_authorize_changing_old_scores(tmp_path):
    rows, frozen = postrun_fixture(tmp_path)
    (tmp_path / 'model_outputs.jsonl').write_text('rewritten outcomes')
    assert not postrun_oracle_preserved(tmp_path, tmp_path, rows, frozen)
