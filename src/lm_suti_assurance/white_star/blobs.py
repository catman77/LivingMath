"""Chunk large numerical artifacts into the existing immutable object store."""

import base64
import json
from ..core import canonical, byte_digest, strict_json
from ..service import require

CHUNK = 48 * 1024
MAX = 32 * 1024 * 1024


def put(workspace, value):
    raw = canonical(value).encode()
    require(len(raw) <= MAX, "RESULT_TOO_LARGE")
    refs = []
    for start in range(0, len(raw), CHUNK):
        refs.append(
            workspace.put(
                {
                    "schema": "levinmas-white-star-chunk/1",
                    "encoding": "base64",
                    "data": base64.b64encode(raw[start : start + CHUNK]).decode(),
                }
            )
        )
    root = {
        "schema": "levinmas-white-star-blob/1",
        "bytes": len(raw),
        "sha256": byte_digest(raw),
        "chunks": refs,
    }
    ref = workspace.put(root)
    return ref, [ref, *refs]


def get(workspace, ref):
    root = workspace.get(ref)
    require(
        root.get("schema") == "levinmas-white-star-blob/1", "INVALID_ARTIFACT_REFERENCE"
    )
    require(
        type(root["bytes"]) is int and 0 <= root["bytes"] <= MAX, "RESULT_TOO_LARGE"
    )
    raw = b"".join(
        base64.b64decode(workspace.get(r)["data"], validate=True)
        for r in root["chunks"]
    )
    require(
        len(raw) == root["bytes"] and byte_digest(raw) == root["sha256"],
        "ARTIFACT_INTEGRITY_FAILURE",
    )
    return strict_json(raw.decode())
