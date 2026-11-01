"""Beta namespace recovery preserves both scientific DBs and original files."""
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from beta019_admin import initialise, export_snapshot, restore_snapshot
from deploy018_storage import inventory
from research_store import ResearchStore


def test_idempotent_init_has_no_scientific_delta(tmp_path):
    root = tmp_path / 'beta'
    initialise(root)
    before = inventory(root / 'state/beta.sqlite3')
    result = initialise(root)
    assert result['migrations']['typed']['idempotent']
    assert inventory(root / 'state/beta.sqlite3') == before


def test_sigkill_namespace_restore_recovers_both_databases(tmp_path):
    root = tmp_path / 'beta'; initialise(root)
    ResearchStore(root / 'state/beta.sqlite3').record('LM_QA_019_RESTORE', 'qa_source', 'fixture', 'Private finite source', 'hypothesis')
    exported = export_snapshot(root)
    before = {n: inventory(root / 'state' / n) for n in ('research.sqlite3', 'beta.sqlite3')}
    p = subprocess.run([sys.executable, str(Path(__file__).with_name('beta019_admin.py')), '--root', str(root), 'restore',
        '--snapshot', exported['snapshot']], env={**os.environ, 'LM018_FAULT': '019_restore_after_rename'}, capture_output=True, timeout=120)
    assert p.returncode == -9, p.stdout + p.stderr
    assert not (root / 'state').exists() and (root / 'restore-plan.json').exists()
    result = initialise(root)
    assert result['recovery']['recovered']
    for n, old in before.items():
        after = inventory(root / 'state' / n)
        assert after['inode'] != old['inode']
        assert after['logical_sha256'] == old['logical_sha256'] and after['chain'] == old['chain']
    assert Path(result['recovery']['preserved_original_state']).exists()


def test_newer_append_only_data_cannot_be_rolled_back(tmp_path):
    root = tmp_path / 'beta'; initialise(root)
    saved = export_snapshot(root)
    ResearchStore(root / 'state/beta.sqlite3').record('LM_QA_019_RESTORE', 'experiment', 'New evidence', 'Do not erase this event', 'experiment')
    before = inventory(root / 'state/beta.sqlite3')
    with pytest.raises(ValueError, match='REFUSE_STALE_OR_INVALID_SNAPSHOT'):
        restore_snapshot(root, Path(saved['snapshot']))
    assert inventory(root / 'state/beta.sqlite3') == before
    assert not (root / 'restore-plan.json').exists()


def test_archive_inspection_verifies_real_committed_source_artifact(tmp_path):
    from test_beta019 import measurement
    from beta019_operator import commit
    from beta019_admin import inspect
    root = tmp_path / 'beta'; initialise(root)
    seals = root / 'seals'; seals.mkdir()
    db = root / 'state/beta.sqlite3'
    _, _, _, _, request = measurement((db, root / 'state', seals))
    commit(db, request)
    report = inspect(root)
    assert len(report['committed_artifacts']) == 1
    assert report['committed_artifacts'][0]['artifact_hash_and_signature'] == 'PASS'
    assert report['proof_status'] == 'unverified'
