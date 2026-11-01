"""Stdlib bootstrap for a signed, hash-locked private beta installation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time


def verify_package(package: Path) -> dict:
    manifest = json.loads((package / 'release-manifest.json').read_text())
    for name, expected in manifest['files'].items():
        rel = Path(name)
        if rel.is_absolute() or '..' in rel.parts or (package / rel).is_symlink() or hashlib.sha256((package / rel).read_bytes()).hexdigest() != expected:
            raise ValueError('019_PACKAGE_HASH_MISMATCH:' + name)
    p = subprocess.run(['openssl', 'pkeyutl', '-verify', '-pubin', '-inkey', str(package / 'release-public.pem'),
        '-rawin', '-in', str(package / 'release-manifest.json'), '-sigfile', str(package / 'release.sig')], capture_output=True, text=True)
    if p.returncode:
        raise ValueError('019_RELEASE_SIGNATURE_INVALID')
    return manifest


def install(package: Path, root: Path) -> dict:
    package, root = package.resolve(strict=True), root.resolve()
    if sys.version_info[:2] not in ((3, 12), (3, 13)) or platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise ValueError('019_UNTESTED_PLATFORM; Linux x86_64 Python3.12/3.13 required')
    manifest = verify_package(package)
    source_sha = hashlib.sha256((package / 'release-manifest.json').read_bytes()).hexdigest()
    marker = root / '.beta019-install.json'
    if root.exists() and any(root.iterdir()) and not marker.exists():
        raise ValueError('019_REFUSE_UNOWNED_INSTALL_ROOT')
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    prior = json.loads(marker.read_text()) if marker.exists() else None
    if prior and prior['manifest_sha256'] != source_sha:
        raise ValueError('019_INSTALL_VERSION_CONFLICT_REVIEW_REQUIRED')
    code, venv = root / 'code', root / 'venv'
    idempotent = code.exists() and (venv / 'bin/python').exists()
    if not prior:
        marker.write_text(json.dumps({'manifest_sha256': source_sha, 'root': str(root), 'release': manifest['version'], 'scope': 'private beta only'}, indent=2) + '\n')
    if code.is_symlink():
        raise ValueError('019_REFUSE_SYMLINK_INSTALL_DIRECTORY')
    code.mkdir(exist_ok=True)
    expected_files = {name[7:] for name in manifest['files'] if name.startswith('source/')}
    extras = {str(p.relative_to(code)) for p in code.rglob('*') if p.is_file() and '__pycache__' not in p.parts} - expected_files
    if extras:
        raise ValueError('019_UNLISTED_INSTALLED_FILES:' + ','.join(sorted(extras)))
    for name in expected_files:
        target = code / name
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(package / 'source' / name, target)
    for name, expected in manifest['files'].items():
        if name.startswith('source/') and hashlib.sha256((code / name[7:]).read_bytes()).hexdigest() != expected:
            raise ValueError('019_INSTALLED_CODE_DRIFT:' + name)
    if not (venv / 'bin/python').exists():
        subprocess.run([sys.executable, '-m', 'venv', str(venv)], check=True)
        with (root / 'portable-install-log.txt').open('a') as log:
            p = subprocess.run([str(venv / 'bin/python'), '-m', 'pip', 'install', '--disable-pip-version-check', '--require-hashes',
                '-r', str(package / 'requirements.lock')], stdout=log, stderr=subprocess.STDOUT, timeout=600)
        if p.returncode:
            raise RuntimeError('019_LOCKED_DEPENDENCY_INSTALL_FAILED:' + str(p.returncode))
    result = subprocess.run([str(venv / 'bin/python'), str(code / 'beta019_admin.py'), '--root', str(root), 'init'], capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError('019_SCHEMA_BOOT_FAILED:' + result.stdout + result.stderr)
    return {'status': 'PASS', 'idempotent': idempotent, 'root': str(root), 'manifest_sha256': source_sha,
        'schema': json.loads(result.stdout), 'python': subprocess.check_output([str(venv / 'bin/python'), '--version'], text=True).strip()}


def uninstall(root: Path) -> dict:
    root = root.resolve(); marker = root / '.beta019-install.json'
    if not marker.exists() or json.loads(marker.read_text())['root'] != str(root):
        raise ValueError('019_OWNED_INSTALL_REQUIRED')
    for proc in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            argv = proc.read_bytes().split(b'\0')
        except OSError:
            continue
        if str(root / 'code/beta019_http.py').encode() in argv:
            raise ValueError('019_STOP_OWNED_BETA_SERVICE_BEFORE_UNINSTALL')
    for name in ('code', 'venv'):
        path = root / name
        if path.is_symlink():
            raise ValueError('019_REFUSE_SYMLINK_INSTALL_DIRECTORY')
        if path.exists():
            shutil.rmtree(path)
    return {'status': 'PASS', 'state_seals_exports_and_audit_retained': True, 'production_changed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--package', type=Path, required=True); parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('action', choices=['install', 'verify', 'uninstall']); args = parser.parse_args()
    try:
        result = install(args.package, args.root) if args.action == 'install' else uninstall(args.root) if args.action == 'uninstall' else verify_package(args.package)
        print(json.dumps({'ok': True, 'result': result}))
    except (ValueError, OSError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print(json.dumps({'ok': False, 'error': str(error)})); raise SystemExit(2)
