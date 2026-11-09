"""Fixed isolated worker with unchanged native supervisor and original quotas."""
import sys
from pathlib import Path
if __package__ is None:sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from lm_suti_assurance.core import canonical,strict_json
from lm_suti_assurance.symbolic import worker as supervisor
from lm_suti_assurance.semantic_bridge.contextual.engine import dispatch


def main():
    try:
        from lm_suti_assurance.white_star.runtime import load
        _,_,identity=load()
        from udav import ReversibleUDAV
        from lm_suti_assurance.white_star.isolation import restrict
        supervisor.run=lambda packet,clock:dispatch(packet)
        restriction=restrict();print(canonical({'ready':True,'engine':'semantic-bridge-patch001/1','numeric':identity,'isolation':restriction}),flush=True)
    except Exception as e:
        print(canonical({'ready':False,'code':'UNAVAILABLE','message':str(e)[:256]}),flush=True);return 2
    for raw in sys.stdin.buffer:
        value=supervisor.bounded(strict_json(raw.decode()),ReversibleUDAV);print(canonical(value),flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
