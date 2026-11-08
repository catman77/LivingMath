"""Separate fixed warm worker, original5s CPU/6s wall/512MiB per fork."""
import sys
from pathlib import Path
if __package__ is None:sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from lm_suti_assurance.core import canonical,strict_json
from lm_suti_assurance.symbolic import worker as supervisor
from lm_suti_assurance.udav_core.symbolic import run as symbolic_run


def main():
    try:
        from lm_suti_assurance.white_star.runtime import load
        adapter,ops,identity=load()
        from udav import ReversibleUDAV
        from lm_suti_assurance.white_star.isolation import restrict
        # Optional numerical module is preloaded before filesystem/network isolation.
        from lm_suti_assurance.udav_core import numeric
        def dispatch(envelope,clock):
            if envelope['engine']=='symbolic':return symbolic_run(envelope['request'],clock)
            if envelope['engine']=='numeric':return numeric.run(envelope['request'],adapter)
            raise ValueError('INVALID_ENGINE')
        supervisor.run=dispatch
        restriction=restrict();print(canonical({'ready':True,'engine':'udav_core/1','numeric':identity,'isolation':restriction}),flush=True)
    except Exception as e:
        print(canonical({'ready':False,'message':str(e)[:256]}),flush=True);return 2
    for raw in sys.stdin.buffer:
        packet=strict_json(raw.decode())
        result=supervisor.bounded({'action':'explore','request':{'engine':packet['engine'],'request':packet['request']}},ReversibleUDAV)
        print(canonical(result),flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
