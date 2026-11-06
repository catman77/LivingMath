"""Existing builtin features and train-derived compositions with executed traces."""

from pathlib import Path
import hashlib
from ..core import digest
from ..symbolic import grammar
from .operator_execution import value as operator_value, evaluate

DEPS = {
    "length": ["literal"],
    "length_mod_2": ["literal"],
    "distinct_atoms": ["alpha_pattern"],
    "endpoint_equal": ["alpha_pattern"],
    "adjacent_equal": ["adjacency"],
}


def encode(record, mode):
    lines = record.get("lines") or [record["tokens"]]
    if mode == "global_alpha":
        names = {}
        encoded = [
            [str(names.setdefault(t, len(names))) for t in line] for line in lines
        ]
    elif mode == "local_alpha":
        encoded = []
        for line in lines:
            names = {}
            encoded.append([str(names.setdefault(t, len(names))) for t in line])
    elif mode == "punctuation":
        encoded = [
            [t[-1] for t in line[-1:] if t and not t[-1].isalnum()] for line in lines
        ]
    elif mode == "length":
        encoded = [["unit"] * len(line) for line in lines]
    else:
        encoded = [list(line) for line in lines]
    # IDs, byte offsets, century/quatrain and source titles NEVER enter a vector.
    return {
        "tokens": [t for line in encoded for t in line],
        "lines": encoded,
        "signature": digest(encoded),
    }


def dependencies(name):
    if name.startswith("pair_"):
        return ["composition"]
    if name.startswith("lag_"):
        return ["alpha_pattern"]
    if name.startswith("line_"):
        return ["literal"]
    return DEPS[name]


def builtin_registry(samples, policy, alphabet):
    binding = hashlib.sha256(Path(grammar.__file__).read_bytes()).hexdigest()
    enabled = policy["enabled_builtins"]
    mode = policy.get("representation", "literal")
    # Declare the fixed registry without evaluating any builtin value. In
    # particular an operator-only allowlist must not run pair statistics even
    # on a single sample just to discover their names.
    names = {"length", "length_mod_2"}
    if "alpha_pattern" in enabled:
        names.update({"distinct_atoms", "endpoint_equal"})
        names.update("lag_" + str(i) + "_mismatches" for i in range(1, 5))
    if "adjacency" in enabled:
        names.add("adjacent_equal")
    if "composition" in enabled:
        names.update(
            "pair_" + str(i) + "_" + suffix
            for i in range(min(4, max(0, len(alphabet) - 1)))
            for suffix in ("final", "min", "max")
        )
    if mode in ("length", "punctuation"):
        names = {"length", "length_mod_2"}
    if any(len(s["lines"]) > 1 for s in samples):
        names.update(
            "line_" + str(i) + "_length"
            for i in range(min(4, max(len(s["lines"]) for s in samples)))
        )
    if mode == "punctuation":
        names.update(
            "line_" + str(i) + "_terminal_codepoint"
            for i in range(min(4, max(len(s["lines"]) for s in samples)))
        )
    records = []
    for name in sorted(names):
        records.append(
            {
                "feature_id": name,
                "feature_version": "1",
                "semantic_type": "finite_word_observer",
                "origin": "BUILTIN",
                "required_observers": dependencies(name),
                "parent_feature_refs": [],
                "source_code_binding_sha256": (
                    binding
                    if not name.startswith("line_")
                    else hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
                ),
                "builtin_function_ref": (
                    "symbolic.grammar.features"
                    if not name.startswith("line_")
                    else "observer_synthesis.features.vector(line_surface_observations)"
                ),
                "construction_trace": None,
                "derived_claim_allowed": False,
                "known_invariance_scope": "declared representation only",
            }
        )
    return records


def admitted(feature, policy):
    name = feature["feature_id"]
    deny = set(policy.get("feature_denylist", []))
    allow = policy.get("feature_allowlist")
    required = set(feature.get("required_observers", []))
    parents = set(feature.get("parent_feature_refs", []))
    computational_parents = {
        p for p in parents if not p.startswith(("operator:", "primitive:"))
    }
    alias = feature.get("semantic_alias_of")
    allowed = (
        allow is None
        or ({name} | computational_parents) <= set(allow)
        or (
            "derived:*" in allow
            and feature["origin"] == "DERIVED_FROM_OPERATORS"
            and not computational_parents
        )
    )
    return (
        alias not in deny
        and not ({name} | parents | {"observer:" + x for x in required}) & deny
        and required <= set(policy["enabled_builtins"])
        and allowed
    )


def vector(encoded, alphabet, policy, features):
    builtin = [f for f in features if f["origin"] == "BUILTIN"]
    groups = sorted({g for f in builtin for g in f["required_observers"]})
    values = (
        grammar.features(
            encoded["tokens"], alphabet, groups or ["_no_builtin_observer_"]
        )
        if builtin
        else {}
    )
    for i, line in enumerate(encoded["lines"][:4]):
        values["line_" + str(i) + "_length"] = len(line)
        values["line_" + str(i) + "_terminal_codepoint"] = (
            ord(line[-1][-1]) if line else 0
        )
    return {
        f["feature_id"]: (
            int(operator_value(f["operator_ast"], encoded["tokens"]))
            if f["origin"] == "DERIVED_FROM_OPERATORS"
            else values.get(f["feature_id"], 0)
        )
        for f in features
    }


def derive(samples, policy, search, budget):
    if not policy.get("derive_relations", True):
        return [], []
    members = [
        {"tokens": s["encoded"]["tokens"], "accepted": s["record"]["accepted"]}
        for s in samples
    ]
    candidates, log = grammar.relational_candidates(
        members, min(15, search["max_proposals"]), policy["enabled_builtins"]
    )
    out = []
    used = 0
    for c in candidates[: search["max_proposals"]]:
        ast = c["ast"]
        depth = c["hypothesis_complexity"]["ast_depth"]
        if depth > search["max_composition_depth"]:
            continue
        feature = {
            "feature_id": "derived_" + digest(ast)[:20],
            "feature_version": "1",
            "semantic_type": "finite_context_relation",
            "origin": "DERIVED_FROM_OPERATORS",
            "operator_ast": ast,
            "required_observers": ["alpha_pattern", "composition"],
            "parent_feature_refs": [
                "operator:SPLIT",
                "operator:REVERSE",
                "primitive:literal_token_equality",
            ],
            "semantic_alias_of": (
                "endpoint_equal"
                if ast["composition"] == "aligned_token_equality" and ast["offset"] == 0
                else None
            ),
            "novelty": "Composition of existing primitives; reconstruction of a known relation is not a newly discovered primitive",
            "source_code_binding_sha256": hashlib.sha256(
                Path(grammar.__file__).read_bytes()
            ).hexdigest(),
            "template_origin": "BUILTIN_COMPOSITION_TEMPLATE_TRAIN_DERIVED_PARAMETERS",
            "construction_trace": [],
            "derived_claim_allowed": True,
            "known_invariance_scope": "finite train and declared within-word contexts; not a universal congruence",
        }
        if not admitted(feature, policy):
            continue
        for s in samples:
            if used >= search["max_witnesses"]:
                break
            budget.check()
            from .contexts import record_state

            state = record_state(s["record"], s["encoded"]["tokens"])
            decision, trace, states = evaluate(
                ast, state, digest(s["record"]), certify=True
            )
            feature["construction_trace"].append(
                {
                    "record_ref": digest(s["record"]),
                    "source_sha256": s["record"]["source"]["sha256"],
                    "operator_trace": trace,
                    "states": states,
                    "input_state_ref": digest(state.data()),
                    "decision": decision,
                }
            )
            used += 1
        check = verify_feature(feature, samples)
        feature["execution_verified"] = check["status"] == "CHECKED_FINITE_INSTANCE"
        feature["verifier_result"] = check
        if feature["execution_verified"]:
            out.append(feature)
    return out, log


def verify_feature(feature, samples):
    from .independent_verifier import verify

    return verify(feature, samples)
