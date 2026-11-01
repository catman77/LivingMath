"""One bounded disposable computation. Only trusted installed adapter constructors run."""
import json
from pathlib import Path
import resource
import sys

# Executed with -I: resolve only the operator-installed package, never cwd/PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from davcore.adapters import Adapter, AdapterSpec  # noqa: E402
from davcore.ast import Formula  # noqa: E402
from davcore.finite import check, audit, candidates, library, Meter, Limit  # noqa: E402
from davcore.models import Budget  # noqa: E402
from davcore.smt import check_smt  # noqa: E402
from research_automation.checker import check_refinement, check_law_result  # noqa: E402


def restrict():
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (12, 12))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    def hook(event, args):
        if (event in {'open', 'os.listdir', 'os.scandir', 'os.system', 'subprocess.Popen', 'ctypes.dlopen'}
                or event.startswith('socket.') or event in {'os.fork', 'os.posix_spawn', 'os.exec'}):
            raise PermissionError('DAV_WORKER_IO_DENIED:' + event)
    sys.addaudithook(hook)


def main():
    raw = sys.stdin.buffer.read(256001)
    if len(raw) > 256000:
        raise ValueError('INPUT_BYTE_BOUND')
    req = json.loads(raw)
    a = Adapter(AdapterSpec.model_validate(req['spec']))
    if a.metadata != req['metadata']:
        raise ValueError('STALE_ADAPTER_BINDING')
    b = Budget.model_validate(req['budget'])
    f = Formula.model_validate(req['formula']) if 'formula' in req else None
    base = Adapter(AdapterSpec.model_validate(req['base_spec'])) if req['action'] == 'check_refinement' else None
    # Optional native library is loaded before the I/O gate, from installed code only.
    if req.get('backend') == 'smt':
        try:
            import z3  # noqa: F401
        except ImportError:
            pass
    restrict()
    action = req['action']
    if action in {'check', 'find_counterexample'}:
        out = check_smt(a, f, b) if req.get('backend') == 'smt' else check(a, f, req.get('states'), b)
    elif action == 'audit':
        out = audit(a, b)
    elif action == 'check_refinement':
        out = check_refinement(base, a, b)
    elif action == 'check_law_independent':
        out = check_law_result(a, f, req['claimed'], b)
    elif action == 'generate':
        out = {'status': 'generated', **candidates(a, b, req.get('offset', 0))}
    elif action == 'reduce':
        out = library(a, req.get('states'), b)
    elif action == 'observe':
        xs = req['states']
        if not xs or len(xs) > b.max_states or len(xs) != len(set(xs)) or any(not a.valid_state(x) for x in xs):
            raise ValueError('INVALID_OBSERVATION_STATES')
        m = Meter(b)
        observations = []
        try:
            for x in xs:
                observations.append({'state': x, 'raw_state': x, 'observed': a.observe(x), 'steps': [
                    {'operation': op, 'input': x, 'full_output': (value := m.apply(a, op, x)),
                     'observed_output': a.observe(value)} for op in a.ops]})
            out = {'status': 'consistent_with_observations', 'observations': observations, 'metrics': m.metrics(),
                   'reason': 'OBSERVATIONS_DO_NOT_ASSERT_ANY_UNIVERSAL_LAW'}
        except Limit as exc:
            out = {'status': 'timeout', 'reason': str(exc), 'observations': observations, 'metrics': m.metrics()}
    else:
        raise ValueError('UNSUPPORTED_WORKER_ACTION')
    out.update(adapter_binding=a.metadata, proof_status='unverified', execution_permission={'allowed': False})
    encoded = json.dumps(out, allow_nan=False, separators=(',', ':')).encode()
    if len(encoded) > b.max_output_bytes:
        encoded = b'{"status":"timeout","reason":"OUTPUT_BYTE_BOUND","proof_status":"unverified","execution_permission":{"allowed":false}}'
    sys.stdout.buffer.write(encoded)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, TypeError, PermissionError) as exc:
        print(json.dumps({'status': 'invalid_adapter', 'reason': str(exc), 'proof_status': 'unverified',
                          'execution_permission': {'allowed': False}}))
