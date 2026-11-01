"""Production authorization must not turn a rehearsal into a live writer."""
import hashlib
import json
import os
from pathlib import Path
import shutil

import pytest

import production020 as production


@pytest.fixture
def authorization(tmp_path):
    template = os.environ.get('LM_PRODUCTION020_TEST_AUTH')
    if not template:
        pytest.skip('Deployment authorization fixture not provided; no live authorization inferred')
    source = json.loads(Path(template).read_text())
    plan = {**source, 'mode': 'rehearsal'}
    adapter = tmp_path / 'adapter.py'
    shutil.copy2(source['adapter_path'], adapter)
    plan['adapter_path'] = str(adapter)
    plan['adapter_sha256'] = hashlib.sha256(adapter.read_bytes()).hexdigest()
    path = tmp_path / 'authorization.json'
    path.write_text(json.dumps(plan))
    path.chmod(0o600)
    return path


def test_authorization_file_cannot_be_shared(authorization):
    authorization.chmod(0o644)
    with pytest.raises(ValueError, match='OWNER_ONLY'):
        production.load_authorization(authorization)


def test_release_pin_cannot_be_changed(authorization):
    plan = json.loads(authorization.read_text())
    plan['capsule_sha256'] = '0' * 64
    authorization.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match='AUTHORIZATION_REQUIRED'):
        production.load_authorization(authorization)


def test_changed_adapter_cannot_reuse_authorization(authorization):
    plan = json.loads(authorization.read_text())
    Path(plan['adapter_path']).write_text('changed adapter')
    with pytest.raises(ValueError, match='ADAPTER_DRIFT'):
        production.load_authorization(authorization)


def test_rehearsal_guard_denies_actual_live_database(authorization, monkeypatch):
    plan = production.load_authorization(authorization)
    import deploy018_storage as storage
    original = storage.private_path
    try:
        production.authorize_storage(plan)
        with pytest.raises(ValueError, match='NOT_AUTHORIZED'):
            storage.private_path(Path.home() / '.local/share/livingmath/research.sqlite3')
        assert storage.private_path(plan['_paths']['typed']) == plan['_paths']['typed']
    finally:
        storage.private_path = original
