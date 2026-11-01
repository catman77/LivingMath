"""Owner CLI: isolated clean installation or BackupAPI rehearsal, never production migration."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import socket
import sqlite3


def initialize(data: Path, layer: Path, snapshots: Path | None = None) -> dict:
    from deploy018_storage import private_path,migrate
    from research_store import ResearchStore
    from typed_cycle011_store import install as install_typed
    from engine017_store import install as install_engine
    from deploy018_authority import install as install_authority
    from deploy018_transport import tls
    data=private_path(data);layer=layer.resolve(strict=True)
    if data.exists():raise FileExistsError('REHEARSAL_TARGET_MUST_BE_NEW')
    data.mkdir(parents=True,mode=0o700)
    canonical=data/'research.sqlite3';typed=data/'typed.sqlite3'
    if snapshots:
        for role,dest in [('canonical',canonical),('typed',typed),('dav',data/'dav.sqlite3')]:
            source=snapshots/(role+'-before.sqlite3')
            with sqlite3.connect(source.resolve(strict=True).as_uri()+'?mode=ro',uri=True) as old,sqlite3.connect(dest) as new:old.backup(new)
            dest.chmod(0o600)
    else:
        ResearchStore(canonical);ResearchStore(typed)
        install_typed(typed,canonical);install_engine(typed)
        migrate(canonical);migrate(typed);install_authority(typed)
    cert,key,password=tls(data/'tls')
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    config={'data':str(data),'layer':str(layer),'cert':str(cert),'key':str(key),'password':str(password),
        'origin':'https://localhost:'+str(port),'port':port}
    (data.parent/(data.name+'-config.json')).write_text(json.dumps(config,indent=2)+'\n')
    (data.parent/(data.name+'-config.json')).chmod(0o600)
    return config


def make_layer(source: Path, out: Path) -> dict:
    """Only selected public assets/tokenizer bytes; never copy source archives."""
    if out.exists():raise FileExistsError('IMMUTABLE_LAYER_TARGET_MUST_BE_NEW')
    out.mkdir(parents=True)
    for name in ('assets','dependency_cache'):shutil.copytree(source/name,out/name)
    manifest={str(f.relative_to(out)):hashlib.sha256(f.read_bytes()).hexdigest() for f in out.rglob('*') if f.is_file()}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--layer',type=Path,required=True);parser.add_argument('--snapshots',type=Path)
    a=parser.parse_args();print(json.dumps(initialize(a.data,a.layer,a.snapshots)))
