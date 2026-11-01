"""Extend the accepted read boundary only to the immutable unified public code/assets."""
import ctypes
import os
from pathlib import Path
import sys


def restrict(plan: dict, layer: Path) -> dict:
    code=plan['_code']
    paths={plan['_paths']['canonical'].parent,layer,Path(sys.base_prefix)/'lib',Path(sys.prefix)/'lib',
           Path(sys.executable).resolve(),Path(sys.prefix)/'pyvenv.cfg',Path('/usr/lib'),Path('/usr/share'),
           Path('/etc'),Path('/dev/null'),Path('/dev/urandom')}
    # Preserve the original RC020 per-file allowlist. No executor, oracle, key or private environment is added.
    paths.add(code)
    for path in code.rglob('*'):
        if not path.is_file() or '__pycache__' in path.parts:continue
        name=path.name
        if (name in {'admin.py','beta019_seed.py'} or 'oracle' in name or 'worlds' in name
                or '_executor' in name or '_operator' in name or name.endswith('_qa.py') or name.startswith(('test_','qa_'))):continue
        if path.suffix in {'.py','.json','.md','.txt'}:paths.add(path)
    forbidden=[Path(p) for p in plan.get('forbidden_files',[])]
    forbidden += [code/n for n in ['beta019_seed.py','beta019_executor.py','beta019_operator.py','law_validation014_oracle.py']]
    libc=ctypes.CDLL(None,use_errno=True);abi=libc.syscall(444,0,0,1)
    if abi<1:raise RuntimeError('MISSING_CAPABILITY_LANDLOCK')
    class Ruleset(ctypes.Structure):_fields_=[('handled_access_fs',ctypes.c_uint64)]
    class PathBeneath(ctypes.Structure):
        _pack_=1
        _fields_=[('allowed_access',ctypes.c_uint64),('parent_fd',ctypes.c_int)]
    rules=Ruleset(12);fd=libc.syscall(444,ctypes.byref(rules),ctypes.sizeof(rules),0)
    if fd<0:raise RuntimeError('LANDLOCK_CREATE')
    try:
        for path in paths:
            if not path.exists():continue
            opened=os.open(path,os.O_PATH|os.O_CLOEXEC)
            try:
                permission=8 if path==code else 12 if path.is_dir() else 4
                rule=PathBeneath(permission,opened)
                if libc.syscall(445,fd,1,ctypes.byref(rule),0)<0:raise RuntimeError('LANDLOCK_ADD:'+str(path))
            finally:os.close(opened)
        if libc.prctl(38,1,0,0,0)!=0 or libc.syscall(446,fd,0)<0:raise RuntimeError('LANDLOCK_RESTRICT')
    finally:os.close(fd)
    denied=[]
    for path in forbidden:
        if not path.exists():continue
        try:
            with path.open('rb') as stream:stream.read(1)
        except PermissionError:denied.append(str(path))
        else:raise RuntimeError('PRIVATE_SOURCE_ISOLATION_FAILED:'+str(path))
    return {'Landlock_ABI':abi,'forbidden_reads_denied':denied,
            'extension':'Immutable DAV/autonomy/Bridge code and selected public research assets only'}
