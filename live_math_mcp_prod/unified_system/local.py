"""Compose the existing unified server on a fresh, owner-private checkout instance."""
import argparse
import asyncio
import hashlib
import json
import os
import re
import resource
import shutil
import socket
import ssl
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

from . import VERSION


def instance_root(name: str) -> Path:
    """Instances live separately from every existing deployment."""
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,47}', name):
        raise ValueError('INSTANCE_NAME_REQUIRED: lowercase letters, digits, underscore or hyphen')
    root = Path.home() / '.local/state/livingmath/checkouts' / name
    if root.is_symlink() or not root.resolve().is_relative_to(root.parent.resolve()):
        raise ValueError('INSTANCE_NAME_SYMLINK_NOT_ALLOWED')
    return root


def validate_origin(value: str) -> str:
    """OAuth issuer is a single HTTPS origin, without paths or credentials."""
    url = urlsplit(value)
    if (url.scheme != 'https' or not url.hostname or url.username or url.password
            or url.path or url.query or url.fragment):
        raise ValueError('HTTPS_ORIGIN_REQUIRED: https://hostname[:port]')
    return value


def _warm_tokenizer(cache: Path) -> None:
    # Fresh interpreter avoids an in-memory tiktoken cache masking a missing file.
    subprocess.run([sys.executable, '-I', '-B', '-c',
        'import tiktoken; tiktoken.get_encoding("o200k_base")'],
        env={**os.environ, 'TIKTOKEN_CACHE_DIR': str(cache)}, check=True, timeout=120)
    if not any(cache.iterdir()):
        raise ValueError('PUBLIC_TOKENIZER_CACHE_NOT_CREATED')


def prepare(repo: Path, name: str, port: int) -> dict:
    """Initialize a NEW instance using existing migrations and reviewed assets."""
    from .assets import build
    from .install009 import initialize
    root = instance_root(name)
    if root.exists():
        raise FileExistsError('INSTANCE_ALREADY_EXISTS: choose another name; existing data is preserved')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', port))
        port = listener.getsockname()[1]
    previous = os.umask(0o077)
    try:
        root.mkdir(parents=True, mode=0o700, exist_ok=False)
        layer = root / 'layer'
        layer.mkdir()
        build(repo.resolve(strict=True), layer / 'assets')
        cache = layer / 'dependency_cache'
        cache.mkdir()
        _warm_tokenizer(cache)
        manifest = {str(p.relative_to(layer)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(layer.rglob('*')) if p.is_file()}
        manifest_file = layer / 'manifest.json'
        manifest_file.write_text(json.dumps(manifest, indent=2) + '\n')
        cfg = initialize(root / 'data', layer)
        cfg.update(version=VERSION, port=port, origin='https://localhost:' + str(port),
            layer_manifest_sha256=hashlib.sha256(manifest_file.read_bytes()).hexdigest())
        (root / 'data-config.json').write_text(json.dumps(cfg, indent=2) + '\n')
        return cfg
    finally:
        os.umask(previous)


def configuration(name: str) -> dict:
    """Read only an owner-private config and verify its immutable asset layer."""
    root = instance_root(name).resolve(strict=True)
    path = root / 'data-config.json'
    if path.is_symlink() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise ValueError('OWNER_PRIVATE_CONFIGURATION_REQUIRED')
    cfg = json.loads(path.read_text())
    if cfg['version'] != VERSION:
        raise ValueError('INSTANCE_VERSION_CHANGED: use a new instance for the new checkout')
    for key in ['data', 'layer', 'cert', 'key', 'password']:
        if not Path(cfg[key]).resolve(strict=True).is_relative_to(root):
            raise ValueError('INSTANCE_PATH_BINDING_REQUIRED:' + key)
    layer = Path(cfg['layer'])
    manifest_file = layer / 'manifest.json'
    if hashlib.sha256(manifest_file.read_bytes()).hexdigest() != cfg['layer_manifest_sha256']:
        raise ValueError('LAYER_HASH_DRIFT:manifest.json')
    for member, expected in json.loads(manifest_file.read_text()).items():
        p = (layer / member).resolve(strict=True)
        if not p.is_relative_to(layer) or hashlib.sha256(p.read_bytes()).hexdigest() != expected:
            raise ValueError('LAYER_HASH_DRIFT:' + member)
    validate_origin(cfg['origin'])
    return cfg


def serve(name: str, *, origin: str | None = None, with_codex: bool = False,
          model: str = 'gpt-6.1-sol') -> None:
    """Run existing44-tool HTTPS/OAuth app; model backend is explicitly opt-in."""
    cfg = configuration(name)
    issuer = validate_origin(origin) if origin is not None else cfg['origin']
    if with_codex and shutil.which('codex') is None:
        raise ValueError('CODEX_CLI_NOT_INSTALLED: install it and sign in before --with-codex')
    os.umask(0o077)
    provider = None
    if with_codex:
        from semantic_repair.inference011 import SubscriptionInference
        provider = SubscriptionInference(instance_root(name) / 'inference-spool', model=model)
    try:
        from .staging009 import create_app
        app = create_app(Path(cfg['data']), Path(cfg['layer']), issuer,
            Path(cfg['password']).read_text().strip(), deployment_id='checkout-' + name,
            semantic_provider=provider)
        import uvicorn
        resource.setrlimit(resource.RLIMIT_AS, (1073741824, 1073741824))
        uvicorn.run(app, host='127.0.0.1', port=cfg['port'], ssl_certfile=cfg['cert'],
            ssl_keyfile=cfg['key'], access_log=False, proxy_headers=False, limit_concurrency=32)
    finally:
        if provider is not None:
            provider.close()


async def smoke(name: str) -> dict:
    """Real local TLS/OAuth handshake and read-only MCP calls; no model call."""
    from deploy018_transport import client, oauth
    cfg = configuration(name)
    context = ssl.create_default_context(cafile=cfg['cert'])
    token = await asyncio.to_thread(oauth, cfg['origin'], context, Path(cfg['password']))
    wire = instance_root(name) / 'smoke-wire.jsonl'
    wire.touch(mode=0o600, exist_ok=True)
    async with client(cfg['origin'], context, token['access_token'], wire) as session:
        await session.initialize()
        discovered = await session.list_tools()
        names = {tool.name for tool in discovered.tools}
        required = {'bridge_system_status', 'bridge_validate_records', 'research_autonomy_ingest', 'service_health'}
        if not required <= names or len(names) != 44:
            raise ValueError('UNIFIED_TOOLS_LIST_MISMATCH')
        for tool, args in [('bridge_system_status', {}), ('service_health', {}),
                           ('bridge_validate_records', {'source_id': 'P1-001'})]:
            result = await session.call_tool(tool, args)
            if result.isError:
                raise ValueError('MCP_READ_FAILED:' + tool)
            payload = result.structuredContent
            if payload is None:
                payload = json.loads(next(item.text for item in result.content if item.type == 'text'))
            if tool == 'bridge_system_status' and payload.get('version') != VERSION:
                raise ValueError('MCP_VERSION_MISMATCH')
            if tool == 'service_health' and payload.get('sqlite_integrity') != 'ok':
                raise ValueError('MCP_SQLITE_HEALTH_FAILED')
            if tool == 'bridge_validate_records' and not (
                    payload.get('record_checks') and all(row['valid'] for row in payload['record_checks'])):
                raise ValueError('MCP_SOURCE_SCHEMA_CHECK_FAILED')
    return {'status': 'PASS', 'version': VERSION, 'tool_count': len(names),
        'transport': 'REAL_HTTPS_OAUTH', 'inference_calls': 0, 'production_accessed': False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'serve', 'smoke'])
    parser.add_argument('--instance', default='development')
    parser.add_argument('--port', type=int, default=18766, help='prepare only; use0 for an available port')
    parser.add_argument('--origin', help='serve only; exact public HTTPS OAuth origin')
    parser.add_argument('--with-codex', action='store_true', help='serve only; use existing owner Codex login')
    parser.add_argument('--model', default='gpt-6.1-sol')
    args = parser.parse_args()
    if args.action == 'prepare':
        print(json.dumps(prepare(Path(__file__).resolve().parents[2], args.instance, args.port), indent=2))
    elif args.action == 'serve':
        serve(args.instance, origin=args.origin, with_codex=args.with_codex, model=args.model)
    else:
        print(json.dumps(asyncio.run(smoke(args.instance)), indent=2))


if __name__ == '__main__':
    main()
