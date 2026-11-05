"""Pinned additive v0.1 adapter over the accepted observer012 production entry.

Config is owner-private. The existing loader still validates legacy approvals,
source hashes and database inodes. The new layer has its own manifest approval.
"""
import argparse
import functools
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_private(path):
    path = Path(path)
    st = path.stat()
    if path.is_symlink() or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) & 0o077:
        raise ValueError('OWNER_ONLY_RELEASE_CONFIGURATION_REQUIRED')
    return json.loads(path.read_text())


def serve(path):
    cfg = load_private(path)
    layer = Path(cfg['release_layer']).resolve(strict=True)
    manifest_path = layer/'release_manifest.json'
    if sha(manifest_path) != cfg['release_manifest_sha256']:
        raise ValueError('RELEASE_MANIFEST_MISMATCH')
    manifest = json.loads(manifest_path.read_text())
    for name, expected in manifest.items():
        p = (layer/name).resolve(strict=True)
        if not p.is_relative_to(layer) or sha(p) != expected:
            raise ValueError('RELEASE_FILE_MISMATCH')
    if cfg['release'] not in ('v0.1.0-developer-preview','v0.2.0-developer-preview'):
        raise ValueError('RELEASE_VERSION_MISMATCH')
    expected = {'release':cfg['release'],'release_manifest_sha256':cfg['release_manifest_sha256'],
                'deployment_id':cfg['deployment_id'],'action':'INSTALL_EXACT_OWNER_AUTHORIZED_PREVIEW'}
    if load_private(cfg['owner_authorization']) != expected:
        raise ValueError('EXACT_RELEASE_AUTHORIZATION_REQUIRED')
    legacy_layer = Path(cfg['legacy_layer']).resolve(strict=True)
    sys.path.insert(0, str(layer/'src'))
    sys.path.insert(1, str(legacy_layer))
    from lm_suti_assurance.mcp import register_tools
    active_release = cfg['release']
    provider = None
    if cfg.get('semantic_proposer') is not None:
        settings = cfg['semantic_proposer']
        if set(settings) != {'spool','model'} or settings['model'] != 'gpt-6.1-sol':
            raise ValueError('PINNED_OWNER_SEMANTIC_PROPOSER_REQUIRED')
        spool = Path(settings['spool']).resolve()
        if not spool.is_relative_to(Path.home()/'.local/state/livingmath'):
            raise ValueError('PRIVATE_SEMANTIC_PROPOSER_SPOOL_REQUIRED')
        from lm_suti_assurance.semantic_bridge.owner_pipe import HostedPipe
        provider = HostedPipe(spool)
    import unified_deploy as legacy
    # Its loader still checks the immutable original observer profile.
    legacy_cfg = legacy.load(Path(cfg['legacy_config']))
    legacy_cfg['origin'] = os.environ.get('LIVE_MATH_PUBLIC_URL', cfg['origin']) if legacy_cfg['mode'] == 'production' else cfg['origin']
    legacy_cfg['port'] = cfg['port']
    legacy_cfg['deployment_id'] = cfg['deployment_id']
    legacy_cfg['startup_record'] = cfg['startup_record']
    import unified_system.server as bridge
    original_mount = bridge.mount

    def mount(server, *args, **kwargs):
        original_mount(server, *args, **kwargs)
        register_tools(server, cfg['assurance_state'])
        from lm_suti_assurance.semantic_bridge.mcp import register_tools as register_semantic
        register_semantic(server, cfg['assurance_state'], provider)
        server._mcp_server.version = active_release
        server._mcp_server.instructions += ' For finite assurance use assurance_contract; manual proposals, exact task review and offline export/replay are separate steps.'
        for name in ('bridge_system_status','service_health','research_contract'):
            tool = server._tool_manager.get_tool(name)
            if tool is None:
                continue
            previous = tool.fn
            def decorate(fn):
                @functools.wraps(fn)
                def result(*a, **kw):
                    value = fn(*a, **kw)
                    value['legacy_protocol_version'] = value.get('version')
                    value['version'] = active_release
                    value['deployment_id'] = cfg['deployment_id']
                    value['assurance_release'] = {'release':active_release,'gate':cfg['release_gate'],
                        'release_manifest_sha256':cfg['release_manifest_sha256'],
                        'external_human_replays':cfg['external_human_replays'],
                        'tool_count':len(server._tool_manager.list_tools()),'execution_permission':False}
                    return value
                return result
            tool.fn = decorate(previous)
    bridge.mount = mount
    # Extend exact legacy read allowlist only with the immutable new release layer.
    # All workspace state is beneath the already allowed canonical data directory.
    import unified_isolation
    from release_isolation import restrict as release_restrict
    def restrict(plan, current_layer):
        # Legacy restrict accepts read-only roots through _paths; do not change DB roles.
        return release_restrict(plan, current_layer, release_layer=layer)
    unified_isolation.restrict = restrict
    original_hooks = legacy.install_hooks
    def hooks(base, current):
        original_hooks(base, current)
        previous = base.template_hooks
        def template_hooks(plan):
            value = previous(plan)
            # Legacy create_app overwrites low-level version *after* mount; set
            # version through the same accepted unified module constant.
            legacy.VERSION = active_release
            return value
        base.template_hooks = template_hooks
    legacy.install_hooks = hooks
    try:
        legacy.serve(legacy_cfg)
    finally:
        if provider is not None:provider.close()


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True)
    args=p.parse_args();os.umask(0o077);serve(args.config)
