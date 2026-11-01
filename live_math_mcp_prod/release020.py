"""Release-only signed bootstrap; delegates to the byte-identical019 engine.

No MCP tools, source adapters, owner decisions or runtime migrations are added.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

VERSION = '1.0.0rc1'
ORIGINAL_ZIP = '58a567adfdbc6e96e549435c020b6eab6f861ceda9ddb50fdfd320ec08f39795'
ORIGINAL_MANIFEST = 'b5b92f6b4f60e7996b1e877fb52323d9528c6da95135954878cde888f1983081'
ORIGINAL_KEY = '3c667fa6a7da5dc96666412773a7b9be81a32399dd60400361ff675b50cc4565'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def openssl(*args: str) -> bytes:
    process = subprocess.run(['openssl', *map(str, args)], capture_output=True, timeout=30)
    if process.returncode:
        raise ValueError('020_SIGNATURE_OR_KEY_INVALID')
    return process.stdout


def key_hash(key: Path) -> str:
    der = openssl('pkey', '-pubin', '-in', key, '-outform', 'DER')
    # Ed25519 SubjectPublicKeyInfo has a fixed12-byte DER prefix.
    if len(der) != 44 or der[:12] != bytes.fromhex('302a300506032b6570032100'):
        raise ValueError('020_ED25519_KEY_REQUIRED')
    return hashlib.sha256(der[12:]).hexdigest()


def signed(manifest: Path, key: Path, signature: Path) -> None:
    openssl('pkeyutl', '-verify', '-pubin', '-inkey', key, '-rawin', '-in', manifest, '-sigfile', signature)


def members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    entries, seen, total = archive.infolist(), set(), 0
    for entry in entries:
        path = PurePosixPath(entry.filename)
        if (not entry.filename or path.is_absolute() or '..' in path.parts
                or '\\' in entry.filename or entry.filename in seen
                or stat.S_ISLNK(entry.external_attr >> 16)):
            raise ValueError('020_UNSAFE_ARCHIVE_MEMBER')
        seen.add(entry.filename)
        total += entry.file_size
    if total > 64 * 1024 * 1024 or len(entries) > 2000:
        raise ValueError('020_ARCHIVE_BUDGET_EXCEEDED')
    return entries


def tree_files(root: Path) -> set[str]:
    result = set()
    if root.is_symlink():
        raise ValueError('020_SYMLINK_PACKAGE')
    for path in root.rglob('*'):
        if path.is_symlink():
            raise ValueError('020_SYMLINK_PACKAGE')
        if path.is_file():
            result.add(path.relative_to(root).as_posix())
    return result


def hash_tree(root: Path, expected: dict, extra: set[str]) -> None:
    if tree_files(root) != set(expected) | extra:
        raise ValueError('020_UNLISTED_OR_MISSING_FILE')
    for name, digest in expected.items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name or sha(root / name) != digest:
            raise ValueError('020_FILE_HASH_MISMATCH:' + name)


def original_tree(core: Path) -> dict:
    if sha(core / 'release-manifest.json') != ORIGINAL_MANIFEST:
        raise ValueError('020_ORIGINAL_MANIFEST_MISMATCH')
    if key_hash(core / 'release-public.pem') != ORIGINAL_KEY:
        raise ValueError('020_ORIGINAL_KEY_MISMATCH')
    signed(core / 'release-manifest.json', core / 'release-public.pem', core / 'release.sig')
    manifest = json.loads((core / 'release-manifest.json').read_text())
    hash_tree(core, manifest['files'], {'release-manifest.json', 'release.sig'})
    return manifest


def extract_original(archive: Path, destination: Path) -> Path:
    if not archive.is_file():
        raise ValueError('MISSING_RELEASE_ARTIFACT')
    if sha(archive) != ORIGINAL_ZIP:
        raise ValueError('020_ORIGINAL_ZIP_MISMATCH')
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive) as z:
        entries = members(z)
        if any(PurePosixPath(e.filename).parts[0] != 'capsule-3' for e in entries):
            raise ValueError('020_ORIGINAL_NAMESPACE_MISMATCH')
        if z.testzip() is not None:
            raise ValueError('020_ORIGINAL_CRC_FAILURE')
        z.extractall(destination)
    core = destination / 'capsule-3'
    original_tree(core)
    return core


def verify(package: Path, expected_key: str | None = None) -> dict:
    package = package.absolute()
    actual_key = key_hash(package / 'RC_PUBLIC.pem')
    if expected_key is not None and actual_key != expected_key:
        raise ValueError('020_TRUSTED_KEY_MISMATCH')
    signed(package / 'RC_MANIFEST.json', package / 'RC_PUBLIC.pem', package / 'RC_SIGNATURE.sig')
    manifest = json.loads((package / 'RC_MANIFEST.json').read_text())
    if (manifest['version'] != VERSION or manifest['original_zip_sha256'] != ORIGINAL_ZIP
            or manifest['original_manifest_sha256'] != ORIGINAL_MANIFEST
            or manifest['owner_approval'] != 'AWAITING_OWNER_SIGNOFF'):
        raise ValueError('020_RELEASE_CONTRACT_MISMATCH')
    hash_tree(package, manifest['files'], {'RC_MANIFEST.json', 'RC_SIGNATURE.sig'})
    original_tree(package / 'core019')
    if sha(package / 'provenance/capsule-019.zip') != ORIGINAL_ZIP:
        raise ValueError('020_ORIGINAL_ZIP_MISMATCH')
    return {'status': 'PASS', 'distribution_version': VERSION, 'runtime_version': '1.0.0b1',
        'protocol': 'livingmath-research019/v1', 'public_key_sha256': actual_key,
        'manifest_sha256': sha(package / 'RC_MANIFEST.json'), 'owner_approval': 'AWAITING_OWNER_SIGNOFF',
        'production_deployment': 'NOT_PERFORMED', 'proof_status': 'unverified'}


def build(original: Path, documents: Path, out: Path, key: Path) -> dict:
    if not original.is_file():
        raise ValueError('MISSING_RELEASE_ARTIFACT')
    out.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='lm020-original-') as temp:
        core = extract_original(original, Path(temp) / 'extracted')
        shutil.copytree(core, out / 'core019')
    (out / 'provenance').mkdir()
    shutil.copy2(original, out / 'provenance/capsule-019.zip')
    if documents:
        for path in documents.rglob('*'):
            if path.is_symlink():
                raise ValueError('020_SYMLINK_DOCUMENT')
            if path.is_file():
                relative = path.relative_to(documents)
                if relative.parts[0] in ('core019', 'provenance', 'release020.py', 'reproduce.sh', 'RC_PUBLIC.pem', 'RC_MANIFEST.json', 'RC_SIGNATURE.sig'):
                    raise ValueError('020_DOCUMENT_OVERRIDES_CODE')
                target = out / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
    shutil.copy2(Path(__file__), out / 'release020.py')
    (out / 'reproduce.sh').write_text('''#!/usr/bin/env bash
set -euo pipefail
RC_PACKAGE=$(cd -- "$(dirname -- "$0")" && pwd)
RC_PYTHON=${PYTHON:-python3}
export PYTHONDONTWRITEBYTECODE=1
exec "$RC_PYTHON" "$RC_PACKAGE/release020.py" --package "$RC_PACKAGE" reproduce --work "${1:?Specify a NEW private work directory}"
''')
    (out / 'reproduce.sh').chmod(0o755)
    (out / 'RC_PUBLIC.pem').write_bytes(openssl('pkey', '-in', key, '-pubout'))
    manifest = {'version': VERSION, 'runtime_version': '1.0.0b1', 'protocol': 'livingmath-research019/v1',
        'original_zip_sha256': ORIGINAL_ZIP, 'original_manifest_sha256': ORIGINAL_MANIFEST,
        'owner_approval': 'AWAITING_OWNER_SIGNOFF', 'production_deployment': 'NOT_PERFORMED',
        'files': {name: sha(out / name) for name in sorted(tree_files(out))}}
    (out / 'RC_MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
    openssl('pkeyutl', '-sign', '-inkey', key, '-rawin', '-in', out / 'RC_MANIFEST.json', '-out', out / 'RC_SIGNATURE.sig')
    return verify(out, key_hash(out / 'RC_PUBLIC.pem'))


def delegate(package: Path, action: str, work: Path | None, root: Path | None) -> int:
    # All executable payload files are checked before any subprocess can run.
    core = package / 'core019'
    environment = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
    if action == 'reproduce':
        if work is None:
            raise ValueError('020_NEW_WORK_REQUIRED')
        argv = [sys.executable, str(core / 'source/beta019_reproduce.py'), '--package', str(core), '--work', str(work)]
    else:
        if root is None:
            raise ValueError('020_INSTALL_ROOT_REQUIRED')
        argv = [sys.executable, str(core / 'source/beta019_install.py'), '--package', str(core), '--root', str(root), action]
    return subprocess.run(argv, env=environment).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--expected-key', help='Raw Ed25519 public key SHA256 from an independently checked release record')
    parser.add_argument('action', choices=['verify', 'install', 'uninstall', 'reproduce'])
    parser.add_argument('--work', type=Path)
    parser.add_argument('--root', type=Path)
    args = parser.parse_args()
    try:
        checked = verify(args.package, args.expected_key)
        if args.action == 'verify':
            print(json.dumps(checked))
            return 0
        return delegate(args.package.resolve(), args.action, args.work, args.root)
    except (ValueError, OSError, KeyError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        print(json.dumps({'status': 'STOP_WITH_RCA', 'error': str(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
