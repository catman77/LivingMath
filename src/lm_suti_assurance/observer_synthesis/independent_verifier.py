"""Independent source/AST/step checker; never imports the trace producer or grammar."""

from pathlib import Path
import hashlib, re
from ..core import digest, canonical, strict_json
from ..symbolic.state import Atom, SymbolicState, apply

VERSION = "operator-observer-independent-checker/1"


def checked(condition):
    if not condition:
        raise ValueError("INVALID_OPERATOR_WITNESS")


def valid_ast(ast, depth=0):
    if not isinstance(ast, dict) or depth > 4:
        return False
    kind = ast.get("composition")
    if kind == "aligned_token_equality":
        k = ast.get("offset")
        return (
            set(ast)
            == {
                "composition",
                "offset",
                "expected_equal",
                "base_max_tokens",
                "left_operations",
                "right_operations",
            }
            and type(k) is int
            and (0 <= k <= 3)
            and (type(ast.get("expected_equal")) is bool)
            and (ast.get("base_max_tokens") == 2 * k + 1)
            and (ast.get("left_operations") == ["SPLIT"])
            and (ast.get("right_operations") == ["REVERSE", "SPLIT"])
        )
    if kind == "iterate_on_inner_fragment":
        return (
            set(ast)
            == {
                "composition",
                "relation",
                "trim_left",
                "trim_right",
                "fragment_operations",
                "base_max_tokens",
            }
            and ast.get("trim_left") == ast.get("trim_right") == 1
            and (ast.get("base_max_tokens") == 1)
            and (ast.get("fragment_operations") == ["SPLIT", "SPLIT"])
            and valid_ast(ast.get("relation"), depth + 1)
        )
    if kind == "all_observed_relations":
        return (
            set(ast) == {"composition", "relations"}
            and isinstance(ast.get("relations"), list)
            and (1 <= len(ast["relations"]) <= 4)
            and all((valid_ast(a, depth + 1) for a in ast["relations"]))
        )
    return False


def verify(feature, samples):
    if feature.get("template_origin")=="ROLE_BRANCHING_PROMOTION":
        from .role_checker import verify as verify_role
        return verify_role(feature,samples)
    if feature.get("template_origin") == "COMPOSITIONAL_AST_PROMOTION":
        from .composition_checker import verify as verify_composition
        return verify_composition(feature,samples)
    if isinstance(feature.get("operator_ast"), dict) and feature["operator_ast"].get(
        "composition"
    ) in ("observed_word_equality", "observed_context_scan"):
        from .promotion_verifier import verify as verify_promoted

        return verify_promoted(feature, samples)

    def rejected(path, reason):
        return {
            "status": "REJECTED",
            "field_path": path,
            "reason": reason,
            "verifier_version": VERSION,
        }

    if feature.get("origin") == "BUILTIN":
        return {
            "status": "BUILTIN",
            "derived_claim_allowed": False,
            "verifier_version": VERSION,
        }
    if feature.get("origin") != "DERIVED_FROM_OPERATORS":
        return rejected("/origin", "No operator derivation supplied")
    ast = feature.get("operator_ast")
    if not valid_ast(ast):
        return rejected("/operator_ast", "Unsupported or altered existing relation AST")
    if feature.get("feature_id") != "derived_" + digest(ast)[:20]:
        return rejected("/feature_id", "AST does not match feature identity")
    grammar_path = Path(__file__).resolve().parent.parent / "symbolic/grammar.py"
    if (
        feature.get("source_code_binding_sha256")
        != hashlib.sha256(grammar_path.read_bytes()).hexdigest()
    ):
        return rejected(
            "/source_code_binding_sha256", "Unbound candidate grammar source"
        )
    alias = (
        "endpoint_equal"
        if ast["composition"] == "aligned_token_equality" and ast["offset"] == 0
        else None
    )
    if feature.get("semantic_alias_of") != alias:
        return rejected(
            "/semantic_alias_of", "Builtin semantic alias must remain explicit"
        )
    evidence = feature.get("construction_trace")
    if not isinstance(evidence, list) or not evidence or len(evidence) > 512:
        return rejected(
            "/construction_trace", "Finite actual source witnesses required"
        )
    indexed = {digest(s["record"]): s for s in samples}
    for index, witness in enumerate(evidence):
        path = f"/construction_trace/{index}"
        try:
            sample = indexed[witness["record_ref"]]
            record = sample["record"]
            source = record["source"]
            text = source["text"]
            checked(
                source["sha256"]
                == witness["source_sha256"]
                == hashlib.sha256(text.encode()).hexdigest()
            )
            checked(text.split() == record["tokens"])
            tokens = sample["encoded"]["tokens"]
            matches = list(re.finditer("\\S+", text))
            checked(len(matches) == len(tokens))
            atoms = tuple(
                (
                    Atom(
                        t,
                        (
                            (
                                source["sha256"],
                                len(text[: m.start()].encode()),
                                len(text[: m.end()].encode()),
                            ),
                        ),
                    )
                    for t, m in zip(tokens, matches)
                )
            )
            bounds = []
            position = 0
            for i, line in enumerate(record.get("lines") or [record["tokens"]]):
                bounds.extend(
                    [
                        (position, "record_start", str(i)),
                        (position + len(line), "record_end", str(i)),
                    ]
                )
                position += len(line)
            initial = SymbolicState(atoms, tuple(bounds))
            table = witness["states"]
            checked(table and all((digest(data) == ref for ref, data in table.items())))
            checked(witness["input_state_ref"] == digest(initial.data()))
            steps = iter(witness["operator_trace"])
            visited = set()

            def expect_state(state):
                ref = digest(state.data())
                visited.add(ref)
                checked(table[ref] == strict_json(canonical(state.data())))
                return ref

            def operator(state, name, args):
                row = next(steps)
                checked(row["operator"] == name and row["args"] == args)
                checked(row["input_state_ref"] == expect_state(state))
                checked(row["input_word_hash"] == state.word_hash)
                outputs, _ = apply(state, name, args)
                checked(row["output_word_hashes"] == [s.word_hash for s in outputs])
                checked(row["output_state_refs"] == [expect_state(s) for s in outputs])
                return outputs

            def readout(expected):
                checked(next(steps) == expected)

            def relation(node, carrier):
                kind = node["composition"]
                if kind == "all_observed_relations":
                    values = [relation(n, carrier) for n in node["relations"]]
                    answer = all(values)
                    readout(
                        {
                            "operation": "all_observed_relations_readout",
                            "values": values,
                            "value": answer,
                        }
                    )
                    return answer
                if kind == "iterate_on_inner_fragment":
                    values = []
                    current = carrier
                    while len(current.tokens) > 1:
                        values.append(relation(node["relation"], current))
                        tail = operator(current, "SPLIT", {"position": 1})[1]
                        current = operator(
                            tail, "SPLIT", {"position": len(tail.tokens) - 1}
                        )[0]
                    answer = all(values)
                    readout(
                        {
                            "operation": "inner_fragment_readout",
                            "values": values,
                            "value": answer,
                        }
                    )
                    return answer
                k = node["offset"]
                if len(carrier.tokens) <= 2 * k + 1:
                    readout(
                        {
                            "operation": "declared_base_case",
                            "record_ref": witness["record_ref"],
                            "value": True,
                        }
                    )
                    return True
                backward = operator(carrier, "REVERSE", {})[0]
                pieces = []
                for value in (carrier, backward):
                    suffix = operator(value, "SPLIT", {"position": k})[1]
                    pieces.append(operator(suffix, "SPLIT", {"position": 1})[0])
                answer = (carrier.tokens[k] == carrier.tokens[-k - 1]) == node[
                    "expected_equal"
                ]
                checked(
                    answer
                    == (
                        (pieces[0].tokens == pieces[1].tokens) == node["expected_equal"]
                    )
                )
                readout(
                    {
                        "operation": "literal_token_equality",
                        "record_ref": witness["record_ref"],
                        "operand_state_refs": [expect_state(s) for s in pieces],
                        "operands": [list(s.tokens) for s in pieces],
                        "expected_equal": node["expected_equal"],
                        "value": answer,
                    }
                )
                return answer

            expect_state(initial)
            checked(witness["decision"] == relation(ast, initial))
            checked(next(steps, None) is None)
            checked(visited == set(table))
        except (
            AssertionError,
            KeyError,
            TypeError,
            ValueError,
            StopIteration,
            IndexError,
        ):
            return rejected(
                path, "AST, output, source lineage or primitive step does not match"
            )
    return {
        "status": "CHECKED_FINITE_INSTANCE",
        "verified_witnesses": len(evidence),
        "operator_ast_digest": digest(ast),
        "verifier_version": VERSION,
        "verifier_digest": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "execution_permission": False,
    }
