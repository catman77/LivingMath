"""Closed additive schemas and finite quotas; numerical contracts are untouched."""

from ..white_star.contracts import check_schema
from ..errors import AssuranceError
from ..core import canonical

OPERATORS = [
    "CONCAT",
    "SPLIT",
    "RENAME",
    "SUBSTITUTE",
    "REVERSE",
    "SP_INV",
    "REDUCE_SP",
    "INSERT_CANCEL_PAIR",
]
OBSERVERS = [
    "literal",
    "alpha_pattern",
    "adjacency",
    "substring_contexts",
    "composition",
    "sp_reduce",
    "hierarchy",
]
LIMITS = dict(
    request_bytes=262144,
    source_bytes=48000,
    max_word_tokens=2048,
    max_nodes=8192,
    max_steps=4096,
    max_candidates_per_step=16,
    max_observations=8192,
    max_total_tokens=131072,
    worker_cpu_s=5,
    worker_wall_s=6,
    worker_memory_bytes=536870912,
    result_bytes=33554432,
    concurrent_jobs=2,
    queue=16,
    page_default=32,
    page_max=128,
    max_rules=15,
    max_features=64,
)


def obj(props, required=()):
    return {
        "type": "object",
        "properties": props,
        "required": list(required),
        "additionalProperties": False,
    }


def arr(items, maximum=256, minimum=0):
    return {"type": "array", "items": items, "maxItems": maximum, "minItems": minimum}


def integer(low, high):
    return {"type": "integer", "minimum": low, "maximum": high}


STRING = {"type": "string", "maxLength": 48000}
REF = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
PROJECT = {"type": "string", "pattern": "^[a-z][a-z0-9_-]{0,63}$"}
KEY = {"type": "string", "pattern": "^[A-Za-z0-9_.:-]{1,128}$"}
SPAN = obj(
    {"byte_start": integer(0, 48000), "byte_end": integer(0, 48000)},
    ["byte_start", "byte_end"],
)
TOKEN = obj(
    {
        "token": {"type": "string", "minLength": 1, "maxLength": 1024},
        **SPAN["properties"],
    },
    ["token", "byte_start", "byte_end"],
)
SEGMENT = obj(
    {
        "id": STRING,
        "parent_id": {"type": ["string", "null"]},
        "kind": STRING,
        **SPAN["properties"],
    },
    ["id", "kind", "byte_start", "byte_end"],
)
SOURCE = obj(
    {
        "text": STRING,
        "sha256": REF,
        "title": STRING,
        "author": STRING,
        "edition": STRING,
        "language": STRING,
        "url": STRING,
        "rights": STRING,
        "alphabet": arr({"type": "string", "minLength": 1, "maxLength": 1024}, 256, 1),
        "segments": arr(SEGMENT, 256),
        "layout": {"type": "object", "maxProperties": 256},
    },
    ["text", "sha256"],
)
SEARCH = obj(
    {
        "seed": integer(0, 2**32 - 1),
        "max_steps": integer(0, 4096),
        "max_candidates_per_step": integer(1, 16),
        "max_word_tokens": integer(1, 2048),
        "max_nodes": integer(1, 8192),
        "max_observations": integer(1, 8192),
        "max_total_tokens": integer(1, 131072),
        "strategy": {"enum": ["local_structural_novelty", "random_local"]},
        "history_identity": {"enum": ["word", "provenance"]},
    },
    [
        "seed",
        "max_steps",
        "max_candidates_per_step",
        "max_word_tokens",
        "max_nodes",
        "strategy",
    ],
)
TRAIN = obj(
    {
        "tokens": arr({"type": "string", "minLength": 1, "maxLength": 1024}, 512),
        "accepted": {"type": "boolean"},
    },
    ["tokens", "accepted"],
)
TASK = obj(
    {
        "mode": {"enum": ["discover_relations", "descriptive", "predictive"]},
        "train": arr(TRAIN, 256),
        "predict": arr(
            arr({"type": "string", "minLength": 1, "maxLength": 1024}, 512), 256
        ),
        "max_rules": integer(1, 15),
    },
    ["mode"],
)
REQUEST = obj(
    {
        "schema": {"const": "levinmas-white-star-symbolic-request/1"},
        "source": SOURCE,
        "normalization": {"enum": ["none", "NFC"]},
        "segmentation": obj(
            {
                "unit": {"enum": ["codepoint", "literal_token", "whitespace", "line"]},
                "record_boundaries": {"enum": ["lines", "whole"]},
                "renaming_scope": {"enum": ["global", "local"]},
                "tokens": arr(TOKEN, 2048),
            },
            ["unit", "record_boundaries", "renaming_scope"],
        ),
        "algebra": obj(
            {
                "kind": {"enum": ["SP", "FREE"]},
                "allow_reduce": {"type": "boolean"},
                "preserve_history": {"const": True},
            },
            ["kind", "allow_reduce", "preserve_history"],
        ),
        "observers": arr({"enum": OBSERVERS}, len(OBSERVERS), 1),
        "operators": arr({"enum": OPERATORS}, len(OPERATORS), 1),
        "search": SEARCH,
        "task": TASK,
    },
    [
        "schema",
        "source",
        "segmentation",
        "algebra",
        "observers",
        "operators",
        "search",
        "task",
    ],
)


def validate(request):
    check_schema(request, REQUEST)
    try:
        encoded = canonical(request).encode()
    except UnicodeError:
        raise AssuranceError("INVALID_UTF8", "/source/text")
    if len(encoded) > LIMITS["request_bytes"]:
        raise AssuranceError("INPUT_TOO_LARGE", "/request")
    if len(request["source"]["text"].encode()) > LIMITS["source_bytes"]:
        raise AssuranceError("INPUT_TOO_LARGE", "/source/text")
    if request["algebra"]["kind"] != "SP" and (
        set(request["operators"]) & {"SP_INV", "REDUCE_SP", "INSERT_CANCEL_PAIR"}
        or "sp_reduce" in request["observers"]
    ):
        raise AssuranceError("SP_ALGEBRA_REQUIRED", "/algebra/kind")
    if "REDUCE_SP" in request["operators"] and not request["algebra"]["allow_reduce"]:
        raise AssuranceError("REDUCTION_NOT_ALLOWED", "/algebra/allow_reduce")
    if len(set(request["operators"])) != len(request["operators"]) or len(
        set(request["observers"])
    ) != len(request["observers"]):
        raise AssuranceError("DUPLICATE_OPTION")
    if request["task"]["mode"] == "predictive" and not request["task"].get("train"):
        raise AssuranceError("TRAIN_REQUIRED", "/task/train")
    return request
