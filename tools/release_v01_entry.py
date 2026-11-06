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
    if cfg['release'] not in ('v0.1.0-developer-preview','v0.2.0-developer-preview','v0.3.0-developer-preview','v0.4.0-developer-preview','v0.4.1-developer-preview','v0.4.2-developer-preview','v0.4.3-developer-preview','v0.4.4-developer-preview','v0.4.5-developer-preview','v0.4.6-developer-preview'):
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
    white_pool = None
    if cfg.get('white_star') == {'enabled':True}:
        from lm_suti_assurance.white_star.pool import Pool
        white_pool = Pool()
    from lm_suti_assurance.symbolic.executor import Executor as SymbolicExecutor, SharedBudget
    shared_symbolic_budget = SharedBudget()
    symbolic_pool = SymbolicExecutor(shared_budget=shared_symbolic_budget)
    replay_profiles = {}
    # Profiles are owner-configured installed immutable layers, never client paths.
    from lm_suti_assurance.core import digest
    for expected_binding, settings in cfg.get('symbolic_replay_profiles', {}).items():
        old_layer = Path(settings['release_layer']).resolve(strict=True)
        if not old_layer.is_relative_to(Path.home()/'.local/state/livingmath'):
            raise ValueError('INSTALLED_HISTORICAL_PROFILE_REQUIRED')
        old_manifest = old_layer/'release_manifest.json'
        if sha(old_manifest) != settings['release_manifest_sha256']:
            raise ValueError('HISTORICAL_PROFILE_MANIFEST_MISMATCH')
        for name, checksum in json.loads(old_manifest.read_text()).items():
            target = (old_layer/name).resolve(strict=True)
            if not target.is_relative_to(old_layer) or sha(target) != checksum:
                raise ValueError('HISTORICAL_PROFILE_FILE_MISMATCH')
        historical_root = old_layer/'src/lm_suti_assurance/symbolic'
        if digest({n:sha(historical_root/n) for n in ('state.py','observers.py','search.py','grammar.py','kernel.py','contracts.py')}) != expected_binding:
            raise ValueError('HISTORICAL_PROFILE_BINDING_MISMATCH')
        profile = SymbolicExecutor(historical_root/'worker.py', shared_budget=shared_symbolic_budget)
        if not profile.status()['ready']:
            profile.close()
            raise ValueError('HISTORICAL_PROFILE_UNAVAILABLE')
        replay_profiles[expected_binding] = profile
    extension_replay_profiles = {}
    for expected_binding, settings in cfg.get('extension_replay_profiles', {}).items():
        old_layer = Path(settings['release_layer']).resolve(strict=True)
        if not old_layer.is_relative_to(Path.home()/'.local/state/livingmath'):
            raise ValueError('INSTALLED_HISTORICAL_EXTENSION_REQUIRED')
        old_manifest = old_layer/'release_manifest.json'
        if sha(old_manifest) != settings['release_manifest_sha256']:
            raise ValueError('HISTORICAL_EXTENSION_MANIFEST_MISMATCH')
        for name, checksum in json.loads(old_manifest.read_text()).items():
            target = (old_layer/name).resolve(strict=True)
            if not target.is_relative_to(old_layer) or sha(target) != checksum:
                raise ValueError('HISTORICAL_EXTENSION_FILE_MISMATCH')
        package = old_layer/'src/lm_suti_assurance'
        symbolic_binding = digest({n:sha(package/'symbolic'/n) for n in ('state.py','observers.py','search.py','grammar.py','kernel.py','contracts.py')})
        modules = {str(p.relative_to(package)):sha(p) for name in ('symbolic_complex','observer_synthesis') for p in sorted((package/name).glob('*.py'))}
        if digest({'symbolic_binding':symbolic_binding,'modules':modules}) != expected_binding:
            raise ValueError('HISTORICAL_EXTENSION_BINDING_MISMATCH')
        profile = SymbolicExecutor(package/'symbolic/worker.py', shared_budget=shared_symbolic_budget)
        if not profile.status()['ready']:
            profile.close()
            raise ValueError('HISTORICAL_EXTENSION_UNAVAILABLE')
        extension_replay_profiles[expected_binding] = profile
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
        from lm_suti_assurance.white_star.mcp import register_tools as register_white
        register_white(server, cfg['assurance_state'], white_pool, recover=True)
        from lm_suti_assurance.symbolic.mcp import register_tools as register_symbolic
        register_symbolic(server, cfg['assurance_state'], symbolic_pool, recover=True, replay_profiles=replay_profiles)
        from lm_suti_assurance.symbolic_complex.mcp import register_tools as register_extensions
        register_extensions(server, cfg['assurance_state'], symbolic_pool, recover=True, replay_profiles=extension_replay_profiles)
        server._mcp_server.version = active_release
        server._mcp_server.instructions += ' For finite assurance use assurance_contract; manual proposals, exact task review and offline export/replay are separate steps.'
        for name in ('bridge_system_status','service_health','research_contract'):
            tool = server._tool_manager.get_tool(name)
            if tool is None:
                continue
            previous = tool.fn
            def decorate(fn, tool_name):
                @functools.wraps(fn)
                def result(*a, **kw):
                    value = fn(*a, **kw)
                    if tool_name == 'bridge_system_status':
                        from lm_suti_assurance.symbolic.mcp import capabilities
                        value['symbolic_v1'] = capabilities(symbolic_pool, replay_profiles)
                        from lm_suti_assurance.symbolic_complex.mcp import capabilities as extension_capabilities
                        value.update(extension_capabilities(symbolic_pool, extension_replay_profiles))
                    value['legacy_protocol_version'] = value.get('version')
                    value['version'] = active_release
                    value['deployment_id'] = cfg['deployment_id']
                    value['assurance_release'] = {'release':active_release,'gate':cfg['release_gate'],
                        'release_manifest_sha256':cfg['release_manifest_sha256'],
                        'external_human_replays':cfg['external_human_replays'],
                        'tool_count':len(server._tool_manager.list_tools()),'execution_permission':False}
                    return value
                return result
            tool.fn = decorate(previous, name)
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
        if white_pool is not None:white_pool.close()
        symbolic_pool.close()
        for profile in replay_profiles.values(): profile.close()
        for profile in extension_replay_profiles.values(): profile.close()


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True)
    args=p.parse_args();os.umask(0o077);serve(args.config)
