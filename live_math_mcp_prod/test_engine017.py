"""017 authority/memory contracts on isolated native sources, not production."""
import copy
import json
import os
from pathlib import Path
import sqlite3
import pytest
from normalizer import canonical
from research_store import ResearchStore
from typed_cycle011_store import install as install011
from law_validation014_store import install as guards
from engine017_store import install
from engine017_fixtures import seed
from engine017_controller import EngineController017
from engine017_contract import SourceEnvelope017
from engine017_server import create_server


@pytest.fixture
def context(tmp_path):
    policy_path = Path(os.environ['LM_ENGINE017_POLICY']) if os.environ.get('LM_ENGINE017_POLICY') else Path(Path('/tmp/lm017_path').read_text().strip()) / 'frozen/pre-registration.json'
    policy = json.loads(policy_path.read_text())
    legacy, db = tmp_path / 'legacy.sqlite3', tmp_path / 'engine.sqlite3'
    ResearchStore(legacy)
    ResearchStore(db)
    install011(db, legacy)
    guards(db)
    install(db)
    seals = tmp_path / 'seals'
    seals.mkdir()
    return policy, legacy, db, tmp_path, seals


@pytest.mark.parametrize('family', ['A', 'B', 'C'])
def test_registered_source_uses_old_native_I_T_without_grants(context, family):
    policy, _, db, workspace, seals = context
    f = next(f for f in policy['families'] if f['id'] == family)
    case = next(c for c in policy['cases'] if c['family'] == family and c['expected'] == 'SUCCESS')
    b = seed(db, workspace, seals, f, case, 'UNIT017')
    engine = EngineController017(db)
    preview = engine.preview({'project': b['project']})
    assert preview['status'] == 'PROPOSAL_READY', preview
    assert preview['purpose'] == 'DISCRIMINATE'
    assert not preview['execution_permission']['allowed']
    assert all(r['operation'] != 'E' for r in preview['native_trace'])
    assert all(h['status'] == 'ACTIVE' for h in preview['independent_branch'])
    first = engine.precommit({'project': b['project']}, 'unit')
    assert first == engine.precommit({'project': b['project'], 'known_fingerprints': [], 'display_label': 'alias'}, 'unit')
    assert not first['execution_permission']['allowed']


def test_source_contract_forbids_code_paths_and_truth_status():
    with pytest.raises(ValueError):
        SourceEnvelope017.model_validate({'python': 'print(1)', 'path': '/tmp/source.py', 'verified': True})


def test_history_exposes_persisted_source_selection_and_state_route(context):
    policy, _, db, workspace, seals = context
    world = seed(db, workspace, seals, policy['families'][0], policy['cases'][0], 'UNIT_HISTORY')
    engine = EngineController017(db)
    pc = engine.precommit({'project': world['project']}, 'history')
    view = engine.history(world['project'])
    payload = view['precommits'][0]['payload']
    assert payload['suffix_ordinals'] and payload['source_bindings'] and payload['admissibility_guard']
    assert view['precommits'][0]['preview']['normalization']['loss_ledger'] is not None
    assert view['state_routes'][0]['stages'][-1] == 'AUDITED'
    assert not view['moves'][0]['execution_permission']['allowed']


def test_integrity_distinguishes_engine_requirements_and_legacy_gaps(tmp_path):
    from engine017_integrity import append_only
    db = tmp_path / 'legacy.sqlite3'
    store = ResearchStore(db)
    store.record('LM_QA_LEGACY_SCOPE', 'qa_source', 'fixture', 'A legacy source', 'hypothesis')
    with pytest.raises(ValueError, match='INCOMPLETE_ENGINE_SCHEMA'):
        append_only(db)
    legacy = append_only(db, require_engine=False)
    assert legacy['events:UPDATE'] is False and legacy['operations:DELETE'] is False


def test_feature_disabled_retains_existing_api(context, monkeypatch):
    _, legacy, db, _, _ = context
    monkeypatch.setenv('LIVE_MATH_TYPED_CYCLE_DB', str(db))
    monkeypatch.setenv('LIVE_MATH_NATIVE_PREVIEW', '1')
    monkeypatch.delenv('LIVE_MATH_ENGINE_017', raising=False)
    from mcp_server import create_server as original
    expected = original(ResearchStore(legacy))
    actual = create_server(legacy, db)
    a, b = expected._tool_manager._tools, actual._tool_manager._tools
    assert len(a) == len(b) == 24
    assert {n: t.parameters for n, t in a.items()} == {n: t.parameters for n, t in b.items()}
    assert 'research_cycle_next' not in b


def test_enabled_api_never_exposes_operator_authority(context, monkeypatch):
    _, legacy, db, _, _ = context
    monkeypatch.setenv('LIVE_MATH_TYPED_CYCLE_DB', str(db))
    monkeypatch.setenv('LIVE_MATH_NATIVE_PREVIEW', '1')
    mcp = create_server(legacy, db, True)
    names = set(mcp._tool_manager._tools)
    assert len(names) == 27
    assert {'research_cycle_next', 'research_cycle_history', 'research_source_contract'} <= names
    assert not {'activate', 'execute', 'commit', 'register_source'} & names


@pytest.mark.parametrize('bad', [{'version': 2}, {'observer': {'projection': 'primary', 'mod': 2}}, {'context_level': 'C4'}, {'source_id': 'wrong'}])
def test_source_rebind_fails_closed(context, bad):
    policy, _, db, workspace, seals = context
    b = seed(db, workspace, seals, policy['families'][0], policy['cases'][0], 'UNIT_REBIND')
    result = EngineController017(db).preview({'project': b['project'], **bad})
    assert result['status'] == 'INSUFFICIENT_CONTEXT'
    assert not result['execution_permission']['allowed']
