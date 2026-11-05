"""Private datasets separate train labels from queries at the public schema boundary."""

from ..symbolic.contracts import obj, arr, integer, REF, OBSERVERS
from ..symbolic_complex.contracts import STRING

SOURCE = obj(
    {
        "text": {"type": "string", "maxLength": 48000},
        "sha256": REF,
        "rights": STRING,
        "edition": STRING,
    },
    ["text", "sha256", "rights", "edition"],
)
SEGMENT = obj(
    {
        "id": STRING,
        "parent_id": {"type": ["string", "null"], "maxLength": 1024},
        "kind": {"enum": ["century", "quatrain", "line", "word"]},
        "byte_start": integer(0, 48000),
        "byte_end": integer(0, 48000),
    },
    ["id", "parent_id", "kind", "byte_start", "byte_end"],
)
RECORD = obj(
    {
        "id": STRING,
        "tokens": arr(STRING, 512),
        "lines": arr(arr(STRING, 128), 32),
        "pair_id": STRING,
        "source": SOURCE,
        "segments": arr(SEGMENT, 600),
        "metadata": obj(
            {
                "century": integer(1, 10),
                "quatrain": integer(1, 100),
                "parent_source_ref": REF,
                "edition_confidence": STRING,
                "parent_byte_start": integer(0, 48000),
                "parent_byte_end": integer(0, 48000),
            }
        ),
    },
    ["id", "tokens", "source"],
)
TRAIN = {
    **RECORD,
    "properties": {**RECORD["properties"], "accepted": {"type": "boolean"}},
    "required": [*RECORD["required"], "accepted"],
}
DATASET = obj(
    {
        "schema": {"const": "livingmath-observer-dataset/1"},
        "kind": {"enum": ["train", "queries", "collection"]},
        "records": {"type": "array", "maxItems": 256},
        "parts": arr(REF, 64),
        "record_kind": {"enum": ["train", "queries"]},
        "sha256": REF,
    },
    ["schema", "kind", "sha256"],
)
POLICY = obj(
    {
        "enabled_builtins": arr({"enum": OBSERVERS}, 7),
        "feature_allowlist": arr(STRING, 128),
        "feature_denylist": arr(STRING, 128),
        "prohibit_undocumented_builtins": {"const": True},
        "synthesis_origin_required": {"const": True},
        "renaming_scope": {"const": "per_variant"},
        "strict_source_boundaries": {"const": True},
        "representation": {
            "enum": ["literal", "global_alpha", "local_alpha", "punctuation", "length"]
        },
        "derive_relations": {"type": "boolean"},
    },
    [
        "enabled_builtins",
        "prohibit_undocumented_builtins",
        "synthesis_origin_required",
        "renaming_scope",
        "strict_source_boundaries",
    ],
)
SEARCH = obj(
    {
        "seed": integer(0, 2**32 - 1),
        "max_composition_depth": integer(1, 4),
        "max_proposals": integer(1, 128),
        "max_contexts": integer(1, 256),
        "max_witnesses": integer(1, 512),
        "max_cpu_ms": integer(1, 4000),
    },
    [
        "seed",
        "max_composition_depth",
        "max_proposals",
        "max_contexts",
        "max_witnesses",
        "max_cpu_ms",
    ],
)
REQUEST = obj(
    {
        "schema": {"const": "livingmath-symbolic-observer-synthesis-request/1"},
        "source_run_id": REF,
        "task": obj(
            {
                "mode": {"const": "context_relation_induction"},
                "conflict_policy": {
                    "enum": [
                        "report_only",
                        "exclude_with_report",
                        "retain_as_empirical",
                    ]
                },
                "train_ref": REF,
                "predict_ref": REF,
                "holdout_labels_visible": {"const": False},
                "structure_levels": arr(
                    {"enum": ["word", "line", "quatrain", "century"]}, 4
                ),
                "candidate_transformations": arr(
                    {"enum": ["SWAP_LINES_2_3", "REVERSE", "RENAME"]}, 3
                ),
            },
            [
                "mode",
                "train_ref",
                "predict_ref",
                "holdout_labels_visible",
                "structure_levels",
                "candidate_transformations",
            ],
        ),
        "feature_policy": POLICY,
        "search": SEARCH,
    },
    ["schema", "task", "feature_policy", "search"],
)
