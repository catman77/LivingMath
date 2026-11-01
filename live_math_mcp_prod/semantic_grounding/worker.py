"""Isolated raw proposal or disjoint source critique; the modules are never co-loaded."""
import json
from pathlib import Path
import resource
import socket
import sys
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from semantic_grounding.contract import ProposalRequest, CritiqueRequest  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {'propose', 'critique'}:
        raise ValueError('INSTALLED_WORKER_MODE_REQUIRED')
    mode = sys.argv[1]
    raw = sys.stdin.buffer.read(64001)
    if len(raw) > 64000:
        raise ValueError('RAW_INPUT_BUDGET')
    invoke: Callable[[], dict[str, Any]]
    if mode == 'propose':
        from semantic_grounding.proposer import propose
        request = ProposalRequest.model_validate_json(raw)
        invoke = lambda: {'hypotheses': propose(request.packet, request.family, request.project)}
    else:
        from semantic_grounding.critic import critique
        other = CritiqueRequest.model_validate_json(raw)
        invoke = lambda: {'critique': critique(other.train, other.challenge, other.family)}
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    def deny(event, args):
        if event in {'open', 'os.listdir', 'os.scandir', 'subprocess.Popen', 'os.system',
                     'ctypes.dlopen', 'os.fork', 'os.exec', 'os.posix_spawn'} or event.startswith('socket.'):
            raise PermissionError('GROUNDING_WORKER_IO_DENIED:' + event)

    sys.addaudithook(deny)
    probes = {}
    operations: list[tuple[str, Callable[[], Any]]] = [('file', lambda: open('/etc/hostname', 'rb')), ('socket', socket.socket)]
    for name, fn in operations:
        try:
            fn()
        except PermissionError:
            probes[name] = 'DENIED'
        else:
            raise RuntimeError('UNENFORCED_PROCESS_BOUNDARY')
    result = invoke()
    forbidden = {'davcore.finite', 'semantic_grounding.formal', 'artifact_translation.generator',
                 'artifact_genesis.audit', 'artifact_genesis.proposer'}
    forbidden.add('semantic_grounding.critic' if mode == 'propose' else 'semantic_grounding.proposer')
    result['isolation'] = {'mode': mode, 'probes': probes,
                           'forbidden_modules_loaded': sorted(forbidden.intersection(sys.modules))}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
