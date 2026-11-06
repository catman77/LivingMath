"""Execute the existing closed relational AST through immutable symbolic primitives."""

from ..core import digest, canonical, strict_json
from ..symbolic.state import Atom, SymbolicState, apply


def evaluate(ast, state, record_ref=None, certify=False):
    trace = []
    states = {}

    def reference(value):
        key = digest(value.data())
        if certify:
            states[key] = strict_json(canonical(value.data()))
        return key

    def step(value, operator, args):
        output, _ = apply(value, operator, args)
        if certify:
            trace.append(
                {
                    "operator": operator,
                    "args": args,
                    "input_state_ref": reference(value),
                    "input_word_hash": value.word_hash,
                    "output_state_refs": [reference(s) for s in output],
                    "output_word_hashes": [s.word_hash for s in output],
                }
            )
        return output

    def walk(node, value, depth=0):
        if depth > 4:
            raise ValueError("MAX_COMPOSITION_DEPTH")
        kind = node["composition"]
        if kind == "all_observed_relations":
            decisions = [walk(a, value, depth + 1) for a in node["relations"]]
            result = all(decisions)
            if certify:
                trace.append(
                    {
                        "operation": "all_observed_relations_readout",
                        "values": decisions,
                        "value": result,
                    }
                )
            return result
        if kind == "iterate_on_inner_fragment":
            decisions = []
            current = value
            while len(current.atoms) > 1:
                decisions.append(walk(node["relation"], current, depth + 1))
                tail = step(current, "SPLIT", {"position": 1})[1]
                current = step(tail, "SPLIT", {"position": len(tail.atoms) - 1})[0]
            result = all(decisions)
            if certify:
                trace.append(
                    {
                        "operation": "inner_fragment_readout",
                        "values": decisions,
                        "value": result,
                    }
                )
            return result
        if kind != "aligned_token_equality":
            raise ValueError("UNSUPPORTED_RULE")
        offset = node["offset"]
        if len(value.atoms) <= 2 * offset + 1:
            if certify:
                trace.append(
                    {
                        "operation": "declared_base_case",
                        "record_ref": record_ref,
                        "value": True,
                    }
                )
            return True
        reverse = step(value, "REVERSE", {})[0]
        selected = []
        for carrier in (value, reverse):
            tail = step(carrier, "SPLIT", {"position": offset})[1]
            selected.append(step(tail, "SPLIT", {"position": 1})[0])
        result = (selected[0].tokens == selected[1].tokens) == node["expected_equal"]
        if certify:
            trace.append(
                {
                    "operation": "literal_token_equality",
                    "record_ref": record_ref,
                    "operand_state_refs": [reference(s) for s in selected],
                    "operands": [list(s.tokens) for s in selected],
                    "expected_equal": node["expected_equal"],
                    "value": result,
                }
            )
        return result

    if certify:
        reference(state)
    decision = walk(ast, state)
    return decision, trace, states


def value(ast, tokens):
    state = SymbolicState(tuple(Atom(t, ()) for t in tokens))
    return evaluate(ast, state)[0]
