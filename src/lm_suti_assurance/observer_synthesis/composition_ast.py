"""Closed existing relational ASTs, bounded structural cuts and actual Word steps.

No grammar/language labels, source paths, callbacks or executable client code.
"""

from ..core import canonical, digest, strict_json
from ..symbolic.state import SymbolicState, apply

DEFAULTS = {
    "mode": "literal_context_only",
    "candidate_sources": ["derivation_trace", "source_run_id"],
    "max_ast_nodes": 32,
    "max_ast_depth": 8,
    "max_recursion_steps": 8,
    "max_tokens": 8,
    "max_train_witnesses": 256,
    "max_runtime_ms": 4000,
    "require_independent_checker": True,
}


class DomainLimit(ValueError):
    """The partial observer has no decision at this input/bound."""


def settings(policy: dict | None = None) -> dict:
    return {**DEFAULTS, **(policy or {})}


def ast_metrics(ast: dict, depth: int = 1) -> tuple[int, int]:
    """Type/termination check for the four fixed constructors, not a DSL parser."""
    if not isinstance(ast, dict) or depth > 8:
        raise ValueError("INVALID_TYPED_AST")
    kind = ast.get("composition")
    if kind == "aligned_token_equality":
        if not (
            set(ast)
            == {
                "composition",
                "offset",
                "expected_equal",
                "base_max_tokens",
                "left_operations",
                "right_operations",
            }
            and type(ast["offset"]) is int
            and 0 <= ast["offset"] <= 3
            and type(ast["expected_equal"]) is bool
            and type(ast["base_max_tokens"]) is int
            and ast["base_max_tokens"] == 2 * ast["offset"] + 1
            and ast["left_operations"] == ["SPLIT"]
            and ast["right_operations"] == ["REVERSE", "SPLIT"]
        ):
            raise ValueError("INVALID_TYPED_AST")
        return 5, depth + 1
    if kind == "all_observed_relations":
        if (
            set(ast) != {"composition", "relations"}
            or not isinstance(ast["relations"], list)
            or not 1 <= len(ast["relations"]) <= 4
        ):
            raise ValueError("INVALID_TYPED_AST")
        parts = [ast_metrics(a, depth + 1) for a in ast["relations"]]
        return 1 + sum(n for n, _ in parts), max(d for _, d in parts)
    if kind == "iterate_on_inner_fragment":
        if not (
            set(ast)
            == {
                "composition",
                "relation",
                "trim_left",
                "trim_right",
                "fragment_operations",
                "base_max_tokens",
            }
            and all(
                type(ast[k]) is int and 0 <= ast[k] <= 8
                for k in ["trim_left", "trim_right", "base_max_tokens"]
            )
            and ast["trim_left"] + ast["trim_right"] > 0
            and ast["base_max_tokens"] >= ast["trim_left"] + ast["trim_right"] - 1
            and ast["fragment_operations"] == ["SPLIT", "SPLIT"]
        ):
            raise ValueError("NON_DECREASING_OR_INVALID_RECURSION")
        n, d = ast_metrics(ast["relation"], depth + 1)
        return n + 4, d
    if kind == "compare_fragments":
        cut = ast.get("cut")
        if not (
            set(ast) == {"composition", "cut", "comparison", "expected_equal"}
            and isinstance(cut, dict)
            and set(cut) == {"operator", "position"}
            and cut["operator"] == "SPLIT"
            and (
                cut["position"] == "MIDPOINT_EXACT_EVEN"
                or (type(cut["position"]) is int and 0 <= cut["position"] <= 8)
            )
            and ast["comparison"] == "literal_word_equality"
            and type(ast["expected_equal"]) is bool
        ):
            raise ValueError("INVALID_FRAGMENT_COMPARISON")
        return 4, depth + 1
    raise ValueError("UNKNOWN_COMPOSITION")


def declared_domain(policy: dict | None) -> dict:
    p = settings(policy)
    return {
        k: p[k]
        for k in ["max_tokens", "max_ast_nodes", "max_ast_depth", "max_recursion_steps"]
    } | {
        "representation": "literal",
        "normalization": "none",
        "alphabet": "literal_atoms_with_global_bijective_renaming",
        "universal_invariant": False,
    }


def execute(
    ast: dict,
    state: SymbolicState,
    domain: dict,
    record_ref: str | None = None,
    certify: bool = False,
    budget=None,
) -> tuple[bool, list, dict]:
    """Execute only existing Word operations, preserving all source lineage."""
    nodes, depth = ast_metrics(ast)
    if nodes > domain["max_ast_nodes"] or depth > domain["max_ast_depth"]:
        raise DomainLimit("AST_SCOPE_EXCEEDED")
    if len(state.tokens) > domain["max_tokens"]:
        raise DomainLimit("OUT_OF_DECLARED_SCOPE")
    trace, states, references = [], {}, {}
    recursion = [0]

    def ref(word):
        if word not in references:
            data = word.data()
            references[word] = digest(data)
            if certify:
                states[references[word]] = strict_json(canonical(data))
        return references[word]

    def emit(row):
        if certify:
            trace.append(row)

    def op(word, name, args):
        if budget:
            budget.check()
        output, _ = apply(word, name, args)
        if certify:
            emit(
                {
                    "operator": name,
                    "args": args,
                    "input_state_ref": ref(word),
                    "input_word_hash": word.word_hash,
                    "output_state_refs": [ref(w) for w in output],
                    "output_word_hashes": [w.word_hash for w in output],
                }
            )
        return output

    def equal(left, right, expected):
        result = (left.tokens == right.tokens) == expected
        if certify:
            emit(
                {
                    "operation": "literal_word_equality",
                    "operand_state_refs": [ref(left), ref(right)],
                    "operands": [list(left.tokens), list(right.tokens)],
                    "expected_equal": expected,
                    "value": result,
                }
            )
        return result

    def walk(node, word):
        if budget:
            budget.check()
        kind = node["composition"]
        if kind == "aligned_token_equality":
            k = node["offset"]
            if len(word.tokens) <= node["base_max_tokens"]:
                emit(
                    {
                        "operation": "declared_base_case",
                        "input_state_ref": ref(word),
                        "base_max_tokens": node["base_max_tokens"],
                        "value": True,
                    }
                )
                return True
            backward = op(word, "REVERSE", {})[0]
            selected = []
            for carrier in [word, backward]:
                suffix = op(carrier, "SPLIT", {"position": k})[1]
                selected.append(op(suffix, "SPLIT", {"position": 1})[0])
            return equal(*selected, node["expected_equal"])
        if kind == "compare_fragments":
            coordinate = node["cut"]["position"]
            n = len(word.tokens)
            position = (
                (None if n % 2 else n // 2)
                if coordinate == "MIDPOINT_EXACT_EVEN"
                else coordinate
            )
            emit(
                {
                    "operation": "structural_cut_coordinate",
                    "input_state_ref": ref(word),
                    "coordinate": coordinate,
                    "resolved_position": position,
                }
            )
            if position is None:
                return False
            if position > n:
                raise DomainLimit("CUT_OUT_OF_SCOPE")
            left, right = op(word, "SPLIT", {"position": position})
            return equal(left, right, node["expected_equal"])
        if kind == "all_observed_relations":
            decisions = [walk(part, word) for part in node["relations"]]
            result = all(decisions)
            emit(
                {
                    "operation": "bounded_conjunction",
                    "values": decisions,
                    "value": result,
                }
            )
            return result
        current, decisions = word, []
        while len(current.tokens) > node["base_max_tokens"]:
            recursion[0] += 1
            if recursion[0] > domain["max_recursion_steps"]:
                raise DomainLimit("MAX_RECURSION_STEPS")
            decision = walk(node["relation"], current)
            decisions.append(decision)
            if not decision:
                break
            previous = len(current.tokens)
            tail = op(current, "SPLIT", {"position": node["trim_left"]})[1]
            current = op(
                tail, "SPLIT", {"position": len(tail.tokens) - node["trim_right"]}
            )[0]
            if len(current.tokens) >= previous:
                raise ValueError("NON_DECREASING_RECURSION")
        result = all(decisions)
        emit(
            {
                "operation": "inner_fragment_readout",
                "input_state_ref": ref(current),
                "values": decisions,
                "stopping_measure": len(current.tokens),
                "value": result,
            }
        )
        return result

    ref(state)
    result = walk(ast, state)
    return result, trace, states


def value(ast: dict, tokens: list | tuple, domain: dict) -> bool | None:
    from ..symbolic.state import Atom

    try:
        return execute(ast, SymbolicState(tuple(Atom(t, ()) for t in tokens)), domain)[
            0
        ]
    except DomainLimit:
        return None
