"""Strict transport and exact-byte preflight before any numerical search."""

import copy
import hashlib
import json
from pathlib import Path
from jsonschema import Draft202012Validator, validators
from ..core import canonical, digest
from ..errors import AssuranceError

ROOT = Path(__file__).parent
VENDOR = ROOT / "vendor"
LIMITS = {
    "source_bytes": 48000,
    "request_bytes": 262144,
    "concepts": [3, 64],
    "unique_charts": 4096,
    "steps": [1, 4096],
    "candidates_per_step": [1, 16],
    "frame_size": "1..steps",
    "decode_first_frames": [1, 64],
    "worker_cpu_s": 5,
    "worker_wall_s": 6,
    "worker_memory_bytes": 512 * 1024 * 1024,
    "concurrent_jobs": 2,
    "queue": 16,
    "result_bytes": 32 * 1024 * 1024,
    "MCP_response_bytes": 262144,
    "page_default": 64,
    "page_max": 128,
    "matrix_dimensions": [1, 8],
    "rational_bits": 256,
    "cyclic_order_dimensions": [2, 2],
}
StrictValidator = validators.extend(
    Draft202012Validator,
    type_checker=Draft202012Validator.TYPE_CHECKER.redefine(
        "integer", lambda checker, x: type(x) is int
    ),
)
TOOLS = {
    t["name"]: t
    for t in json.loads((VENDOR / "contracts/proposed_tools.json").read_text())["tools"]
}
# Unknown families must reach the explicit UNSUPPORTED_MODEL domain result.
TOOLS["white_star_validate_model"]["inputSchema"]["properties"]["proposal"][
    "properties"
]["family"] = {"type": "string", "minLength": 1, "maxLength": 128}
PROJECT = {"type": "string", "pattern": "^[a-z][a-z0-9_-]{0,63}$"}
KEY = {"type": "string", "pattern": "^[A-Za-z0-9_.:-]{1,128}$"}
REF = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
for t in TOOLS.values():
    props = t["inputSchema"].get("properties", {})
    if "project" in props:
        props["project"] = PROJECT
    if "request_key" in props:
        props["request_key"] = KEY
    if "run_id" in props:
        props["run_id"] = REF
TOOLS["white_star_inspect"]["inputSchema"]["properties"]["view"]["enum"] += [
    "readings",
    "checks",
    "artifact",
]
TOOLS["white_star_inspect"]["inputSchema"]["properties"]["artifact_ref"] = REF
for name, props, required, readonly in [
    (
        "semantic_run_frozen",
        {
            "project": PROJECT,
            "request_key": KEY,
            "common_snapshot_ref": REF,
            "decoder_slots": {"type": "integer", "minimum": 1, "maximum": 64},
        },
        ["project", "request_key", "common_snapshot_ref"],
        False,
    ),
    (
        "white_star_replay",
        {"project": PROJECT, "bundle_ref": REF},
        ["project", "bundle_ref"],
        True,
    ),
]:
    TOOLS[name] = {
        "name": name,
        "inputSchema": {
            "type": "object",
            "properties": props,
            "required": required,
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": readonly,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    }
TOOLS["white_star_record_interpretation"]["inputSchema"]["properties"]["provenance"] = {
    "type": "object",
    "properties": {
        "kind": {"enum": ["MANUAL", "FIXTURE", "CLIENT_LLM"]},
        "model_requested": {"type": ["string", "null"], "maxLength": 256},
        "instructions_sha256": {
            "type": ["string", "null"],
            "pattern": "^[0-9a-f]{64}$",
        },
        "receipt_sha256": {"type": ["string", "null"], "pattern": "^[0-9a-f]{64}$"},
        "decoder_protocol_id": {"type": "string", "minLength": 1, "maxLength": 256},
    },
    "required": [
        "kind",
        "model_requested",
        "instructions_sha256",
        "receipt_sha256",
        "decoder_protocol_id",
    ],
    "additionalProperties": False,
}

TOOLS["white_star_record_interpretation"]["inputSchema"]["properties"]["provenance"][
    "properties"
].update(
    {
        "model_calls": {"type": "integer", "minimum": 0, "maximum": 1},
        "usage": {
            "type": ["object", "null"],
            "properties": {
                k: {"type": "integer", "minimum": 0}
                for k in [
                    "input_tokens",
                    "output_tokens",
                    "cached_input_tokens",
                    "reasoning_output_tokens",
                    "cache_write_input_tokens",
                ]
            },
            "additionalProperties": False,
        },
        "LLM_latency_s": {"type": ["number", "null"], "minimum": 0},
        "cost_USD": {"type": ["number", "null"], "minimum": 0},
    }
)

RESPONSE = {
    "type": "object",
    "properties": {
        "schema": {"const": "levinmas-white-star-response/1"},
        "ok": {"type": "boolean"},
        "status": {"type": "string"},
        "execution_permission": {"const": False},
        "data": {"type": "object"},
        "error": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "message": {"type": "string"},
                "field_path": {"type": "string"},
                "run_id": {"type": ["string", "null"]},
            },
            "required": ["code", "message", "field_path", "run_id"],
            "additionalProperties": False,
        },
    },
    "required": ["schema", "ok", "status", "execution_permission"],
    "additionalProperties": False,
    "oneOf": [
        {"required": ["data"], "properties": {"ok": {"const": True}}},
        {"required": ["error"], "properties": {"ok": {"const": False}}},
    ],
}


def fail(code, field="", message=None):
    raise AssuranceError(code, field, {"message": message or code})


def check_schema(value, schema):
    from ..validation import inspect

    try:
        inspect(value)
    except AssuranceError as exc:
        fail("INVALID_INPUT", exc.field or "", exc.code)
    try:
        canonical(value)
    except (ValueError, TypeError, OverflowError):
        fail("INVALID_INPUT", "", "Nonfinite or non-JSON value")
    errors = sorted(
        StrictValidator(schema).iter_errors(value), key=lambda e: str(e.path)
    )
    if errors:
        e = errors[0]
        fail("INVALID_INPUT", "/" + "/".join(map(str, e.path)), e.message[:500])


def source_evidence(source, evidence, path):
    raw = source["text"].encode("utf-8")
    lo, hi = evidence["byte_start"], evidence["byte_end"]
    if type(lo) is not int or type(hi) is not int or not 0 <= lo < hi <= len(raw):
        fail("EVIDENCE_MISMATCH", path, "Invalid UTF-8 byte span")
    if (
        raw[lo:hi] != evidence["quote"].encode()
        or raw[:lo].count(b"\n") + 1 != evidence["line"]
    ):
        fail("EVIDENCE_MISMATCH", path, "Exact quote bytes or one-based line mismatch")


def preflight(request: dict) -> dict:
    schema = json.loads(
        (VENDOR / "contracts/white_star_request.schema.json").read_text()
    )
    check_schema(request, schema)
    if len(canonical(request).encode()) > LIMITS["request_bytes"]:
        fail("INPUT_TOO_LARGE")
    data = request["encoding"]
    source = data["source"]
    raw = source["text"].encode()
    if len(raw) > 48000:
        fail("INPUT_TOO_LARGE", "/encoding/source/text")
    if hashlib.sha256(raw).hexdigest() != source["sha256"]:
        fail("SOURCE_MISMATCH", "/encoding/source/sha256")
    ids = set()
    vectors = set()
    for i, c in enumerate(data["concepts"]):
        if c["id"] in ids:
            fail("INVALID_INPUT", f"/encoding/concepts/{i}/id", "Duplicate concept ID")
        ids.add(c["id"])
        v = tuple(c["coordinates"])
        if v == (0, 0) or v in vectors:
            fail(
                "INVALID_INPUT",
                f"/encoding/concepts/{i}/coordinates",
                "Nonzero distinct vectors required",
            )
        vectors.add(v)
        for j, e in enumerate(c["evidence"]):
            source_evidence(source, e, f"/encoding/concepts/{i}/evidence/{j}")
    if len({a["id"] for a in data["axes"]}) != 2:
        fail("INVALID_INPUT", "/encoding/axes", "Distinct axes required")
    seen = set()
    for i, r in enumerate(data["source_relations"]):
        if r["id"] in seen or not set(r["concepts"]) <= ids:
            fail(
                "INVALID_INPUT",
                f"/encoding/source_relations/{i}",
                "Duplicate relation or absent concept",
            )
        seen.add(r["id"])
    p = data["protocol"]
    if p["frame_size"] > p["steps"]:
        fail("INVALID_INPUT", "/encoding/protocol/frame_size")
    # Policy strings are declarative metadata; flags alone select behavior.
    return common_snapshot(data)


def common_snapshot(data: dict) -> dict:
    return {
        "schema": "levinmas-semantic-input/1",
        "source": copy.deepcopy(data["source"]),
        "concepts": [
            {k: copy.deepcopy(c[k]) for k in ("id", "label", "evidence")}
            for c in data["concepts"]
        ],
        "source_relations": copy.deepcopy(data["source_relations"]),
        "uncertainties": list(data["uncertainties"]),
    }


def integrity() -> dict:
    manifest = {
        n.removeprefix("code/"): h
        for n, h in json.loads((VENDOR / "MANIFEST.json").read_text())["files"].items()
        if n.startswith("code/")
    }
    actual = {}
    for name, expected in manifest.items():
        path = VENDOR / "code" / name
        h = hashlib.sha256(path.read_bytes()).hexdigest()
        if h != expected:
            fail("ENGINE_UNAVAILABLE", "", "Vendor integrity failure: " + name)
        actual[name] = h
    return actual
