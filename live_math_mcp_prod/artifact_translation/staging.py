"""Mount the local extension on the existing authenticated HTTP factory, clones only."""
import argparse
from pathlib import Path
import os


def create_app(root: Path, source_root: Path, password: str):
    import http_server
    import davcore.mcp as dav_tools
    from .mcp import register_tools, private_clone_guard
    from .experiment import verify_freeze, verify_source_spans
    from .contract import SourceGraph
    from davcore.ast import digest
    import json
    verify_freeze(source_root);verify_source_spans(source_root)
    source_bindings={entry['graph']['id']:digest(SourceGraph.model_validate(entry['graph']).model_dump())
                     for entry in json.loads((source_root/'frozen/graphs.json').read_text())}
    private_clone_guard(root,root/'research.sqlite3',root/'dav.sqlite3')
    previous=http_server.create_server
    def factory(store,**settings):
        captured=[];original=dav_tools.register_tools
        def capture(*args,**kwargs):
            service=original(*args,**kwargs);captured.append(service);return service
        dav_tools.register_tools=capture
        try:server=previous(store,**settings)
        finally:dav_tools.register_tools=original
        if len(captured)!=1:raise ValueError('EXISTING_DAV_FACTORY_PROFILE_REQUIRED')
        register_tools(server,captured[0],root,store.path,source_bindings)
        server._mcp_server.name='LivingMath Artifact Translation Private QA'
        server._mcp_server.instructions='Private BackupAPI clones; source translation via existing DAV. Production tools/configuration are unchanged. No automatic-research lifecycle is claimed by this temporary test profile.'
        return server
    http_server.create_server=factory
    try:return http_server.create_app('https://livingmath.example',root,password)
    finally:http_server.create_server=previous


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--port',type=int,required=True)
    a=parser.parse_args();os.umask(0o077)
    os.environ['LIVE_MATH_DAV']='1';os.environ['LIVE_MATH_DAV_DB']=str(a.root/'dav.sqlite3')
    import uvicorn
    uvicorn.run(create_app(a.root,a.source_root,(a.root/'qa-password').read_text().strip()),host='127.0.0.1',port=a.port,
                access_log=False,proxy_headers=False)
