"""Existing builtin features and train-derived compositions with executed traces."""

from pathlib import Path
import hashlib
from ..core import digest
from ..symbolic import grammar
from ..symbolic.state import Atom, SymbolicState, apply

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
    sample = samples[0]
    names = set(
        grammar.features(
            sample["tokens"], alphabet, enabled or ["_no_builtin_observer_"]
        )
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
            int(grammar.relation_value(f["operator_ast"], encoded["tokens"]))
            if f["origin"] == "DERIVED_FROM_OPERATORS"
            else values.get(f["feature_id"], 0)
        )
        for f in features
    }


def execution_trace(ast, tokens, record_ref, depth=0, state=None):
    """Execute the stored existing relation AST with actual state.apply operators."""
    if depth > 4:
        raise ValueError("MAX_COMPOSITION_DEPTH")
    operation = ast["composition"]
    if state is None:
        state = SymbolicState(tuple(Atom(t, ()) for t in tokens))
    if operation == "all_observed_relations":
        return [
            x
            for a in ast["relations"]
            for x in execution_trace(a, tokens, record_ref, depth + 1, state)
        ]
    if operation == "iterate_on_inner_fragment":
        out = []
        remaining = list(tokens)
        current_state = state
        for _ in range(len(tokens) + 1):
            if len(remaining) <= ast["base_max_tokens"]:
                break
            out += execution_trace(
                ast["relation"], remaining, record_ref, depth + 1, current_state
            )
            state = current_state
            left, _ = apply(state, "SPLIT", {"position": ast["trim_left"]})
            inner, _ = apply(
                left[1], "SPLIT", {"position": len(left[1].tokens) - ast["trim_right"]}
            )
            out.append(
                {
                    "operator": "SPLIT",
                    "args": {"position": ast["trim_left"]},
                    "input_word_hash": state.word_hash,
                    "output_word_hashes": [s.word_hash for s in left],
                }
            )
            out.append(
                {
                    "operator": "SPLIT",
                    "args": {"position": len(left[1].tokens) - ast["trim_right"]},
                    "input_word_hash": left[1].word_hash,
                    "output_word_hashes": [s.word_hash for s in inner],
                }
            )
            remaining = list(inner[0].tokens)
            current_state = inner[0]
        return out
    if operation != "aligned_token_equality":
        raise ValueError("UNSUPPORTED_RULE")
    if len(tokens) <= ast["base_max_tokens"]:
        return [
            {"operation": "declared_base_case", "record_ref": record_ref, "value": True}
        ]
    reverse, _ = apply(state, "REVERSE", {})
    offset = ast["offset"]
    trace = []
    selected = []
    trace.append(
        {
            "operator": "REVERSE",
            "args": {},
            "input_word_hash": state.word_hash,
            "output_word_hashes": [reverse[0].word_hash],
        }
    )
    for s in (state, reverse[0]):
        parts, _ = apply(s, "SPLIT", {"position": offset})
        atoms, _ = apply(parts[1], "SPLIT", {"position": 1})
        selected.append(atoms[0].tokens)
        trace.extend(
            [
                {
                    "operator": "SPLIT",
                    "args": {"position": offset},
                    "input_word_hash": s.word_hash,
                    "output_word_hashes": [p.word_hash for p in parts],
                },
                {
                    "operator": "SPLIT",
                    "args": {"position": 1},
                    "input_word_hash": parts[1].word_hash,
                    "output_word_hashes": [p.word_hash for p in atoms],
                },
            ]
        )
    verdict = (selected[0] == selected[1]) == ast["expected_equal"]
    if verdict != grammar.relation_value(ast, tokens):
        raise ValueError("EXECUTION_TRACE_MISMATCH")
    return trace + [
        {
            "operation": "literal_token_equality",
            "operands": [list(t) for t in selected],
            "value": verdict,
            "record_ref": record_ref,
        }
    ]


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

            trace = execution_trace(
                ast,
                s["encoded"]["tokens"],
                digest(s["record"]),
                state=record_state(s["record"], s["encoded"]["tokens"]),
            )
            feature["construction_trace"].append(
                {
                    "record_ref": digest(s["record"]),
                    "source_sha256": s["record"]["source"]["sha256"],
                    "operator_trace": trace,
                    "decision": grammar.relation_value(ast, s["encoded"]["tokens"]),
                }
            )
            used += 1
        check = verify_feature(feature, samples)
        feature["execution_verified"] = check["status"] == "CHECKED_FINITE_INSTANCE"
        feature["verifier_result"] = check
        if feature["execution_verified"]:
            out.append(feature)
    return out, log


def valid_ast(ast, depth=0):
    if not isinstance(ast, dict) or depth > 4:
        return False
    op = ast.get("composition")
    if op == "aligned_token_equality":
        k = ast.get("offset")
        return (
            type(k) is int
            and 0 <= k <= 3
            and type(ast.get("expected_equal")) is bool
            and ast.get("base_max_tokens") == 2 * k + 1
            and ast.get("left_operations") == ["SPLIT"]
            and ast.get("right_operations") == ["REVERSE", "SPLIT"]
        )
    if op == "iterate_on_inner_fragment":
        return (
            ast.get("trim_left") == ast.get("trim_right") == 1
            and ast.get("base_max_tokens") == 1
            and valid_ast(ast.get("relation"), depth + 1)
        )
    if op == "all_observed_relations":
        return 1 <= len(ast.get("relations", [])) <= 4 and all(
            valid_ast(a, depth + 1) for a in ast["relations"]
        )
    return False


def verify_feature(feature, samples):
    """Replay every claimed operator witness; a claimed origin/boolean is insufficient."""
    if feature.get("origin") == "BUILTIN":
        return {"status": "BUILTIN", "derived_claim_allowed": False}
    if feature.get("origin") != "DERIVED_FROM_OPERATORS":
        return {"status": "REJECTED", "field_path": "/origin"}
    ast = feature.get("operator_ast")
    if (
        feature.get("source_code_binding_sha256")
        != hashlib.sha256(Path(grammar.__file__).read_bytes()).hexdigest()
    ):
        return {"status": "REJECTED", "field_path": "/source_code_binding_sha256"}
    if not valid_ast(ast):
        return {"status": "REJECTED", "field_path": "/operator_ast"}
    if feature.get("feature_id") != "derived_" + digest(ast)[:20]:
        return {"status": "REJECTED", "field_path": "/feature_id"}
    expected_alias = (
        "endpoint_equal"
        if ast["composition"] == "aligned_token_equality" and ast["offset"] == 0
        else None
    )
    if feature.get("semantic_alias_of") != expected_alias:
        return {"status": "REJECTED", "field_path": "/semantic_alias_of"}
    evidence = feature.get("construction_trace")
    if not isinstance(evidence, list) or not evidence:
        return {"status": "REJECTED", "field_path": "/construction_trace"}
    indexed = {digest(s["record"]): s for s in samples}
    for i, row in enumerate(evidence):
        sample = indexed.get(row.get("record_ref"))
        if (
            sample is None
            or row.get("source_sha256") != sample["record"]["source"]["sha256"]
        ):
            return {
                "status": "REJECTED",
                "field_path": f"/construction_trace/{i}/record_ref",
            }
        from .contexts import record_state

        if row.get("operator_trace") != execution_trace(
            ast,
            sample["encoded"]["tokens"],
            row["record_ref"],
            state=record_state(sample["record"], sample["encoded"]["tokens"]),
        ) or row.get("decision") != grammar.relation_value(
            ast, sample["encoded"]["tokens"]
        ):
            return {
                "status": "REJECTED",
                "field_path": f"/construction_trace/{i}/operator_trace",
            }
    return {
        "status": "CHECKED_FINITE_INSTANCE",
        "verified_witnesses": len(evidence),
        "operator_ast_digest": digest(ast),
    }
