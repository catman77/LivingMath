"""Real unified44/TLS/OAuth rehearsal using the production mount on private paths.

Owner CLI only. All source comes from this installed code and reviewed assets;
MCP callers cannot select paths/modules. No production config is read or changed.
"""
import argparse
import hashlib
import os
from pathlib import Path

from deploy018_storage import private_path
from unified_deploy import install_hooks


def create_app(data: Path, layer: Path, origin: str, password: str, deployment_id='artifact009-rehearsal',fault_once: Path | None=None,
               semantic_provider=None):
    import production020 as base
    import beta019_http
    code=Path(__file__).resolve().parent.parent
    canonical=private_path(data/'research.sqlite3');typed=private_path(data/'typed.sqlite3')
    private_path(data/'dav.sqlite3');private_path(data/'oauth.sqlite3')
    for key in ['LIVE_MATH_DAV','LIVE_MATH_AUTORESEARCH','LIVE_MATH_DAV_DB']:
        os.environ.pop(key,None)
    os.environ['LIVE_MATH_NATIVE_PREVIEW']='1';os.environ['LIVE_MATH_TYPED_CYCLE_DB']=str(typed)
    (data/'inbox').mkdir(exist_ok=True)
    cfg={'_layer':layer,'dav_database':str(data/'dav.sqlite3'),'inbox':str(data/'inbox'),
        'deployment_id':deployment_id,'mode':'rehearsal',
        'layer_manifest_sha256':hashlib.sha256((layer/'manifest.json').read_bytes()).hexdigest(),
        '_semantic_provider': semantic_provider}
    plan={'_code':code,'_paths':{'canonical':canonical,'typed':typed,'oauth':data/'oauth.sqlite3'},
        'mode':'rehearsal','deployment_id':deployment_id,'adapter_sha256':hashlib.sha256(Path(base.__file__).read_bytes()).hexdigest()}
    install_hooks(base,cfg);base.template_hooks(plan)
    app=beta019_http.create_app(origin,data,typed,password,enabled=True,bounds={'rate':1000,'window':1})
    if fault_once is not None:
        if not fault_once.resolve().is_relative_to(data.resolve()):raise ValueError('PRIVATE_REHEARSAL_FAULT_PATH_REQUIRED')
        from davcore.storage import Store
        append=Store.append
        def fail_once(self,project,kind,*args,**kwargs):
            if kind=='artifact_result' and fault_once.exists():
                fault_once.rename(fault_once.with_suffix('.fired'))
                os._exit(79)
            return append(self,project,kind,*args,**kwargs)
        Store.append=fail_once
    from unified_isolation import restrict
    restrict(plan,layer)
    return app


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('data','layer','cert','key','password'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--origin',required=True);parser.add_argument('--port',type=int,required=True)
    parser.add_argument('--fault-once',type=Path)
    args=parser.parse_args();os.umask(0o077)
    app=create_app(args.data.resolve(),args.layer.resolve(),args.origin,args.password.read_text().strip(),fault_once=args.fault_once)
    import uvicorn
    import resource
    resource.setrlimit(resource.RLIMIT_AS,(1073741824,1073741824))
    uvicorn.run(app,host='127.0.0.1',port=args.port,ssl_certfile=str(args.cert),ssl_keyfile=str(args.key),
        access_log=False,proxy_headers=False,limit_concurrency=32)
