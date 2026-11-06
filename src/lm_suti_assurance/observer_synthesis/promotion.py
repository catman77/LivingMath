"""Promote labelled short-word context witnesses into two closed finite predicates.

No language-specific flag or builtin calculator: SPLIT/CONCAT and literal equality
are the only executable primitives. A witness is never automatically an invariant.
"""

from pathlib import Path
from collections import defaultdict
import hashlib
from ..core import canonical, digest, strict_json
from ..symbolic.state import apply
from .contexts import record_state

KINDS = {"observed_word_equality", "observed_context_scan"}
MAX_TOKENS = 8


def execute(ast, state, record_ref=None, certify=False):
    if len(state.atoms) > ast["max_tokens"]:
        return None, [], {}
    trace = []
    states = {}

    def ref(s):
        key = digest(s.data())
        if certify:
            states[key] = strict_json(canonical(s.data()))
        return key

    def step(s, op, args, other=None):
        outputs, _ = apply(s, op, args, other)
        if certify:
            trace.append(
                {
                    "operator": op,
                    "args": args,
                    "input_state_ref": ref(s),
                    "input_word_hash": s.word_hash,
                    "other_state_ref": ref(other) if other is not None else None,
                    "output_state_refs": [ref(v) for v in outputs],
                    "output_word_hashes": [v.word_hash for v in outputs],
                }
            )
        return outputs

    def anchor(node, s):
        whole, empty = step(s, "SPLIT", {"position": len(s.atoms)})
        restored = step(whole, "CONCAT", {}, empty)[0]
        result = list(whole.tokens) == node["prototype_tokens"]
        if certify:
            trace.append(
                {
                    "operation": "observed_word_equality",
                    "record_ref": record_ref,
                    "operand_ref": ref(whole),
                    "prototype_record_ref": node["prototype_record_ref"],
                    "prototype_tokens": node["prototype_tokens"],
                    "restored_word_hash": restored.word_hash,
                    "value": result,
                }
            )
        return result

    if certify:
        ref(state)
    if ast["composition"] == "observed_word_equality":
        result = anchor(ast, state)
    elif ast["composition"] == "observed_context_scan":
        values = []
        width = len(ast["predicate_ast"]["prototype_tokens"])
        for start in range(max(0, len(state.atoms) - width + 1)):
            left, tail = step(state, "SPLIT", {"position": start})
            fragment, right = step(tail, "SPLIT", {"position": width})
            joined = step(left, "CONCAT", {}, fragment)[0]
            restored = step(joined, "CONCAT", {}, right)[0]
            if restored.word_hash != state.word_hash or restored.atoms != state.atoms:
                raise ValueError("FRAME_RECONSTRUCTION_FAILED")
            values.append(anchor(ast["predicate_ast"], fragment))
        result = any(values)
        if certify:
            trace.append(
                {
                    "operation": "bounded_context_readout",
                    "parent_feature_ref": ast["parent_feature_ref"],
                    "values": values,
                    "positions_checked": len(values),
                    "value": result,
                }
            )
    else:
        raise ValueError("UNSUPPORTED_OBSERVER_PREDICATE")
    return result, trace, states


def _witness(ast, row):
    state = record_state(row["record"], row["encoded"]["tokens"])
    decision, trace, states = execute(ast, state, digest(row["record"]), True)
    return {
        "record_ref": digest(row["record"]),
        "source_sha256": row["record"]["source"]["sha256"],
        "input_state_ref": digest(state.data()),
        "states": states,
        "operator_trace": trace,
        "decision": decision,
    }


def promote(samples, contexts, policy, search, budget, admitted):
    log = []
    output = []

    def failed(reason, **details):
        log.append(
            {
                "phase": "context_promotion",
                "status": "NOT_PROMOTED",
                "failed_obligation": reason,
                **details,
            }
        )

    if search["max_composition_depth"] < 2:
        failed("MAX_COMPOSITION_DEPTH", required_depth=2)
        return output, log
    if not samples or policy.get("representation", "literal") != "literal":
        failed("LITERAL_SOURCE_REPRESENTATION_REQUIRED")
        return output, log
    if (
        max(len(r["encoded"]["tokens"]) for r in samples) > MAX_TOKENS
        or len(samples) > 64
    ):
        failed(
            "FINITE_SHORT_WORD_SCOPE_REQUIRED",
            max_tokens=MAX_TOKENS,
            max_train_records=64,
        )
        return output, log
    if len(samples) * 2 > search["max_witnesses"]:
        failed("INSUFFICIENT_COMPLETE_TRAIN_WITNESS_BUDGET", required=2 * len(samples))
        return output, log
    labelled = defaultdict(list)
    for row in samples:
        labelled[tuple(row["encoded"]["tokens"])].append(row)
    if any(len({r["record"]["accepted"] for r in rs}) != 1 for rs in labelled.values()):
        failed("CONTRADICTORY_TRAIN_LABELS")
        return output, log
    context_by_ref = {
        c["source_train_ref"]: c
        for c in contexts
        if c["status"] == "DISTINGUISHED"
        and c["left_membership"] is True
        and c["right_membership"] is False
        and c["operator_ast"]["composition"] == "observed_fragment_deletion"
    }
    candidates = sorted(
        [
            r
            for r in samples
            if r["record"]["accepted"] and digest(r["record"]) in context_by_ref
        ],
        key=lambda r: (len(r["encoded"]["tokens"]), digest(r["record"])),
    )
    attempted = set()
    source_binding = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    limit = search["max_proposals"]
    for row in candidates:
        word = tuple(row["encoded"]["tokens"])
        if word in attempted:
            continue
        if len(attempted) >= limit:
            failed("MAX_PROMOTION_PROPOSALS", examined=len(attempted))
            break
        attempted.add(word)
        budget.check()
        log.append(
            {
                "phase": "context_promotion",
                "status": "CANDIDATE_PROPOSED",
                "pattern_record_ref": digest(row["record"]),
            }
        )
        proper = {
            word[a:b]
            for a in range(len(word))
            for b in range(a + 1, len(word) + 1)
            if b - a < len(word)
        }
        if not proper or any(
            w not in labelled or labelled[w][0]["record"]["accepted"] for w in proper
        ):
            failed(
                "LABELLED_PROPER_FRAGMENT_MINIMALITY_REQUIRED",
                pattern_record_ref=digest(row["record"]),
            )
            continue
        maximum = min(
            MAX_TOKENS, 2 * max(len(r["encoded"]["tokens"]) for r in samples) + 2
        )
        anchor_ast = {
            "composition": "observed_word_equality",
            "prototype_tokens": list(word),
            "prototype_record_ref": digest(row["record"]),
            "max_tokens": maximum,
            "equality": "literal_tokens_only",
        }
        anchor_id = "derived_" + digest(anchor_ast)[:20]
        ast = {
            "composition": "observed_context_scan",
            "parent_feature_ref": anchor_id,
            "predicate_ast": anchor_ast,
            "max_tokens": maximum,
            "scan": "all_contiguous_positions",
            "frame_operations": ["SPLIT", "SPLIT", "CONCAT", "CONCAT"],
        }
        proof = {
            "schema": "livingmath-context-promotion/1",
            "label_scope": "train_only",
            "source_train_refs": sorted(digest(r["record"]) for r in samples),
            "positive_record_ref": digest(row["record"]),
            "negative_fragment_refs": sorted(
                digest(labelled[w][0]["record"]) for w in proper
            ),
            "context_witness": context_by_ref[digest(row["record"])],
            "representation": "literal",
            "claim_status": "EMPIRICAL",
            "invariance": ["source_lineage_preserved", "literal_word_reconstructed"],
            "scope_max_tokens": maximum,
        }

        def feature(program, parents, role):
            return {
                "feature_id": "derived_" + digest(program)[:20],
                "feature_version": "2",
                "semantic_type": "bounded_source_boolean_predicate",
                "origin": "DERIVED_FROM_OPERATORS",
                "operator_ast": program,
                "required_observers": [],
                "parent_feature_refs": parents,
                "semantic_alias_of": None,
                "source_code_binding_sha256": source_binding,
                "template_origin": "LABELLED_CONTEXT_PROMOTION",
                "construction_trace": [],
                "promotion_proof": proof,
                "dependency_features": [],
                "role": role,
                "derived_claim_allowed": True,
                "known_invariance_scope": {
                    "representation": "literal",
                    "max_tokens": maximum,
                    "universal_invariant": False,
                },
                "novelty": "Finite composition of existing primitives; no builtin reconstruction claim or new fundamental operation",
            }

        anchor = feature(
            anchor_ast,
            ["operator:SPLIT", "operator:CONCAT", "primitive:literal_word_equality"],
            "DEPENDENCY",
        )
        child = feature(
            ast, [anchor_id, "operator:SPLIT", "operator:CONCAT"], "PREDICTIVE"
        )
        if not admitted(anchor, policy) or not admitted(child, policy):
            failed(
                "PARENT_OR_FEATURE_DISABLED",
                feature_id=child["feature_id"],
                parents=child["parent_feature_refs"],
            )
            continue
        for sample in samples:
            budget.check()
            anchor["construction_trace"].append(_witness(anchor_ast, sample))
            child["construction_trace"].append(_witness(ast, sample))
        mismatches = [
            w["record_ref"]
            for w, r in zip(child["construction_trace"], samples)
            if w["decision"] != r["record"]["accepted"]
        ]
        if mismatches:
            failed(
                "TRAIN_COUNTEREXAMPLE",
                pattern_record_ref=digest(row["record"]),
                counterexample_refs=mismatches,
                executed_rule=True,
            )
            continue
        from .promotion_verifier import verify

        for f in [anchor, child]:
            if f is child:
                f["dependency_features"] = [anchor]
            check = verify(f, samples)
            f["verifier_result"] = check
            f["execution_verified"] = check["status"] == "CHECKED_INSTANCE"
        if not all(f["execution_verified"] for f in [anchor, child]):
            failed("INDEPENDENT_PROMOTION_CHECK_FAILED", executed_rule=True)
            continue
        output.extend([anchor, child])
        log.append(
            {
                "phase": "context_promotion",
                "status": "PROMOTED",
                "feature_id": child["feature_id"],
                "parent_feature_ref": anchor_id,
                "tested_train_records": len(samples),
                "executed_rule": True,
                "registered_features": 2,
                "claim_status": "EMPIRICAL",
            }
        )
        # One promoted predictive rule per bounded pass; no open-ended search.
        break
    if not candidates:
        failed("NO_LABELLED_DISTINGUISHING_CONTEXT")
    return output, log
