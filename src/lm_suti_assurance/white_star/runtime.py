"""Fixed worker imports only; never imported into the main server's module namespace."""

import hashlib
import sys
from pathlib import Path
from .contracts import VENDOR, integrity, preflight


def load(prepare=False):
    integrity()
    sys.path.insert(0, str(VENDOR / "integration"))
    import white_star_adapter as adapter
    import fast_source

    if prepare:
        native = fast_source.build_native()
    else:
        # Compute expected identity without calling the lazy compiler.
        import platform

        key = hashlib.sha256(
            (fast_source.HERE / "native/white_star.cpp").read_bytes()
            + repr(
                (fast_source.BUILD_FLAGS, platform.machine(), platform.system())
            ).encode()
        ).hexdigest()[:16]
        native = fast_source.HERE / "native/build" / ("white_star_" + key + ".so")
        if not native.is_file():
            raise RuntimeError("ENGINE_UNAVAILABLE_NATIVE_NOT_PREPARED")
    fast_source.build_native = lambda: native
    fast_source.native_library()
    import formal_models

    return (
        adapter,
        formal_models,
        {
            "native_sha256": hashlib.sha256(native.read_bytes()).hexdigest(),
            "algorithm": "UNCHANGED_SUPPLIED_CODE",
            "files": len(integrity()),
        },
    )
