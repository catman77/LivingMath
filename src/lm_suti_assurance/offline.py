"""Thread-scoped audit boundary: no sockets, subprocesses or dynamic code loading."""
import sys
import threading
from contextlib import contextmanager
from .errors import AssuranceError

_STATE = threading.local()


def _audit(event, args):
    if getattr(_STATE, 'active', False) and (event.startswith('socket.') or
            event in {'subprocess.Popen', 'os.system', 'os.posix_spawn', 'ctypes.dlopen'}):
        raise AssuranceError('OFFLINE_EXTERNAL_OPERATION_FORBIDDEN', details={'event': event})


sys.addaudithook(_audit)


@contextmanager
def isolated():
    previous = getattr(_STATE, 'active', False)
    _STATE.active = True
    try:
        yield
    finally:
        _STATE.active = previous
