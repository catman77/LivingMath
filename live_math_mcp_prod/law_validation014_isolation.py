"""Landlock read allowlist for the trusted014 engine, without seals or oracle."""
import ctypes
import errno
import os
from pathlib import Path
import sys


def restrict_reads(workspace,forbidden):
    libc=ctypes.CDLL(None,use_errno=True)
    create,add,restrict=444,445,446  # Linux generic syscall numbers (x86_64/aarch64).
    abi=libc.syscall(create,0,0,1)
    if abi<1:raise RuntimeError('MISSING_CAPABILITY_LANDLOCK:'+str(ctypes.get_errno()))
    class Ruleset(ctypes.Structure):_fields_=[('handled_access_fs',ctypes.c_uint64)]
    class PathBeneath(ctypes.Structure):
        _pack_=1
        _fields_=[('allowed_access',ctypes.c_uint64),('parent_fd',ctypes.c_int)]
    read_file,read_dir=4,8
    rules=Ruleset(read_file|read_dir);fd=libc.syscall(create,ctypes.byref(rules),ctypes.sizeof(rules),0)
    if fd<0:raise RuntimeError('LANDLOCK_CREATE:'+str(ctypes.get_errno()))
    source=Path(__file__).resolve().parent
    paths={Path(workspace).resolve(),Path(sys.base_prefix)/'lib',Path(sys.prefix)/'lib',Path('/usr/lib'),Path('/usr/share'),Path('/etc'),Path('/dev/null'),Path('/dev/urandom')}
    for module in tuple(sys.modules.values()):
        name=getattr(module,'__file__',None)
        if name:
            p=Path(name).resolve()
            if p.parent==source:
                if 'oracle' in p.name or 'worlds' in p.name or p.name.endswith('_qa.py'):raise RuntimeError('FORBIDDEN_MODULE_PRELOADED:'+p.name)
                paths.add(p)
    for name in ('research_store.py','frontier.py','evidence_review.py','move_lifecycle.py','mcp_server.py','normalization-schema.json'):
        paths.add(source/name)
    try:
        for path in paths:
            if not path.exists():continue
            descriptor=os.open(path,os.O_PATH|os.O_CLOEXEC)
            try:
                rule=PathBeneath(read_file|(read_dir if path.is_dir() else 0),descriptor)
                if libc.syscall(add,fd,1,ctypes.byref(rule),0)<0:raise RuntimeError('LANDLOCK_ADD:'+str(path)+':'+str(ctypes.get_errno()))
            finally:os.close(descriptor)
        if libc.prctl(38,1,0,0,0)!=0:raise RuntimeError('NO_NEW_PRIVS')
        if libc.syscall(restrict,fd,0)<0:raise RuntimeError('LANDLOCK_RESTRICT:'+str(ctypes.get_errno()))
    finally:os.close(fd)
    denied=[]
    for path in forbidden:
        try:
            with open(path,'rb') as stream:stream.read(1)
        except PermissionError:denied.append(str(path))
        else:raise RuntimeError('ORACLE_ISOLATION_FAILED:'+str(path))
    return {'Landlock_ABI':abi,'forbidden_reads_denied':denied,'scope':'READ_FILE/READ_DIR allowlist; not a sandbox against schema-owning operator'}
