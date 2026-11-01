"""Raw-only disposable proposer; no source catalog, evaluator, target or oracle access."""
import json
from pathlib import Path
import resource
import socket
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from artifact_genesis.contract import RawPacket  # noqa: E402
from artifact_genesis.proposer import propose  # noqa: E402


def main():
    raw=sys.stdin.buffer.read(64001)
    if len(raw)>64000:raise ValueError('RAW_INPUT_BUDGET')
    packet=RawPacket.model_validate(json.loads(raw))
    resource.setrlimit(resource.RLIMIT_CPU,(5,5));resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,)*2)
    resource.setrlimit(resource.RLIMIT_FSIZE,(0,0));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    def deny(event,args):
        if event in {'open','os.listdir','os.scandir','subprocess.Popen','os.system','ctypes.dlopen','os.fork','os.exec','os.posix_spawn'} or event.startswith('socket.'):
            raise PermissionError('RAW_PROPOSER_IO_DENIED:'+event)
    sys.addaudithook(deny)
    probes={}
    for name,fn in [('file',lambda:open('/etc/hostname','rb')),('socket',socket.socket)]:
        try:fn()
        except PermissionError:probes[name]='DENIED'
        else:raise RuntimeError('UNENFORCED_PROPOSER_IO_GATE')
    out=propose(packet)
    out['isolation']={'probes':probes,'forbidden_modules_loaded':[m for m in sys.modules if m in {
        'artifact_genesis.audit','artifact_genesis.binding','artifact_genesis.postcheck','artifact_translation.generator','davcore.finite'}],
        'stdin_fields':sorted(packet.model_dump())}
    print(json.dumps(out,ensure_ascii=False,allow_nan=False))


if __name__=='__main__':main()
