"""Fresh-checkout installation must preserve sources and isolate private state."""
import hashlib
import json
from pathlib import Path

import pytest


def test_published_assets_build_without_author_archives(tmp_path):
    import shutil

    from unified_system.assets import Assets, build
    repo = Path(__file__).resolve().parent.parent
    shutil.copytree(repo / 'assets/unified', tmp_path / 'repo/assets/unified')
    build(tmp_path / 'repo', tmp_path / 'out')
    assert Assets(tmp_path / 'out').manifest == Assets(repo / 'assets/unified').manifest
    (tmp_path / 'repo/assets/unified/bridge.json').write_text('{}')
    with pytest.raises(ValueError, match='HASH_DRIFT'):
        build(tmp_path / 'repo', tmp_path / 'bad')


def test_published_bundle_does_not_hide_changed_author_archive(tmp_path):
    import shutil

    from unified_system.assets import Assets, build
    repo = Path(__file__).resolve().parent.parent
    shutil.copytree(repo / 'assets/unified', tmp_path / 'repo/assets/unified')
    pairs = Assets(repo / 'assets/unified').bridge['pairs']
    (tmp_path / 'repo/bridge004').mkdir()
    (tmp_path / 'repo/bridge004/frozen-pairs.json').write_text(json.dumps(pairs))
    (tmp_path / 'repo/SUTI.uni.zip').write_bytes(b'changed original archive')
    with pytest.raises(ValueError, match='SUTI_WORKING_ARCHIVE_HASH_DRIFT'):
        build(tmp_path / 'repo', tmp_path / 'out')


@pytest.mark.parametrize('name', ['../production', '/tmp/instance', 'a/b', '.', ''])
def test_instance_name_cannot_select_an_arbitrary_path(name):
    from unified_system.local import instance_root
    with pytest.raises(ValueError, match='INSTANCE_NAME'):
        instance_root(name)


def test_fresh_instance_and_existing_instance_preservation(tmp_path, monkeypatch):
    from research_store import ResearchStore
    from unified_system import local
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))
    # Network vocabulary acquisition is separately exercised in the real clean install.
    monkeypatch.setattr(local, '_warm_tokenizer', lambda cache: (cache / 'unit-cache').write_bytes(b'unit-only'))
    repo = Path(__file__).resolve().parent.parent
    cfg = local.prepare(repo, 'checkout-test', 0)
    root = local.instance_root('checkout-test')
    assert not root.stat().st_mode & 0o077
    assert not (root / 'data-config.json').stat().st_mode & 0o077
    assert cfg['origin'].startswith('https://localhost:') and cfg['port'] > 0
    assert ResearchStore(Path(cfg['data']) / 'research.sqlite3').health()['sqlite_integrity'] == 'ok'
    assert local.configuration('checkout-test')['layer_manifest_sha256'] == cfg['layer_manifest_sha256']
    original = (root / 'data/research.sqlite3').read_bytes()
    with pytest.raises(FileExistsError):
        local.prepare(repo, 'checkout-test', 0)
    assert (root / 'data/research.sqlite3').read_bytes() == original
    p = root / 'layer/assets/bridge.json'
    p.write_bytes(p.read_bytes() + b' ')
    with pytest.raises(ValueError, match='LAYER_HASH_DRIFT'):
        local.configuration('checkout-test')


@pytest.mark.parametrize('origin', ['http://localhost:18766', 'https://a.invalid/path', 'https://user:secret@a.invalid', 'https://a.invalid/?token=x'])
def test_origin_rejects_insecure_or_nonissuer_urls(origin):
    from unified_system.local import validate_origin
    with pytest.raises(ValueError, match='HTTPS_ORIGIN_REQUIRED'):
        validate_origin(origin)


def test_native_source_fixture_is_original_and_detects_drift(tmp_path):
    from checkout_test_support import native_source
    source = Path(__file__).parent / 'testdata/xi015_source'
    manifest = json.loads((source / 'manifest.json').read_text())
    native_source(tmp_path / 'copy', tmp_path / 'absent.zip')
    for name, sha in manifest['files'].items():
        assert hashlib.sha256((tmp_path / 'copy' / name).read_bytes()).hexdigest() == sha
    import shutil
    shutil.copytree(source, tmp_path / 'broken')
    (tmp_path / 'broken/vendor/source.py').write_bytes(b'changed')
    with pytest.raises(ValueError, match='PINNED_SOURCE_DRIFT'):
        native_source(tmp_path / 'bad', tmp_path / 'absent.zip', snapshot=tmp_path / 'broken')
