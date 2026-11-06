"""Independent checker for the two fixed context-promotion predicates.

Does not import promotion, contexts, operator_execution or grammar; no label from
outside the supplied immutable train snapshot is admissible.
"""

from pathlib import Path
import re, hashlib
from ..core import digest, canonical, strict_json
from ..symbolic.state import Atom, SymbolicState, apply

VERSION = "context-promotion-independent-checker/1"


def check(condition):
    if not condition:
        raise ValueError("INVALID_PROMOTION_CERTIFICATE")


def state_for(record):
    text = record["source"]["text"]
    sha = record["source"]["sha256"]
    check(
        hashlib.sha256(text.encode()).hexdigest() == sha
        and text.split() == record["tokens"]
    )
    atoms = tuple(
        Atom(
            m.group(),
            ((sha, len(text[: m.start()].encode()), len(text[: m.end()].encode())),),
        )
        for m in re.finditer(r"\S+", text)
    )
    bounds = []
    offset = 0
    for i, line in enumerate(record.get("lines") or [record["tokens"]]):
        bounds += [
            (offset, "record_start", str(i)),
            (offset + len(line), "record_end", str(i)),
        ]
        offset += len(line)
    return SymbolicState(atoms, tuple(bounds))


def shape(ast):
    if (
        not isinstance(ast, dict)
        or type(ast.get("max_tokens")) is not int
        or not 1 <= ast["max_tokens"] <= 8
    ):
        return False
    if ast.get("composition") == "observed_word_equality":
        tokens = ast.get("prototype_tokens")
        return (
            set(ast)
            == {
                "composition",
                "prototype_tokens",
                "prototype_record_ref",
                "max_tokens",
                "equality",
            }
            and isinstance(tokens, list)
            and 1 <= len(tokens) <= 8
            and all(isinstance(t, str) and 0 < len(t) <= 1024 for t in tokens)
            and isinstance(ast["prototype_record_ref"], str)
            and bool(re.fullmatch("[0-9a-f]{64}", ast["prototype_record_ref"]))
            and ast["equality"] == "literal_tokens_only"
        )
    if ast.get("composition") == "observed_context_scan":
        predicate = ast.get("predicate_ast")
        return (
            set(ast)
            == {
                "composition",
                "parent_feature_ref",
                "predicate_ast",
                "max_tokens",
                "scan",
                "frame_operations",
            }
            and isinstance(predicate, dict)
            and predicate.get("composition") == "observed_word_equality"
            and shape(predicate)
            and ast["parent_feature_ref"] == "derived_" + digest(predicate)[:20]
            and ast["max_tokens"] == predicate["max_tokens"]
            and ast["scan"] == "all_contiguous_positions"
            and ast["frame_operations"] == ["SPLIT", "SPLIT", "CONCAT", "CONCAT"]
        )
    return False


def verify(feature, samples):
    def rejected(path, reason):
        return {
            "status": "REJECTED",
            "field_path": path,
            "reason": reason,
            "verifier_version": VERSION,
            "execution_permission": False,
        }

    try:
        pending = [feature]
        while pending:
            item = pending.pop()
            if isinstance(item, dict):
                check(
                    not set(item)
                    & {
                        "heldout_labels",
                        "test_labels",
                        "query_labels",
                        "hidden_labels",
                        "accepted",
                    }
                )
                pending.extend(item.values())
            elif isinstance(item, list):
                pending.extend(item)
        allowed = {
            "feature_id",
            "feature_version",
            "semantic_type",
            "origin",
            "operator_ast",
            "required_observers",
            "parent_feature_refs",
            "semantic_alias_of",
            "source_code_binding_sha256",
            "template_origin",
            "construction_trace",
            "promotion_proof",
            "dependency_features",
            "role",
            "derived_claim_allowed",
            "known_invariance_scope",
            "novelty",
            "execution_verified",
            "verifier_result",
            "digest",
        }
        check(set(feature) <= allowed and feature["origin"] == "DERIVED_FROM_OPERATORS")
        ast = feature["operator_ast"]
        check(shape(ast))
        check(feature["feature_id"] == "derived_" + digest(ast)[:20])
        check(
            feature["source_code_binding_sha256"]
            == hashlib.sha256(
                Path(__file__).with_name("promotion.py").read_bytes()
            ).hexdigest()
        )
        check(
            feature["required_observers"] == []
            and feature["semantic_alias_of"] is None
            and feature["template_origin"] == "LABELLED_CONTEXT_PROMOTION"
        )
        check(0 < len(samples) <= 64)
        indexed = {digest(s["record"]): s["record"] for s in samples}
        check(
            len(indexed) == len(samples)
            and all(type(r.get("accepted")) is bool for r in indexed.values())
        )
        check(all(s["encoded"]["tokens"] == s["record"]["tokens"] for s in samples))
        proof = feature["promotion_proof"]
        check(
            set(proof)
            == {
                "schema",
                "label_scope",
                "source_train_refs",
                "positive_record_ref",
                "negative_fragment_refs",
                "context_witness",
                "representation",
                "claim_status",
                "invariance",
                "scope_max_tokens",
            }
        )
        check(
            proof["schema"] == "livingmath-context-promotion/1"
            and proof["label_scope"] == "train_only"
            and proof["source_train_refs"] == sorted(indexed)
            and proof["representation"] == "literal"
            and proof["claim_status"] == "EMPIRICAL"
        )
        check(
            proof["invariance"]
            == ["source_lineage_preserved", "literal_word_reconstructed"]
            and proof["scope_max_tokens"] == ast["max_tokens"]
        )
        prototype = (
            ast
            if ast["composition"] == "observed_word_equality"
            else ast["predicate_ast"]
        )
        ref = prototype["prototype_record_ref"]
        record = indexed[ref]
        check(
            record["accepted"] is True
            and record["tokens"] == prototype["prototype_tokens"]
            and proof["positive_record_ref"] == ref
        )
        word = tuple(record["tokens"])
        proper = {
            word[a:b]
            for a in range(len(word))
            for b in range(a + 1, len(word) + 1)
            if b - a < len(word)
        }
        negatives = [indexed[r] for r in proof["negative_fragment_refs"]]
        check(
            proper
            and len(negatives) == len(proper)
            and {tuple(r["tokens"]) for r in negatives} == proper
            and all(r["accepted"] is False for r in negatives)
        )
        scope = {
            "representation": "literal",
            "max_tokens": ast["max_tokens"],
            "universal_invariant": False,
        }
        check(feature["known_invariance_scope"] == scope)
        # Independently replay the original deletion witness and resolve its output label.
        context = proof["context_witness"]
        check(
            context["source_train_ref"] == ref
            and context["source_sha256"] == record["source"]["sha256"]
            and context["status"] == "DISTINGUISHED"
            and context["origin"] == "DERIVED_FROM_OPERATORS"
            and context["left_membership"] is True
            and context["right_membership"] is False
        )
        original = state_for(record)
        k = len(original.tokens) // 2
        left, tail = apply(original, "SPLIT", {"position": k})[0]
        cut = min(1, len(tail.tokens))
        middle, right = apply(tail, "SPLIT", {"position": cut})[0]
        joined = apply(left, "CONCAT", {}, right)[0][0]
        check(
            context["operator_ast"]
            == {
                "operations": ["SPLIT", "SPLIT", "CONCAT"],
                "cuts": [k, cut],
                "composition": "observed_fragment_deletion",
            }
        )

        def context_step(s, op, args, other=None):
            result, _ = apply(s, op, args, other)
            return {
                "operator": op,
                "args": args,
                "input_word_hash": s.word_hash,
                "input_lineage_digest": digest(s.data()),
                "other_lineage_digest": digest(other.data())
                if other is not None
                else None,
                "output_word_hashes": [o.word_hash for o in result],
                "output_lineage_digests": [digest(o.data()) for o in result],
            }

        expected = [
            context_step(original, "SPLIT", {"position": k}),
            context_step(tail, "SPLIT", {"position": cut}),
            context_step(left, "CONCAT", {}, right),
        ]
        check(
            context["operator_trace"] == expected
            and context["target_encoding_digest"] == digest([list(joined.tokens)])
        )
        known = [r for r in indexed.values() if r["tokens"] == list(joined.tokens)]
        check(
            known
            and all(r["accepted"] is False for r in known)
            and set(context["right_source_refs"]) == {digest(r) for r in known}
        )
        if ast["composition"] == "observed_context_scan":
            check(
                feature["role"] == "PREDICTIVE"
                and feature["parent_feature_refs"]
                == [ast["parent_feature_ref"], "operator:SPLIT", "operator:CONCAT"]
            )
            check(len(feature["dependency_features"]) == 1)
            parent = feature["dependency_features"][0]
            check(
                parent["feature_id"] == ast["parent_feature_ref"]
                and parent["operator_ast"] == prototype
                and parent["promotion_proof"] == proof
            )
            check(verify(parent, samples)["status"] == "CHECKED_INSTANCE")
        else:
            check(
                feature["role"] == "DEPENDENCY"
                and feature["parent_feature_refs"]
                == [
                    "operator:SPLIT",
                    "operator:CONCAT",
                    "primitive:literal_word_equality",
                ]
                and feature["dependency_features"] == []
            )
        evidence = feature["construction_trace"]
        check(
            len(evidence) == len(samples)
            and {w["record_ref"] for w in evidence} == set(indexed)
        )
        for witness in evidence:
            check(
                set(witness)
                == {
                    "record_ref",
                    "source_sha256",
                    "input_state_ref",
                    "states",
                    "operator_trace",
                    "decision",
                }
            )
            r = indexed[witness["record_ref"]]
            carrier = state_for(r)
            check(len(carrier.tokens) <= ast["max_tokens"])
            check(
                witness["source_sha256"] == r["source"]["sha256"]
                and witness["input_state_ref"] == digest(carrier.data())
            )
            table = witness["states"]
            check(table and all(digest(v) == key for key, v in table.items()))
            visited = set()
            steps = iter(witness["operator_trace"])

            def require_state(s):
                key = digest(s.data())
                visited.add(key)
                check(table[key] == strict_json(canonical(s.data())))
                return key

            def operation(s, op, args, other=None):
                outputs, _ = apply(s, op, args, other)
                expected = {
                    "operator": op,
                    "args": args,
                    "input_state_ref": require_state(s),
                    "input_word_hash": s.word_hash,
                    "other_state_ref": require_state(other)
                    if other is not None
                    else None,
                    "output_state_refs": [require_state(o) for o in outputs],
                    "output_word_hashes": [o.word_hash for o in outputs],
                }
                check(next(steps) == expected)
                return outputs

            def anchor(node, value):
                complete, empty = operation(
                    value, "SPLIT", {"position": len(value.tokens)}
                )
                restored = operation(complete, "CONCAT", {}, empty)[0]
                answer = list(value.tokens) == node["prototype_tokens"]
                check(
                    next(steps)
                    == {
                        "operation": "observed_word_equality",
                        "record_ref": witness["record_ref"],
                        "operand_ref": require_state(complete),
                        "prototype_record_ref": node["prototype_record_ref"],
                        "prototype_tokens": node["prototype_tokens"],
                        "restored_word_hash": restored.word_hash,
                        "value": answer,
                    }
                )
                return answer

            require_state(carrier)
            if ast["composition"] == "observed_word_equality":
                answer = anchor(ast, carrier)
            else:
                decisions = []
                m = len(prototype["prototype_tokens"])
                for start in range(max(0, len(carrier.tokens) - m + 1)):
                    left, tail = operation(carrier, "SPLIT", {"position": start})
                    fragment, right = operation(tail, "SPLIT", {"position": m})
                    partial = operation(left, "CONCAT", {}, fragment)[0]
                    rebuilt = operation(partial, "CONCAT", {}, right)[0]
                    check(
                        rebuilt.tokens == carrier.tokens
                        and rebuilt.atoms == carrier.atoms
                        and rebuilt.word_hash == carrier.word_hash
                    )
                    decisions.append(anchor(prototype, fragment))
                answer = any(decisions)
                # Direct bounded semantics is independent of producer operator traversal.
                check(
                    answer
                    == any(
                        tuple(carrier.tokens[i : i + m])
                        == tuple(prototype["prototype_tokens"])
                        for i in range(len(carrier.tokens) - m + 1)
                    )
                )
                check(
                    next(steps)
                    == {
                        "operation": "bounded_context_readout",
                        "parent_feature_ref": ast["parent_feature_ref"],
                        "values": decisions,
                        "positions_checked": len(decisions),
                        "value": answer,
                    }
                )
                check(answer == r["accepted"])
            check(
                witness["decision"] == answer
                and next(steps, None) is None
                and visited == set(table)
            )
    except (KeyError, ValueError, TypeError, IndexError, StopIteration, RecursionError):
        return rejected(
            "/promotion_certificate",
            "Origin, AST, train-only label contract, source lineage, parent or operator trace failed",
        )
    return {
        "status": "CHECKED_INSTANCE",
        "claim_status": "CHECKED_FINITE_INSTANCE",
        "verified_witnesses": len(evidence),
        "operator_ast_digest": digest(ast),
        "verifier_version": VERSION,
        "verifier_digest": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "training_compatibility": feature["role"] == "PREDICTIVE",
        "universal_invariant": False,
        "execution_permission": False,
    }
