"""Independent replay for closed composition certificates; never calls their producer."""

import hashlib, re
from pathlib import Path
from ..core import canonical, digest, strict_json
from ..symbolic.state import Atom, SymbolicState, apply

VERSION = "bounded-composition-independent-checker/1"


def need(condition: bool, reason: str = "INVALID_COMPOSITION_CERTIFICATE") -> None:
    if not condition:
        raise ValueError(reason)


def source_state(record: dict) -> SymbolicState:
    text = record["source"]["text"]
    sha = record["source"]["sha256"]
    need(
        hashlib.sha256(text.encode()).hexdigest() == sha
        and text.split() == record["tokens"],
        "SOURCE_MISMATCH",
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
        bounds.extend(
            [
                (offset, "record_start", str(i)),
                (offset + len(line), "record_end", str(i)),
            ]
        )
        offset += len(line)
    return SymbolicState(atoms, tuple(bounds))


def type_check(ast: dict, level: int = 1) -> tuple[int, int]:
    # Intentionally independent of the emitter's ast_metrics/type checker.
    need(isinstance(ast, dict) and level <= 8, "AST_DEPTH")
    kind = ast.get("composition")
    if kind == "aligned_token_equality":
        need(
            set(ast)
            == {
                "composition",
                "offset",
                "expected_equal",
                "base_max_tokens",
                "left_operations",
                "right_operations",
            },
            "AST_FIELDS",
        )
        need(
            type(ast["offset"]) is int
            and 0 <= ast["offset"] <= 3
            and type(ast["expected_equal"]) is bool,
            "AST_TYPES",
        )
        need(
            type(ast["base_max_tokens"]) is int
            and ast["base_max_tokens"] == 2 * ast["offset"] + 1,
            "AST_BASE",
        )
        need(
            ast["left_operations"] == ["SPLIT"]
            and ast["right_operations"] == ["REVERSE", "SPLIT"],
            "ILLEGAL_OPERATOR",
        )
        return 5, level + 1
    if kind == "all_observed_relations":
        need(
            set(ast) == {"composition", "relations"}
            and isinstance(ast["relations"], list)
            and 1 <= len(ast["relations"]) <= 4,
            "AST_FIELDS",
        )
        values = [type_check(a, level + 1) for a in ast["relations"]]
        return 1 + sum(n for n, _ in values), max(d for _, d in values)
    if kind == "iterate_on_inner_fragment":
        need(
            set(ast)
            == {
                "composition",
                "relation",
                "trim_left",
                "trim_right",
                "base_max_tokens",
                "fragment_operations",
            },
            "AST_FIELDS",
        )
        for key in ["trim_left", "trim_right", "base_max_tokens"]:
            need(type(ast[key]) is int and 0 <= ast[key] <= 8, "AST_TYPES")
        need(
            ast["trim_left"] + ast["trim_right"] > 0
            and ast["base_max_tokens"] >= ast["trim_left"] + ast["trim_right"] - 1,
            "NON_DECREASING_RECURSION",
        )
        need(ast["fragment_operations"] == ["SPLIT", "SPLIT"], "ILLEGAL_OPERATOR")
        nodes, depth = type_check(ast["relation"], level + 1)
        return nodes + 4, depth
    need(kind == "compare_fragments", "UNKNOWN_COMPOSITION")
    need(
        set(ast) == {"composition", "cut", "comparison", "expected_equal"}, "AST_FIELDS"
    )
    cut = ast["cut"]
    need(
        isinstance(cut, dict)
        and set(cut) == {"operator", "position"}
        and cut["operator"] == "SPLIT",
        "ILLEGAL_OPERATOR",
    )
    position = cut["position"]
    need(
        position == "MIDPOINT_EXACT_EVEN"
        or (type(position) is int and 0 <= position <= 8),
        "INVALID_POSITION",
    )
    need(
        ast["comparison"] == "literal_word_equality"
        and type(ast["expected_equal"]) is bool,
        "ILLEGAL_COMPARISON",
    )
    return 4, level + 1


def execute_checked(ast: dict, record: dict, witness: dict, domain: dict) -> bool:
    """Reconstruct Word states and independently consume every claimed step."""
    need(
        set(witness)
        == {
            "record_ref",
            "source_sha256",
            "input_state_ref",
            "operator_trace",
            "states",
            "decision",
        },
        "WITNESS_FIELDS",
    )
    need(witness["record_ref"] == digest(record), "RECORD_BINDING")
    initial = source_state(record)
    need(len(initial.tokens) <= domain["max_tokens"], "OUT_OF_SCOPE")
    table = witness["states"]
    steps = witness["operator_trace"]
    cursor = [0]
    seen = set()
    cache = {}
    recursions = [0]
    need(
        isinstance(table, dict) and isinstance(steps, list) and len(steps) <= 1024,
        "TRACE_SHAPE",
    )

    def state(word):
        if word not in cache:
            data = strict_json(canonical(word.data()))
            ref = digest(data)
            cache[word] = ref
            need(
                isinstance(table.get(ref), dict)
                and digest(table[ref]) == ref
                and canonical(table[ref]) == canonical(data),
                "STATE_OR_UTF8_SPAN_MISMATCH",
            )
            seen.add(ref)
        return cache[word]

    def consume(expected):
        need(cursor[0] < len(steps), "MISSING_STEP")
        row = steps[cursor[0]]
        cursor[0] += 1
        need(canonical(row) == canonical(expected), "STEP_REEXECUTION_MISMATCH")

    def operation(word, name, args):
        outputs, _ = apply(word, name, args)
        consume(
            {
                "operator": name,
                "args": args,
                "input_state_ref": state(word),
                "input_word_hash": word.word_hash,
                "output_state_refs": [state(w) for w in outputs],
                "output_word_hashes": [w.word_hash for w in outputs],
            }
        )
        return outputs

    def equality(a, b, expect):
        answer = (list(a.tokens) == list(b.tokens)) == expect
        consume(
            {
                "operation": "literal_word_equality",
                "operand_state_refs": [state(a), state(b)],
                "operands": [list(a.tokens), list(b.tokens)],
                "expected_equal": expect,
                "value": answer,
            }
        )
        return answer

    def run(node, word):
        code = node["composition"]
        if code == "aligned_token_equality":
            offset = node["offset"]
            if len(word.atoms) <= node["base_max_tokens"]:
                consume(
                    {
                        "operation": "declared_base_case",
                        "input_state_ref": state(word),
                        "base_max_tokens": node["base_max_tokens"],
                        "value": True,
                    }
                )
                return True
            backwards = operation(word, "REVERSE", {})[0]
            a = operation(word, "SPLIT", {"position": offset})[1]
            left = operation(a, "SPLIT", {"position": 1})[0]
            b = operation(backwards, "SPLIT", {"position": offset})[1]
            right = operation(b, "SPLIT", {"position": 1})[0]
            return equality(left, right, node["expected_equal"])
        if code == "compare_fragments":
            n = len(word.atoms)
            coordinate = node["cut"]["position"]
            pos = (
                n // 2
                if coordinate == "MIDPOINT_EXACT_EVEN" and n % 2 == 0
                else None
                if coordinate == "MIDPOINT_EXACT_EVEN"
                else coordinate
            )
            consume(
                {
                    "operation": "structural_cut_coordinate",
                    "input_state_ref": state(word),
                    "coordinate": coordinate,
                    "resolved_position": pos,
                }
            )
            if pos is None:
                return False
            need(pos <= n, "OUT_OF_SCOPE")
            a, b = operation(word, "SPLIT", {"position": pos})
            return equality(a, b, node["expected_equal"])
        if code == "all_observed_relations":
            answers = []
            for child in node["relations"]:
                answers.append(run(child, word))
            answer = all(answers)
            consume(
                {"operation": "bounded_conjunction", "values": answers, "value": answer}
            )
            return answer
        at = word
        answers = []
        while len(at.atoms) > node["base_max_tokens"]:
            recursions[0] += 1
            need(recursions[0] <= domain["max_recursion_steps"], "RECURSION_BOUND")
            answer = run(node["relation"], at)
            answers.append(answer)
            if not answer:
                break
            old_size = len(at.atoms)
            rest = operation(at, "SPLIT", {"position": node["trim_left"]})[1]
            at = operation(
                rest, "SPLIT", {"position": len(rest.atoms) - node["trim_right"]}
            )[0]
            need(len(at.atoms) < old_size, "NON_DECREASING_RECURSION")
        answer = all(answers)
        consume(
            {
                "operation": "inner_fragment_readout",
                "input_state_ref": state(at),
                "values": answers,
                "stopping_measure": len(at.atoms),
                "value": answer,
            }
        )
        return answer

    need(witness["source_sha256"] == record["source"]["sha256"], "SOURCE_MISMATCH")
    need(witness["input_state_ref"] == state(initial), "SOURCE_STATE_MISMATCH")
    result = run(ast, initial)
    need(cursor[0] == len(steps) and set(table) == seen, "TRUNCATED_OR_EXTRA_TRACE")
    need(
        type(witness["decision"]) is bool and witness["decision"] == result,
        "DECISION_MISMATCH",
    )
    return result


def verify(feature: dict, samples: list[dict]) -> dict:
    path = "/operator_ast"
    try:
        if "digest" in feature:
            path = "/digest"
            need(
                feature["digest"]
                == digest({k: v for k, v in feature.items() if k != "digest"}),
                "CERTIFICATE_DIGEST_MISMATCH",
            )
        pending = [feature]
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                need(
                    not set(value)
                    & {
                        "heldout_labels",
                        "test_labels",
                        "query_labels",
                        "hidden_labels",
                        "accepted",
                    },
                    "HELDOUT_LABEL_LEAKAGE",
                )
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)
        allowed = {
            "feature_id",
            "feature_version",
            "semantic_type",
            "origin",
            "operator_ast",
            "operator_ast_digest",
            "operator_bindings",
            "required_observers",
            "parent_feature_refs",
            "semantic_alias_of",
            "source_code_binding_sha256",
            "template_origin",
            "construction_trace",
            "candidate_provenance",
            "train_digest",
            "train_only_witness_refs",
            "witness_set_digest",
            "claim_status",
            "derived_claim_allowed",
            "known_invariance_scope",
            "execution_verified",
            "verifier_result",
            "digest",
            "role",
            "novelty",
        }
        path = "/origin"
        need(
            set(feature) <= allowed and feature["origin"] == "DERIVED_FROM_OPERATORS",
            "ORIGIN_OR_FIELDS",
        )
        need(
            feature["semantic_type"] == "bounded_operator_composition"
            and feature["role"] == "PREDICTIVE"
            and type(feature["execution_verified"]) is bool,
            "CERTIFICATE_TYPES",
        )
        need(
            feature["feature_version"] == "2"
            and feature["template_origin"] == "COMPOSITIONAL_AST_PROMOTION",
            "CERTIFICATE_VERSION",
        )
        path = "/operator_ast"
        ast = feature["operator_ast"]
        nodes, depth = type_check(ast)
        need(feature["operator_ast_digest"] == digest(ast), "AST_DIGEST")
        domain = feature["known_invariance_scope"]
        path = "/known_invariance_scope"
        limits = {
            "max_tokens": 8,
            "max_ast_nodes": 32,
            "max_ast_depth": 8,
            "max_recursion_steps": 8,
        }
        need(
            set(domain)
            == set(limits)
            | {"representation", "normalization", "alphabet", "universal_invariant"},
            "SCOPE_FIELDS",
        )
        for k, cap in limits.items():
            need(type(domain[k]) is int and 1 <= domain[k] <= cap, "SCOPE_BOUNDS")
        need(
            nodes <= domain["max_ast_nodes"] and depth <= domain["max_ast_depth"],
            "AST_SCOPE",
        )
        need(
            domain["representation"] == "literal"
            and domain["normalization"] == "none"
            and domain["alphabet"] == "literal_atoms_with_global_bijective_renaming",
            "SOURCE_REPRESENTATION",
        )
        need(
            domain["universal_invariant"] is False
            and feature["claim_status"] == "CHECKED_FINITE_INSTANCE",
            "FALSE_UNIVERSAL_CLAIM",
        )
        need(
            feature["required_observers"] == []
            and feature["derived_claim_allowed"] is True,
            "UNDECLARED_BUILTIN",
        )
        package = Path(__file__).resolve().parent.parent
        state_sha = hashlib.sha256(
            (package / "symbolic/state.py").read_bytes()
        ).hexdigest()
        evaluator_sha = hashlib.sha256(
            (Path(__file__).with_name("composition_ast.py")).read_bytes()
        ).hexdigest()
        path = "/operator_bindings"
        need(
            feature["operator_bindings"]
            == {"state_sha256": state_sha, "evaluator_sha256": evaluator_sha},
            "OPERATOR_BINDING_MISMATCH",
        )
        need(
            feature["source_code_binding_sha256"] == evaluator_sha, "EVALUATOR_BINDING"
        )
        need(
            feature["feature_id"]
            == "derived_"
            + digest(
                {
                    "ast": ast,
                    "domain": domain,
                    "operator_bindings": feature["operator_bindings"],
                }
            )[:20],
            "FEATURE_IDENTITY",
        )
        expected_parents = {"operator:SPLIT", "primitive:literal_word_equality"}
        if ast["composition"] != "compare_fragments":
            expected_parents.add("operator:REVERSE")
        need(
            set(feature["parent_feature_refs"]) == expected_parents,
            "DEPENDENCY_BINDING",
        )
        alias = (
            "endpoint_equal"
            if ast["composition"] == "aligned_token_equality" and ast["offset"] == 0
            else None
        )
        need(feature["semantic_alias_of"] == alias, "SEMANTIC_ALIAS")
        records = sorted([s["record"] for s in samples], key=digest)
        refs = [digest(r) for r in records]
        path = "/train_digest"
        need(0 < len(records) <= 256 and len(set(refs)) == len(refs), "TRAIN_COVERAGE")
        need(
            feature["train_digest"] == digest(records)
            and feature["train_only_witness_refs"] == refs,
            "TRAIN_BINDING",
        )
        need(
            all(s["encoded"]["tokens"] == s["record"]["tokens"] for s in samples),
            "SOURCE_REPRESENTATION",
        )
        proof = feature["candidate_provenance"]
        need(
            proof["ast_digest"] == digest(ast)
            and proof["train_digest"] == digest(records),
            "CANDIDATE_BINDING",
        )
        need(proof["route"] in ["derivation_trace", "source_run_id"], "CANDIDATE_ROUTE")
        common = {"route", "origin", "ast_digest", "train_digest"}
        additional = (
            {"generator", "generator_source_sha256"}
            if proof["route"] == "derivation_trace"
            else {
                "source_run_id",
                "source_input_digest",
                "source_result_digest",
                "source_kernel_binding",
                "source_ast_digest",
                "source_train_digest",
                "train_semantic_digest",
            }
        )
        need(set(proof) == common | additional, "CANDIDATE_PROVENANCE_FIELDS")

        need(
            proof["origin"]
            == (
                "AUTO_DISCOVERED"
                if proof["route"] == "derivation_trace"
                else "SOURCE_SUPPLIED"
            ),
            "CANDIDATE_ORIGIN",
        )
        if proof["route"] == "derivation_trace":
            generators = {
                "symbolic.grammar.relational_candidates": hashlib.sha256(
                    (package / "symbolic/grammar.py").read_bytes()
                ).hexdigest(),
                "bounded_structural_cut_x_literal_word_comparison": hashlib.sha256(
                    Path(__file__).with_name("compositional.py").read_bytes()
                ).hexdigest(),
            }
            need(
                proof["generator"] in generators
                and proof["generator_source_sha256"] == generators[proof["generator"]],
                "GENERATOR_BINDING",
            )
        if proof["route"] == "source_run_id":
            source_binding = digest(
                {
                    name: hashlib.sha256(
                        (package / "symbolic" / name).read_bytes()
                    ).hexdigest()
                    for name in (
                        "state.py",
                        "observers.py",
                        "search.py",
                        "grammar.py",
                        "kernel.py",
                        "contracts.py",
                    )
                }
            )
            need(
                proof["source_kernel_binding"] == source_binding,
                "SOURCE_KERNEL_BINDING",
            )
            need(proof["source_ast_digest"] == digest(ast), "SOURCE_AST_MISMATCH")
            semantics = sorted(
                [{"tokens": r["tokens"], "accepted": r["accepted"]} for r in records],
                key=digest,
            )
            need(
                proof["train_semantic_digest"] == digest(semantics),
                "SOURCE_TRAIN_MISMATCH",
            )
            for key in [
                "source_run_id",
                "source_input_digest",
                "source_result_digest",
                "source_kernel_binding",
                "source_train_digest",
            ]:
                need(
                    isinstance(proof[key], str)
                    and bool(re.fullmatch("[0-9a-f]{64}", proof[key])),
                    "SOURCE_BINDING",
                )

        witnesses = feature["construction_trace"]
        path = "/construction_trace"
        need(
            isinstance(witnesses, list) and len(witnesses) == len(records),
            "MISSING_TRAIN_WITNESS",
        )
        need(feature["witness_set_digest"] == digest(witnesses), "WITNESS_DIGEST")
        for i, (r, w) in enumerate(zip(records, witnesses)):
            path = f"/construction_trace/{i}/operator_trace"
            need(w["record_ref"] == refs[i], "TRAIN_WITNESS_ORDER")
            decision = execute_checked(ast, r, w, domain)
            need(decision == r["accepted"], "TRAIN_INCOMPATIBLE")
        result = {
            "status": "CHECKED_INSTANCE",
            "verified_witnesses": len(records),
            "training_compatibility": True,
            "ast_digest": digest(ast),
            "verifier_version": VERSION,
            "verifier_digest": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "universal_invariant": False,
            "execution_permission": False,
        }
        path = "/verifier_result"
        if "verifier_result" in feature:
            need(
                canonical(feature["verifier_result"]) == canonical(result),
                "FORGED_VERIFIER_RESULT",
            )
        return result
    except (ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
        return {
            "status": "REJECTED",
            "field_path": path,
            "reason": str(exc) or "INVALID_COMPOSITION_CERTIFICATE",
            "verifier_version": VERSION,
            "execution_permission": False,
        }
