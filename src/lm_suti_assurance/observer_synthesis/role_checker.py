"""Independent finite role checker. Never imports the program solver or generator."""

import hashlib, re
from pathlib import Path
from ..core import digest, canonical, strict_json
from ..symbolic.state import Atom, SymbolicState, apply

VERSION = "role-branch-independent-checker/1"
PARENTS = [
    "operator:SPLIT",
    "operator:CONCAT",
    "primitive:ATOM_ROLE",
    "primitive:FINITE_EXISTS",
    "primitive:BRANCH_AND",
    "primitive:EPS_BASE",
]


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def exact(a, b):
    return canonical(a) == canonical(b)


def validate_program(p, d):
    need(
        isinstance(p, dict)
        and set(p)
        == {
            "composition",
            "base",
            "roles",
            "sequence",
            "quantifier",
            "combine",
            "reconstruction",
        },
        "PROGRAM_FIELDS",
    )
    need(
        p["composition"] == "finite_role_branching"
        and p["base"] in ["EPS", "NONE"]
        and p["quantifier"] == "FINITE_EXISTS"
        and p["combine"] == "BRANCH_AND"
        and p["reconstruction"] == "CONCAT",
        "PROGRAM_CONSTRUCTORS",
    )
    roles = p["roles"]
    seq = p["sequence"]
    need(
        isinstance(roles, dict)
        and set(roles) == {"OPEN", "CLOSE"}
        and all(type(x) is str and 0 < len(x) <= 1024 for x in roles.values())
        and roles["OPEN"] != roles["CLOSE"],
        "ROLE_BINDING",
    )
    need(isinstance(seq, list) and 2 <= len(seq) <= 4, "RULE_ARITY")
    seen = []
    count = 0
    for item in seq:
        need(isinstance(item, dict), "INSTRUCTION")
        if item.get("op") == "ATOM_ROLE":
            need(set(item) == {"op", "role"} and item["role"] in roles, "ROLE_TEST")
            seen.append(item["role"])
        else:
            need(
                set(item) == {"op", "branch"}
                and item["op"] == "RECURSE"
                and item["branch"] == "b" + str(count),
                "BRANCH_ID",
            )
            count += 1
    need(seen == ["OPEN", "CLOSE"] and count <= 2, "DECREASING_RULE")
    caps = {
        "max_tokens": 12,
        "max_cells": 91,
        "max_split_trials": 512,
        "max_depth": 8,
        "max_ast_nodes": 32,
        "max_ast_depth": 8,
    }
    need(
        isinstance(d, dict)
        and set(d)
        == set(caps)
        | {
            "representation",
            "role_semantics",
            "renaming_contract",
            "NF_INVARIANT",
            "universal_invariant",
        },
        "SCOPE_FIELDS",
    )
    need(
        all(type(d[k]) is int and 1 <= d[k] <= cap for k, cap in caps.items()),
        "SCOPE_LIMIT",
    )
    need(
        d["representation"] == "literal"
        and d["role_semantics"] == "LITERAL_ROLE_SENSITIVE"
        and d["renaming_contract"] == "ATOMS_AND_ROLES_TOGETHER"
        and d["NF_INVARIANT"] is False
        and d["universal_invariant"] is False,
        "FALSE_INVARIANCE_CLAIM",
    )
    need(7 + len(seq) <= d["max_ast_nodes"] and 3 <= d["max_ast_depth"], "AST_BOUND")
    return count


def source(record):
    s = record["source"]
    text = s["text"]
    raw = text.encode()
    need(
        hashlib.sha256(raw).hexdigest() == s["sha256"]
        and text.split() == record["tokens"],
        "SOURCE_BYTES",
    )
    matches = list(re.finditer(r"\S+", text))
    atoms = tuple(
        Atom(
            t,
            (
                (
                    s["sha256"],
                    len(text[: m.start()].encode()),
                    len(text[: m.end()].encode()),
                ),
            ),
        )
        for t, m in zip(record["tokens"], matches)
    )
    need(len(atoms) == len(record["tokens"]), "TOKEN_ARITY")
    bounds = []
    pos = 0
    for i, line in enumerate(record.get("lines") or [record["tokens"]]):
        bounds.extend(
            [(pos, "record_start", str(i)), (pos + len(line), "record_end", str(i))]
        )
        pos += len(line)
    return SymbolicState(atoms, tuple(bounds))


def verify_proof(program, record, scope, proof):
    path = "/proof"
    try:
        count = validate_program(program, scope)
        initial = source(record)
        tokens = list(initial.tokens)
        n = len(tokens)
        common = {
            "schema",
            "program_digest",
            "record_ref",
            "source_sha256",
            "scope_digest",
            "input_state",
            "status",
        }
        need(
            isinstance(proof, dict) and proof["schema"] == "finite-role-certificate/1",
            "PROOF_FORMAT",
        )
        need(
            proof["program_digest"] == digest(program)
            and proof["record_ref"] == digest(record)
            and proof["source_sha256"] == record["source"]["sha256"]
            and proof["scope_digest"] == digest(scope),
            "PROOF_BINDING",
        )
        need(exact(proof["input_state"], initial.data()), "SOURCE_SPANS")
        if proof["status"] == "UNKNOWN":
            need(set(proof) == common | {"reason"}, "UNKNOWN_FIELDS")
            return {
                "status": "UNKNOWN",
                "reason": proof["reason"],
                "execution_permission": False,
                "verifier_version": VERSION,
            }
        need(
            set(proof) == common | {"decision", "cells", "tree", "states", "work"}
            and proof["status"] == "DECIDED"
            and type(proof["decision"]) is bool,
            "PROOF_FIELDS",
        )
        need(
            n <= scope["max_tokens"] and (n + 1) * (n + 2) // 2 <= scope["max_cells"],
            "OUT_OF_SCOPE",
        )
        need(count == 0 or n // 2 <= scope["max_depth"], "DEPTH_BOUND")
        rows = proof["cells"]
        need(
            isinstance(rows, list) and len(rows) == (n + 1) * (n + 2) // 2,
            "NEGATIVE_COVERAGE",
        )
        table = {}
        index = 0
        trials = 0
        for length in range(n + 1):
            for i in range(n - length + 1):
                j = i + length
                row = rows[index]
                path = "/proof/cells/" + str(index)
                index += 1
                need(
                    isinstance(row, dict)
                    and set(row) == {"range", "value", "allocation"}
                    and exact(row["range"], [i, j])
                    and type(row["value"]) is bool,
                    "INTERVAL_ROW",
                )
                # Independent exhaustive equation over all finite allocations; not a solver call.
                options = []
                if length >= 2:
                    if count == 0 and length == 2:
                        options = [[]]
                    elif count == 1:
                        options = [[length - 2]]
                    elif count == 2:
                        options = [[k, length - 2 - k] for k in range(length - 1)]
                first = [] if length == 0 and program["base"] == "EPS" else None
                for allocation in options:
                    trials += 1
                    need(trials <= scope["max_split_trials"], "SPLIT_BUDGET")
                    cursor = i
                    b = 0
                    valid = True
                    for instruction in program["sequence"]:
                        if instruction["op"] == "ATOM_ROLE":
                            match = (
                                tokens[cursor] == program["roles"][instruction["role"]]
                            )
                            valid = valid and match
                            cursor += 1
                        else:
                            end = cursor + allocation[b]
                            need(end - cursor < length, "STRICT_DECREASE")
                            child = table[cursor, end]["value"]
                            valid = valid and child
                            cursor = end
                            b += 1
                    need(cursor == j, "PARTITION_COVERAGE")
                    if valid and first is None:
                        first = allocation
                need(
                    row["value"] == (first is not None)
                    and exact(row["allocation"], first),
                    "INTERVAL_EQUATION",
                )
                table[i, j] = row
        need(
            exact(proof["work"], {"cells": len(rows), "split_trials": trials}),
            "WORK_COUNTS",
        )
        need(proof["decision"] == table[0, n]["value"], "ROOT_VALUE")
        path = "/proof/tree"
        if not proof["decision"]:
            need(proof["tree"] is None and proof["states"] == {}, "NEGATIVE_STRUCTURE")
        else:
            states = proof["states"]
            need(
                isinstance(states, dict)
                and all(digest(v) == k for k, v in states.items()),
                "STATE_HASH",
            )
            visited = set()

            def ref(s):
                key = digest(s.data())
                need(key in states and exact(states[key], s.data()), "STATE_CONTENT")
                visited.add(key)
                return key

            def walk(node, i, j, state, level):
                need(level <= scope["max_depth"], "DEPTH_BOUND")
                need(
                    isinstance(node, dict)
                    and set(node)
                    == {
                        "range",
                        "tokens",
                        "input_state_ref",
                        "kind",
                        "roles",
                        "children",
                        "trace",
                        "allocation",
                        "measure",
                        "reconstructed_tokens",
                    },
                    "NODE_FIELDS",
                )
                need(
                    exact(node["range"], [i, j])
                    and exact(node["tokens"], list(state.tokens))
                    and node["input_state_ref"] == ref(state),
                    "NODE_SOURCE",
                )
                need(
                    exact(node["allocation"], table[i, j]["allocation"])
                    and exact(node["reconstructed_tokens"], list(state.tokens)),
                    "NODE_RECONSTRUCTION",
                )
                if i == j:
                    need(
                        node["kind"] == "EPS_BASE"
                        and program["base"] == "EPS"
                        and node["roles"] == node["children"] == node["trace"] == []
                        and exact(node["measure"], {"parent": 0, "children": []}),
                        "EPS_BASE",
                    )
                    return
                need(
                    node["kind"] == "RULE" and len(node["children"]) == count,
                    "MISSING_BRANCH",
                )
                trace = iter(node["trace"])
                roles = []
                children = []
                pieces = []
                remain = state
                cursor = i
                b = 0

                def operation(carrier, name, args, other=None):
                    entry = next(trace)
                    output, _ = apply(carrier, name, args, other)
                    expected = {
                        "operator": name,
                        "args": args,
                        "input_state_ref": ref(carrier),
                        "other_state_ref": ref(other) if other is not None else None,
                        "output_state_refs": [ref(x) for x in output],
                        "input_word_hash": carrier.word_hash,
                        "output_word_hashes": [x.word_hash for x in output],
                    }
                    need(exact(entry, expected), "PRIMITIVE_STEP")
                    return output

                for instruction in program["sequence"]:
                    size = (
                        1 if instruction["op"] == "ATOM_ROLE" else node["allocation"][b]
                    )
                    piece, remain = operation(remain, "SPLIT", {"position": size})
                    pieces.append(piece)
                    if instruction["op"] == "ATOM_ROLE":
                        role = instruction["role"]
                        need(piece.tokens == (program["roles"][role],), "ATOM_ROLE")
                        roles.append(
                            {
                                "role": role,
                                "position": cursor,
                                "token": piece.tokens[0],
                                "state_ref": ref(piece),
                            }
                        )
                    else:
                        need(size < j - i, "STRICT_DECREASE")
                        walk(
                            node["children"][b], cursor, cursor + size, piece, level + 1
                        )
                        children.append(size)
                        b += 1
                    cursor += size
                reconstructed = pieces[0]
                for piece in pieces[1:]:
                    reconstructed = operation(reconstructed, "CONCAT", {}, piece)[0]
                need(
                    exact(node["roles"], roles)
                    and exact(node["measure"], {"parent": j - i, "children": children})
                    and not remain.tokens
                    and reconstructed.tokens == state.tokens,
                    "CONCAT_LITERAL_RECONSTRUCTION",
                )
                need(next(trace, None) is None, "EXTRA_PRIMITIVE")

            walk(proof["tree"], 0, n, initial, 0)
            need(set(states) == visited, "STATE_COVERAGE")
        return {
            "status": "CHECKED_INSTANCE",
            "decision": proof["decision"],
            "program_digest": digest(program),
            "proof_digest": digest(proof),
            "verifier_version": VERSION,
            "execution_permission": False,
            "universal_invariant": False,
        }
    except (
        ValueError,
        KeyError,
        TypeError,
        IndexError,
        StopIteration,
        UnicodeError,
    ) as exc:
        return {
            "status": "REJECTED",
            "field_path": path,
            "reason": str(exc),
            "verifier_version": VERSION,
            "execution_permission": False,
        }


def verify(feature, samples):
    path = "/feature"
    try:
        base = {
            "feature_id",
            "feature_version",
            "semantic_type",
            "origin",
            "template_origin",
            "operator_ast",
            "operator_ast_digest",
            "operator_bindings",
            "source_code_binding_sha256",
            "candidate_provenance",
            "required_observers",
            "parent_feature_refs",
            "semantic_alias_of",
            "train_digest",
            "train_only_witness_refs",
            "known_invariance_scope",
            "claim_status",
            "derived_claim_allowed",
            "construction_trace",
            "witness_set_digest",
            "execution_verified",
            "role",
            "novelty",
        }
        need(set(feature) - {"verifier_result", "digest"} == base, "FEATURE_FIELDS")
        need(
            feature["feature_version"] == "3"
            and feature["semantic_type"] == "typed_role_language"
            and feature["origin"] == "DERIVED_FROM_OPERATORS"
            and feature["template_origin"] == "ROLE_BRANCHING_PROMOTION"
            and feature["claim_status"] == "CHECKED_FINITE_INSTANCE"
            and feature["derived_claim_allowed"] is True
            and type(feature["execution_verified"]) is bool,
            "ORIGIN_OR_CLAIM",
        )
        program = feature["operator_ast"]
        scope = feature["known_invariance_scope"]
        validate_program(program, scope)
        need(feature["operator_ast_digest"] == digest(program), "AST_DIGEST")
        package = Path(__file__).parent
        hashes = {
            "state_sha256": hashlib.sha256(
                (package.parent / "symbolic/state.py").read_bytes()
            ).hexdigest(),
            "evaluator_sha256": hashlib.sha256(
                (package / "role_ast.py").read_bytes()
            ).hexdigest(),
        }
        need(
            feature["operator_bindings"] == hashes
            and feature["source_code_binding_sha256"] == hashes["evaluator_sha256"],
            "OPERATOR_BINDING",
        )
        need(
            feature["feature_id"]
            == "derived_"
            + digest({"ast": program, "domain": scope, "operator_bindings": hashes})[
                :20
            ],
            "FEATURE_ID",
        )
        need(
            feature["required_observers"] == []
            and sorted(feature["parent_feature_refs"]) == sorted(PARENTS)
            and feature["semantic_alias_of"] is None
            and feature["role"] == "PREDICTIVE",
            "UNDECLARED_BUILTIN",
        )
        records = sorted([x["record"] for x in samples], key=digest)
        refs = [digest(r) for r in records]
        need(0 < len(records) <= 256 and len(set(refs)) == len(refs), "TRAIN_COVERAGE")
        need(
            all(x["encoded"]["tokens"] == x["record"]["tokens"] for x in samples),
            "REPRESENTATION",
        )
        need(
            feature["train_digest"] == digest(records)
            and feature["train_only_witness_refs"] == refs,
            "TRAIN_BINDING",
        )
        need(
            set(program["roles"].values()) <= {t for r in records for t in r["tokens"]},
            "UNSEEN_ROLE_ATOM",
        )
        expected = {
            "catalog": "roles_x_nullable_rule_shuffles/1",
            "route": "derivation_trace",
            "origin": "AUTO_DISCOVERED",
            "ast_digest": digest(program),
            "train_digest": digest(records),
            "generator_source_sha256": hashlib.sha256(
                (package / "role_promotion.py").read_bytes()
            ).hexdigest(),
        }
        need(exact(feature["candidate_provenance"], expected), "GENERATOR_PROVENANCE")
        proof = feature["construction_trace"]
        need(isinstance(proof, list) and len(proof) == len(records), "WITNESS_COVERAGE")
        need(feature["witness_set_digest"] == digest(proof), "WITNESS_DIGEST")
        for i, (w, r) in enumerate(zip(proof, records)):
            path = "/construction_trace/" + str(i)
            need(
                set(w) == {"record_ref", "proof"} and w["record_ref"] == digest(r),
                "WITNESS_REF",
            )
            result = verify_proof(program, r, scope, w["proof"])
            need(
                result["status"] == "CHECKED_INSTANCE"
                and type(r["accepted"]) is bool
                and result["decision"] == r["accepted"],
                "INDEPENDENT_TRAIN_EXECUTION: " + str(result),
            )
        if "digest" in feature:
            need(
                feature["digest"]
                == digest({k: v for k, v in feature.items() if k != "digest"}),
                "OUTER_DIGEST",
            )
        checked = {
            "status": "CHECKED_INSTANCE",
            "training_compatibility": True,
            "verified_witnesses": len(records),
            "ast_digest": digest(program),
            "verifier_version": VERSION,
            "verifier_digest": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "execution_permission": False,
            "universal_invariant": False,
        }
        if "verifier_result" in feature:
            need(exact(feature["verifier_result"], checked), "VERIFIER_RESULT")
        return checked
    except (ValueError, KeyError, TypeError, IndexError, UnicodeError) as exc:
        return {
            "status": "REJECTED",
            "field_path": path,
            "reason": str(exc),
            "verifier_version": VERSION,
            "execution_permission": False,
        }
