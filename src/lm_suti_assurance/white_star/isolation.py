"""Read-only allowlist for numerical supervisors and their forked jobs."""

import ctypes
import os
from pathlib import Path
import pwd
import sys


def restrict():
    original = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".codex/auth.json"
    libc = ctypes.CDLL(None, use_errno=True)

    class Ruleset(ctypes.Structure):
        _fields_ = [("handled_access_fs", ctypes.c_uint64)]

    class Beneath(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int)]

    abi = libc.syscall(444, 0, 0, 1)
    if abi < 3:
        raise RuntimeError("ENGINE_UNAVAILABLE_LANDLOCK_ABI3_REQUIRED")
    rules = Ruleset((1 << 15) - 1)
    fd = libc.syscall(444, ctypes.byref(rules), ctypes.sizeof(rules), 0)
    if fd < 0:
        raise RuntimeError("ENGINE_UNAVAILABLE_LANDLOCK_REQUIRED")
    roots = {
        Path(__file__).resolve().parents[1],
        Path(sys.base_prefix) / "lib",
        Path(sys.prefix) / "lib",
        Path("/usr/lib"),
        Path("/lib"),
        Path("/usr/share/zoneinfo"),
        Path("/etc/ld.so.cache"),
        Path("/dev/null"),
        Path("/dev/urandom"),
    }
    try:
        for root in roots:
            if not root.exists():
                continue
            handle = os.open(root, os.O_PATH | os.O_CLOEXEC)
            try:
                rule = Beneath(12 if root.is_dir() else 4, handle)
                if libc.syscall(445, fd, 1, ctypes.byref(rule), 0) < 0:
                    raise RuntimeError("ENGINE_UNAVAILABLE_LANDLOCK_RULE")
            finally:
                os.close(handle)
        if libc.prctl(38, 1, 0, 0, 0) != 0 or libc.syscall(446, fd, 0) < 0:
            raise RuntimeError("ENGINE_UNAVAILABLE_LANDLOCK_RESTRICT")
    finally:
        os.close(fd)
    # Don't read any bytes even if a misconfiguration accidentally allows opening.
    try:
        probe = os.open(original, os.O_RDONLY)
    except (PermissionError, FileNotFoundError):
        denied = True
    else:
        os.close(probe)
        raise RuntimeError("ENGINE_UNAVAILABLE_CREDENTIAL_ISOLATION")
    probe_path = Path("/tmp") / ("white-star-write-probe-" + str(os.getpid()))
    try:
        probe = os.open(probe_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except PermissionError:
        writes_denied = True
    else:
        os.close(probe)
        probe_path.unlink()
        raise RuntimeError("ENGINE_UNAVAILABLE_WRITE_ISOLATION")
    return {
        "filesystem_writes_denied": writes_denied,
        "Landlock_ABI": abi,
        "read_allowlist": "installed immutable code and interpreter libraries only",
        "credentials_denied": denied,
        "network": "audit-denied inside job",
        "physical_execution": False,
    }
