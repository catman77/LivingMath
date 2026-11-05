"""Stateful batch API for the equivalent native WhiteStar/CAD/UDAV kernel.

Only stdlib ctypes, a C++17 compiler, NumPy and pandas are required. The native
kernel computes every observation anew; it neither replays nor caches streams.
Each source owns its state. One instance must not be used concurrently.
"""
from __future__ import annotations

import ctypes as C
from dataclasses import dataclass
import hashlib
import math
import numbers
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

import numpy as np
import pandas as pd

from source import CHARTS, Observation

HERE = Path(__file__).resolve().parent
LABELS = np.array([f"WS:E{d}:A{a}" for d in range(5) for a in range(8)] + ["WS:unresolved"], dtype=object)
I64P = C.POINTER(C.c_int64)
_LIB = None
BUILD_FLAGS = ("-O3", "-std=c++17", "-shared", "-fPIC", "-ffp-contract=off")


def build_native() -> Path:
    source = HERE / "native" / "white_star.cpp"
    key = hashlib.sha256(source.read_bytes() + repr((BUILD_FLAGS, platform.machine(), platform.system())).encode()).hexdigest()[:16]
    directory = HERE / "native" / "build"
    directory.mkdir(exist_ok=True)
    target = directory / f"white_star_{key}.so"
    if target.is_file():
        return target
    if platform.system() != "Linux":
        raise RuntimeError("native build is currently supported on Linux; use the reference source elsewhere")
    compiler = shutil.which("c++") or shutil.which("g++")
    if not compiler:
        raise RuntimeError("a C++17 compiler is required; the unchanged source.py remains usable without one")
    fd, temporary = tempfile.mkstemp(prefix="white_star_", suffix=".so", dir=directory)
    os.close(fd)
    try:
        process = subprocess.run([compiler, *BUILD_FLAGS, str(source), "-o", temporary],
                                 capture_output=True, text=True, timeout=60)
        if process.returncode:
            raise RuntimeError("native compilation failed:\n" + process.stderr)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return target


def native_library():
    global _LIB
    if _LIB is None:
        lib = C.CDLL(str(build_native()))
        lib.ws_error.restype = C.c_char_p
        lib.ws_create.argtypes = [C.c_int64, C.c_int, C.c_int, I64P, C.c_int]
        lib.ws_create.restype = C.c_void_p
        lib.ws_destroy.argtypes = [C.c_void_p]
        lib.ws_destroy.restype = None
        lib.ws_run.argtypes = [C.c_void_p, C.c_uint64, C.POINTER(C.c_uint8), C.POINTER(C.c_int32), I64P]
        lib.ws_run.restype = C.c_int
        lib.ws_set_charts.argtypes = [C.c_void_p, I64P, C.c_int]
        lib.ws_set_charts.restype = C.c_int
        lib.ws_snapshot.argtypes = [C.c_void_p, C.POINTER(C.c_uint64)]
        lib.ws_snapshot.restype = None
        _LIB = lib
    return _LIB


def validate_charts(charts):
    result = []
    for matrix in charts:
        if len(matrix) != 4 or any(isinstance(v, bool) or not isinstance(v, numbers.Integral) for v in matrix):
            raise ValueError("each CAD matrix must have four integer coefficients")
        m = tuple(int(v) for v in matrix)
        if any(abs(v) >= 1 << 61 for v in m):
            raise ValueError("CAD coefficients must have absolute value below 2^61")
        if m[0] * m[3] == m[1] * m[2]:
            raise ValueError("CAD matrices must be nonsingular")
        if m in result:
            raise ValueError("duplicate CAD matrix")
        result.append(m)
    if not 1 <= len(result) <= 4096:
        raise ValueError("provide 1..4096 CAD matrices")
    return tuple(result)


def decode_signature(code: int) -> tuple[int, ...]:
    code, phase = divmod(code, 8)
    code, sy = divmod(code, 3)
    code, sx = divmod(code, 3)
    code, gcd = divmod(code, 4)
    depth, parity = divmod(code, 3)
    return depth, parity, gcd, sx - 1, sy - 1, phase


@dataclass
class ObservationBatch:
    codes: np.ndarray
    views: np.ndarray
    audit: np.ndarray | None
    charts: tuple
    start_step: int

    def labels(self):
        return LABELS[self.codes]

    def observations(self) -> list[Observation]:
        if self.audit is None:
            raise ValueError("request read(..., audit=True) to retain full observations")
        records = []
        for r in self.audit.tolist():
            step, a, b, view, x, y, sig = r[:7]
            candidates = [r[i:i+5] for i in range(7, len(r), 5)]
            xx, yy, quotients = abs(x), abs(y), []
            while yy:
                quotient, remainder = divmod(xx, yy)
                quotients.append(quotient)
                xx, yy = yy, remainder
            signature = decode_signature(sig)
            records.append(Observation(
                step=step, numerator=(0, 0), denominator=(0, 0), witness=(a, b),
                finite_fibre_layer=a + b, candidate_views=tuple(c[0] for c in candidates),
                candidate_scores=tuple((c[1] / 13, 1 / (1 + c[2]),
                                        1 / (1 + c[3]), 1 / (1 + c[4])) for c in candidates),
                view=view, matrix=self.charts[view], coordinates=(x, y),
                direction_defined=bool(a or b), euclid_quotients=tuple(quotients),
                gcd=xx, signature=signature,
                state=str(LABELS[min(signature[0], 4) * 8 + signature[-1]]) if a or b else str(LABELS[40]),
            ))
        return records


class FastWhiteStarSource:
    """Native live source. read() advances; set_charts() steers without reset.

    Custom nonsingular integer matrices may be nonorthogonal and have det != ±1.
    The default atlas, k=3 and selection decisions reproduce source.py.
    """

    def __init__(self, seed=42, k=3, mode="active", charts=CHARTS):
        if isinstance(seed, bool) or not isinstance(seed, int) or not -(1 << 63) <= seed < 1 << 63:
            raise ValueError("seed must be a signed 64-bit integer")
        self.charts = validate_charts(charts)
        if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= len(self.charts):
            raise ValueError("require 1 <= k <= number of CAD matrices")
        if mode not in ("active", "fixed"):
            raise ValueError("mode must be active or fixed")
        self.seed, self.k, self.mode = seed, k, mode
        self._lib = native_library()
        array = np.array(self.charts, dtype=np.int64)
        self._handle = self._lib.ws_create(seed, k, int(mode == "fixed"), array.ctypes.data_as(I64P), len(array))
        if not self._handle:
            raise RuntimeError(self._lib.ws_error().decode())

    def _require_open(self):
        if not getattr(self, "_handle", None):
            raise RuntimeError("source is closed")

    def read(self, count: int, *, audit=False, max_output_bytes=256 * 1024 * 1024) -> ObservationBatch:
        self._require_open()
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("count must be a nonnegative integer")
        columns = 7 + 5 * (1 if self.mode == "fixed" else self.k)
        needed = count * (5 + (columns * 8 if audit else 0))
        if needed > max_output_bytes:
            raise ValueError("batch output exceeds max_output_bytes; request smaller batches")
        codes = np.empty(count, dtype=np.uint8)
        views = np.empty(count, dtype=np.int32)
        data = np.empty((count, columns), dtype=np.int64) if audit else None
        start = self.snapshot()["steps"]
        result = self._lib.ws_run(self._handle, count, codes.ctypes.data_as(C.POINTER(C.c_uint8)),
                                  views.ctypes.data_as(C.POINTER(C.c_int32)),
                                  data.ctypes.data_as(I64P) if audit else None)
        if result:
            raise OverflowError(self._lib.ws_error().decode())
        return ObservationBatch(codes, views, data, self.charts, start)

    def set_charts(self, charts) -> None:
        self._require_open()
        validated = validate_charts(charts)
        if len(validated) < self.k:
            raise ValueError("new atlas must contain at least k matrices")
        array = np.array(validated, dtype=np.int64)
        if self._lib.ws_set_charts(self._handle, array.ctypes.data_as(I64P), len(array)):
            raise ValueError(self._lib.ws_error().decode())
        self.charts = validated

    def snapshot(self) -> dict:
        self._require_open()
        raw = np.empty(7, dtype=np.uint64)
        self._lib.ws_snapshot(self._handle, raw.ctypes.data_as(C.POINTER(C.c_uint64)))
        steps, projections, used, charts, vertices, edges, storage = map(int, raw)
        return dict(steps=steps, projections=projections, charts_used=used,
                    available_charts=charts, full_signatures=vertices,
                    observation_vertices=vertices, observation_edges=edges,
                    beta0=int(steps > 0), beta1=edges-vertices+int(steps > 0),
                    graph_storage_bytes=storage)

    def close(self):
        if getattr(self, "_handle", None):
            self._lib.ws_destroy(self._handle)
            self._handle = None

    def __enter__(self):
        self._require_open()
        return self

    def __exit__(self, *_):
        self.close()

    def __del__(self):
        self.close()


class FastWhiteStarEncoder:
    """Original encode(frame) boundary, with lazy expansion of the audit trace."""

    def __init__(self, seed=42, k=3, mode="active", charts=CHARTS, retain_trace=True):
        self.seed, self.k, self.mode = seed, k, mode
        self.charts, self.retain_trace = validate_charts(charts), retain_trace
        self.batch, self._trace, self.diagnostics = None, None, {}

    def encode(self, frame):
        with FastWhiteStarSource(self.seed, self.k, self.mode, self.charts) as source:
            self.batch = source.read(len(frame), audit=self.retain_trace)
            self.diagnostics = source.snapshot()
        self._trace = None
        return pd.Series(self.batch.labels(), index=frame.index, dtype=object)

    @property
    def trace(self):
        if self._trace is None:
            self._trace = self.batch.observations() if self.batch is not None else []
        return self._trace


if __name__ == "__main__":
    print(build_native())
