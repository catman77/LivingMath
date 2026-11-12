"""Durability and compatibility boundaries beyond geometric construction."""
import copy
import importlib.util
from pathlib import Path
from unittest.mock import patch
import pytest
from lm_suti_assurance.core import digest
from lm_suti_assurance.errors import AssuranceError
from lm_suti_assurance.completeness import service as module
from test_completeness import pool, setup, load, request


def test_failed_commit_does_not_publish_receipts_or_advance(setup):
    import lm_suti_assurance.workspace as workspace
    s, start, _ = setup
    w = s.base.workspace('qa')
    journal = (w.path/'journal.jsonl').read_bytes()
    original = workspace.atomic_write
    def crash(path, raw):
        if path.name == 'journal.jsonl':
            raise OSError('injected crash before durable journal commit')
        return original(path, raw)
    with patch.object(workspace, 'atomic_write', crash):
        with pytest.raises(OSError): s.advance('qa', start['plan_ref'], 'crash', start['cursor'], 3)
    assert (w.path/'journal.jsonl').read_bytes() == journal
    assert s.inspect('qa', start['plan_ref'])['computed_count'] == 0
    resumed = s.advance('qa', start['plan_ref'], 'crash', start['cursor'], 3)
    assert resumed['computed_count'] == 3


def test_changed_kernel_fails_closed(setup):
    s, start, _ = setup
    with patch.object(module, 'kernel_binding', return_value={'sha256': '0'*64}):
        with pytest.raises(AssuranceError, match='KERNEL_BINDING_MISMATCH'):
            s.advance('qa', start['plan_ref'], 'mismatch', start['cursor'], 1)


def test_plan_retry_conflict_and_changed_scope_need_new_plan(setup):
    s, start, q = setup
    from lm_suti_assurance.completeness.contracts import SCOPE
    assert s.plan('qa', 'plan', q, SCOPE) == start
    q['encoding']['protocol']['seed'] += 1
    with pytest.raises(AssuranceError, match='REQUEST_KEY_CONFLICT'): s.plan('qa', 'plan', q, SCOPE)
    changed = s.plan('qa', 'new-scope', q, SCOPE)
    assert changed['plan_ref'] != start['plan_ref']
    with pytest.raises(AssuranceError, match='CURSOR_PREFIX_MISMATCH'):
        s.advance('qa', changed['plan_ref'], 'wrong-scope', start['cursor'], 1)


def test_atlas_and_omissions_have_full_pagination(setup):
    s, start, _ = setup
    plan = load(s, start['plan_ref'])
    for view, expected in [('atlas', plan['atlas']['charts']), ('omissions', plan['atlas']['omitted_collinear_pairs']), ('plan', plan['obligations'])]:
        rows, index = [], 0
        while True:
            page = s.inspect('qa', start['plan_ref'], view, index, 3)
            rows += page['records']
            if page['next_cursor'] is None: break
            index = page['next_cursor']
        assert rows == expected


def test_existing_tool_definitions_do_not_change(tmp_path):
    path = Path(__file__).resolve().parents[1]/'tools/completeness001_server.py'
    spec = importlib.util.spec_from_file_location('coverage_server_test', path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    server = m.build(tmp_path/'state', coverage=False)
    def signatures():
        return {t.name: t.model_dump(exclude={'fn', 'fn_metadata'}) for t in server._tool_manager.list_tools()}
    old = signatures()
    from lm_suti_assurance.completeness.mcp import register_tools
    register_tools(server, tmp_path/'state')
    new = signatures()
    assert len(new) == len(old)+4 and all(new[k] == v for k, v in old.items())


@pytest.mark.parametrize('audience', ['public', 'reviewers', 'private'])
def test_generic_bundle_cannot_leak_private_input_or_claim_unsupported_replay(setup, audience):
    from lm_suti_assurance.bundle import export_bundle
    s, _, _ = setup
    with pytest.raises(AssuranceError, match='COVERAGE_EXPORT_REQUIRES_PLAN_REF'):
        export_bundle(s.base.workspace('qa'), audience)
