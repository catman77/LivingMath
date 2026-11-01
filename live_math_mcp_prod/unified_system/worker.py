"""Bounded source schema worker; no source program, network or filesystem reads after load."""
import json
from pathlib import Path
import resource
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from unified_system.assets import Assets  # noqa: E402
from unified_system.validation import check  # noqa: E402


def main():
    raw=sys.stdin.buffer.read(128001)
    if len(raw)>128000:raise ValueError('BRIDGE_INPUT_BYTE_BOUND')
    request=json.loads(raw)
    assets=Assets(Path(sys.argv[1]))
    resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,)*2)
    resource.setrlimit(resource.RLIMIT_CPU,(5,5))
    resource.setrlimit(resource.RLIMIT_FSIZE,(0,0))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    def deny(event,args):
        if event=='open' or event.startswith('socket.') or event in {'os.system','subprocess.Popen'}:
            raise PermissionError('BRIDGE_WORKER_IO_DENIED')
    sys.addaudithook(deny)
    out=check(assets.bridge,request['source_id'],request.get('records'),request.get('projection_fields'))
    print(json.dumps(out,ensure_ascii=False))


if __name__=='__main__':
    try:main()
    except (ValueError,TypeError,KeyError) as exc:
        print(json.dumps({'status':'REJECTED','reason':str(exc),'proof_status':'unverified','execution_permission':{'allowed':False}}))
