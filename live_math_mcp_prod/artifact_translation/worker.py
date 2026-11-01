"""Disposable generator: imports no checker/oracle and receives no holdout text."""
import json
from pathlib import Path
import resource
import socket
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from artifact_translation.contract import ProposalRequest  # noqa: E402
from artifact_translation.generator import propose  # noqa: E402


def main() -> None:
    raw=sys.stdin.buffer.read(64001)
    if len(raw)>64000:raise ValueError('PROPOSAL_INPUT_BYTE_BOUND')
    req=ProposalRequest.model_validate(json.loads(raw))
    resource.setrlimit(resource.RLIMIT_CPU,(6,6))
    resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,)*2)
    resource.setrlimit(resource.RLIMIT_FSIZE,(0,0))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    def deny(event,args):
        if (event in {'open','os.listdir','os.scandir','subprocess.Popen','os.system','ctypes.dlopen',
                      'os.fork','os.posix_spawn','os.exec'} or event.startswith('socket.')):
            raise PermissionError('GENERATOR_EXTERNAL_IO_DENIED:'+event)
    sys.addaudithook(deny)
    probes={}
    try:
        with open('/etc/hostname','rb'):pass
    except PermissionError:probes['filesystem_probe_denied']=True
    else:raise RuntimeError('GENERATOR_FILE_BOUNDARY_NOT_ENFORCED')
    try:socket.socket()
    except PermissionError:probes['network_probe_denied']=True
    else:raise RuntimeError('GENERATOR_SOCKET_BOUNDARY_NOT_ENFORCED')
    out=propose(req)
    out['worker_isolation']={'filesystem_after_imports':'DENIED','network':'DENIED',
                            'checker_imported':any(n in sys.modules for n in [
                                'artifact_translation.checker','davcore.finite','davcore.smt']),
                            'hidden_answer_supplied':False,**probes}
    sys.stdout.write(json.dumps(out,ensure_ascii=False,allow_nan=False))


if __name__=='__main__':main()
