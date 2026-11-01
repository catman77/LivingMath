"""Publish the additive unified system while retaining the exact approved RC020 core."""
import argparse
import functools
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
from typing import Any

from unified_system import VERSION


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    info=path.stat()
    if path.is_symlink() or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077:
        raise ValueError('OWNER_ONLY_UNIFIED_CONFIGURATION_REQUIRED')
    cfg=json.loads(path.read_text())
    if cfg['version']!=VERSION or cfg['authorization']!='Publish SUTI-Bridge-LivingMath MCP for direct ChatGPT testing':
        raise ValueError('UNIFIED_DEPLOYMENT_AUTHORIZATION_MISMATCH')
    for key in ['base_entry','base_authorization']:
        if sha(Path(cfg[key]))!=cfg[key+'_sha256']:raise ValueError('PINNED_BASE_DEPLOYMENT_DRIFT')
    layer=Path(cfg['layer']).resolve(strict=True)
    manifest=json.loads((layer/'manifest.json').read_text())
    if sha(layer/'manifest.json')!=cfg['layer_manifest_sha256']:raise ValueError('UNIFIED_MANIFEST_DRIFT')
    for name,expected in manifest.items():
        p=(layer/name).resolve(strict=True)
        if not p.is_relative_to(layer) or sha(p)!=expected:raise ValueError('UNIFIED_SOURCE_OR_ASSET_DRIFT:'+name)
    if cfg['mode']=='production':
        if not cfg.get('artifact_owner_approval'):raise ValueError('EXACT_ARTIFACT_OWNER_APPROVAL_REQUIRED')
        approval_path=Path(cfg['artifact_owner_approval'])
        info=approval_path.stat()
        if approval_path.is_symlink() or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077:
            raise ValueError('OWNER_ONLY_ARTIFACT_PROMOTION_APPROVAL_REQUIRED')
        approval=json.loads(approval_path.read_text())
        expected={'version':VERSION,'package_sha256':cfg['artifact_package_sha256'],
            'layer_manifest_sha256':cfg['layer_manifest_sha256'],'schema_sha256':cfg['artifact_schema_sha256'],
            'instance_id':cfg['deployment_id'],'action':'APPROVE_EXACT_ARTIFACT_PROFILE_PROMOTION'}
        if approval!=expected:raise ValueError('EXACT_ARTIFACT_FINGERPRINT_APPROVAL_REQUIRED')
    cfg['_layer']=layer
    return cfg


def serve(cfg: dict) -> None:
    spec=importlib.util.spec_from_file_location('_accepted_rc020_base',cfg['base_entry'])
    if spec is None or spec.loader is None:raise ValueError('BASE_ENTRYPOINT_CANNOT_BE_LOADED')
    base: Any=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
    plan=base.load_authorization(Path(cfg['base_authorization']))
    for role,item in cfg.get('databases',{}).items():
        actual=Path(item['path']).resolve(strict=True)
        if actual.stat().st_ino!=item['inode']:raise ValueError('UNIFIED_DATABASE_IDENTITY_DRIFT:'+role)
        plan['_paths'][role]=actual
    plan['mode']=cfg['mode'];plan['origin']=cfg['origin'];plan['port']=cfg['port']
    plan['deployment_id']=cfg['deployment_id'];plan['startup_record']=cfg['startup_record']
    plan['password_file']=cfg['password_file']
    provider = None
    settings = cfg.get('semantic_inference')
    if settings is not None:
        if set(settings) != {'kind', 'model', 'spool'} or settings['kind'] != 'codex_chatgpt':
            raise ValueError('OWNER_SELECTED_SOURCE_INFERENCE_REQUIRED')
        spool = Path(settings['spool']).resolve()
        if not spool.is_relative_to(Path.home()/'.local/state/livingmath'):
            raise ValueError('PRIVATE_SOURCE_INFERENCE_SPOOL_REQUIRED')
        from semantic_repair.inference011 import SubscriptionInference
        provider = SubscriptionInference(spool, model=settings['model'])
        cfg['_semantic_provider'] = provider
    try:
        install_hooks(base,cfg)
        base.serve(plan)
    finally:
        if provider is not None:provider.close()


def install_hooks(base, cfg: dict) -> None:
    """Same additive unified mount for approved production and isolated rehearsal."""
    cache=cfg['_layer']/'dependency_cache'
    if not cache.is_dir():raise ValueError('PINNED_PUBLIC_TOKENIZER_CACHE_REQUIRED')
    os.environ['TIKTOKEN_CACHE_DIR']=str(cache)
    base_release=base.RELEASE
    base.RELEASE=VERSION
    original_hooks=base.template_hooks

    def template_hooks(current):
        provenance=original_hooks(current)
        # The accepted preview worker uses an explicit environment. Supply the public vocabulary
        # from the immutable layer instead of granting reads of arbitrary temporary directories.
        import native_preview008_server as preview
        previous_init=preview.MeasuredProcess.__init__
        def cached_init(self,*args,**kwargs):
            kwargs['env']={**kwargs.get('env',{}),'TIKTOKEN_CACHE_DIR':str(cache)}
            previous_init(self,*args,**kwargs)
        setattr(preview.MeasuredProcess,'__init__',cached_init)
        import deploy018_authority as authority
        previous=authority.template
        def template(name):
            module=previous(name)
            if name!='http_server':return module
            previous_app=module.create_app
            def create_app(*args,**kwargs):
                original_factory=module.create_server
                captured: list[Any]=[]
                def factory(*a,**kw):
                    server=original_factory(*a,**kw)
                    from davcore.mcp import register_tools as register_dav
                    from research_automation.controller import Controller
                    from research_automation.server import register_tools as register_auto
                    from unified_system.assets import Assets
                    from unified_system.server import mount
                    dav=register_dav(server,Path(cfg['dav_database']),tuple(current['_paths'].values()))
                    controller=Controller(dav,canonical=current['_paths']['canonical'],inbox=Path(cfg['inbox']),
                        semantic_provider=cfg.get('_semantic_provider'))
                    register_auto(server,controller)
                    mount(server,Assets(current_layer/'assets'),dav,controller,cfg['deployment_id'])
                    captured.append(server)
                    return server
                module.create_server=factory
                app=previous_app(*args,**kwargs)
                for server in captured:
                    server._mcp_server.version=VERSION
                    for tool_name in ['research_contract','service_health']:
                        tool=server._tool_manager.get_tool(tool_name);previous_fn=tool.fn
                        def decorate(fn,srv):
                            @functools.wraps(fn)
                            def result(*a,**kw):
                                data=fn(*a,**kw)
                                data['base_protocol_version']=data['version'];data['version']=VERSION
                                data['installed_release']={**data.get('installed_release',{}),'version':VERSION,
                                    'protocol':'suti-bridge-livingmath/mcp/1','tool_count':len(srv._tool_manager.list_tools()),
                                    'base_release':base_release,'layer_manifest_sha256':cfg['layer_manifest_sha256'],
                                    'artifact_promotion':'OWNER_APPROVED_EXACT_FINGERPRINT' if cfg['mode']=='production' else 'NOT_PROMOTED_REHEARSAL'}
                                return data
                            return result
                        tool.fn=decorate(previous_fn,server)
                return app
            module.create_app=create_app
            return module
        authority.template=template
        return {**provenance,'unified_layer_manifest':cfg['layer_manifest_sha256'],'base_release':base_release}
    current_layer=cfg['_layer']
    base.template_hooks=template_hooks
    from unified_isolation import restrict
    base.restrict_service_reads=lambda current:restrict(current,current_layer)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',type=Path,required=True)
    a=parser.parse_args();os.umask(0o077);serve(load(a.config))
