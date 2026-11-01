"""Release boundary tests; no mathematical source or production state changes."""
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import zipfile

import pytest

import release020 as rc


@pytest.fixture(scope='module')
def capsule(tmp_path_factory):
    original = os.environ.get('LM020_ORIGINAL_ZIP')
    if not original:
        pytest.skip('Actual signed019 ZIP required; no synthetic replacement')
    base = tmp_path_factory.mktemp('rc020')
    docs = base / 'docs'
    docs.mkdir()
    (docs / 'OWNER_RELEASE_DECISION.md').write_text('AWAITING_OWNER_SIGNOFF\n')
    key = base / 'private.pem'
    subprocess.run(['openssl', 'genpkey', '-algorithm', 'Ed25519', '-out', str(key)], check=True)
    out = base / 'package'
    rc.build(Path(original), docs, out, key)
    return out


def copy(capsule, tmp_path):
    out = tmp_path / 'copy'
    shutil.copytree(capsule, out)
    return out


def test_original_bytes_and_authority_remain_distinct(capsule):
    result = rc.verify(capsule, rc.key_hash(capsule / 'RC_PUBLIC.pem'))
    assert result['runtime_version'] == '1.0.0b1'
    assert result['distribution_version'] == '1.0.0rc1'
    assert result['owner_approval'] == 'AWAITING_OWNER_SIGNOFF'
    assert rc.sha(capsule / 'provenance/capsule-019.zip') == rc.ORIGINAL_ZIP


@pytest.mark.parametrize('name', ['core019/source/beta019_executor.py', 'OWNER_RELEASE_DECISION.md'])
def test_tampered_code_or_owner_dossier_cannot_delegate(capsule, tmp_path, name, monkeypatch):
    package = copy(capsule, tmp_path)
    (package / name).write_text('tampered')
    monkeypatch.setattr('sys.argv', ['release020.py', '--package', str(package), 'install', '--root', str(tmp_path / 'install')])
    def forbidden(*args):
        pytest.fail('Unverified payload reached delegate')
    monkeypatch.setattr(rc, 'delegate', forbidden)
    assert rc.main() == 2
    assert not (tmp_path / 'install').exists()


def test_extra_executable_file_is_rejected(capsule, tmp_path):
    package = copy(capsule, tmp_path)
    (package / 'core019/source/evil.py').write_text('raise RuntimeError("must never run")')
    with pytest.raises(ValueError, match='UNLISTED'):
        rc.verify(package)


def test_symlink_directory_is_rejected(capsule, tmp_path):
    link = tmp_path / 'package'
    link.symlink_to(capsule, target_is_directory=True)
    with pytest.raises(ValueError, match='SYMLINK'):
        rc.verify(link)


def test_wrong_external_trust_anchor_is_rejected(capsule):
    with pytest.raises(ValueError, match='TRUSTED_KEY_MISMATCH'):
        rc.verify(capsule, '0' * 64)


def test_bad_release_signature_is_rejected(capsule, tmp_path):
    package = copy(capsule, tmp_path)
    (package / 'RC_SIGNATURE.sig').write_bytes(b'\0' * 64)
    with pytest.raises(ValueError, match='SIGNATURE'):
        rc.verify(package)


@pytest.mark.parametrize('name', ['../outside.py', '/outside.py', 'core\\outside.py'])
def test_unsafe_archive_names(name):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as z:
        z.writestr(name, 'no execution')
    with zipfile.ZipFile(stream) as z, pytest.raises(ValueError, match='UNSAFE'):
        rc.members(z)


def test_archive_symlink_is_rejected():
    stream = io.BytesIO()
    info = zipfile.ZipInfo('link')
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(stream, 'w') as z:
        z.writestr(info, '../outside')
    with zipfile.ZipFile(stream) as z, pytest.raises(ValueError, match='UNSAFE'):
        rc.members(z)


def test_missing_original_is_not_reconstructed(tmp_path):
    with pytest.raises(ValueError, match='MISSING_RELEASE_ARTIFACT'):
        rc.extract_original(tmp_path / 'missing.zip', tmp_path / 'original')
    assert not (tmp_path / 'original').exists()


def test_owner_approved_manifest_is_never_generated(capsule):
    manifest = json.loads((capsule / 'RC_MANIFEST.json').read_text())
    assert manifest['owner_approval'] == 'AWAITING_OWNER_SIGNOFF'
    assert manifest['production_deployment'] == 'NOT_PERFORMED'
