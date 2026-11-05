"""Real SPLIT/CONCAT contextual counterexamples with source-bound operator lineage."""

import re
from collections import defaultdict
from ..core import digest
from ..symbolic.state import Atom, SymbolicState, apply


def record_state(record, tokens=None):
    text = record["source"]["text"]
    sha = record["source"]["sha256"]
    matches = list(re.finditer(r"\S+", text))
    names = record["tokens"] if tokens is None else tokens
    if len(names) != len(matches):
        raise ValueError("SOURCE_TOKEN_ARITY")
    atoms = tuple(
        Atom(
            t, ((sha, len(text[: m.start()].encode()), len(text[: m.end()].encode())),)
        )
        for t, m in zip(names, matches)
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


def step(state, op, args, trace, other=None):
    outputs, _ = apply(state, op, args, other)
    trace.append(
        {
            "operator": op,
            "args": args,
            "input_word_hash": state.word_hash,
            "input_lineage_digest": digest(state.data()),
            "other_lineage_digest": digest(other.data()) if other is not None else None,
            "output_word_hashes": [s.word_hash for s in outputs],
            "output_lineage_digests": [digest(s.data()) for s in outputs],
        }
    )
    return outputs


def observed_contexts(rows, policy, search, budget, transformations):
    from .features import encode

    labels = defaultdict(set)
    source_refs = defaultdict(list)
    for r in rows:
        key = r["encoded"]["signature"]
        labels[key].add(r["record"]["accepted"])
        source_refs[key].append(digest(r["record"]))
    output = []
    for row in rows[: search["max_contexts"]]:
        budget.check()
        record = row["record"]
        state = record_state(record)
        trace = []
        lines = record.get("lines", [])
        if len(lines) >= 3 and "SWAP_LINES_2_3" in transformations:
            a, b, c = len(lines[0]), len(lines[1]), len(lines[2])
            left, tail = step(state, "SPLIT", {"position": a}, trace)
            u, tail = step(tail, "SPLIT", {"position": b}, trace)
            v, right = step(tail, "SPLIT", {"position": c}, trace)
            joined = step(left, "CONCAT", {}, trace, v)[0]
            joined = step(joined, "CONCAT", {}, trace, u)[0]
            joined = step(joined, "CONCAT", {}, trace, right)[0]
            changed = [lines[0], lines[2], lines[1], *lines[3:]]
            target = {"tokens": [t for line in changed for t in line], "lines": changed}
            scope = (
                "line_in_quatrain"
                if any(s["kind"] == "quatrain" for s in record.get("segments", []))
                else "line_in_source_record"
            )
            expression = {
                "operations": ["SPLIT", "SPLIT", "SPLIT", "CONCAT", "CONCAT", "CONCAT"],
                "cuts": [a, b, c],
                "composition": "swap_two_observed_fragments",
            }
        else:
            k = len(state.atoms) // 2
            left, tail = step(state, "SPLIT", {"position": k}, trace)
            u, right = step(tail, "SPLIT", {"position": min(1, len(tail.atoms))}, trace)
            joined = step(left, "CONCAT", {}, trace, right)[0]
            target = {"tokens": list(joined.tokens), "lines": [list(joined.tokens)]}
            scope = "fragment_in_word"
            expression = {
                "operations": ["SPLIT", "SPLIT", "CONCAT"],
                "cuts": [k, min(1, len(tail.atoms))],
                "composition": "observed_fragment_deletion",
            }
        # Re-encode AFTER transformation; pre-encoded token IDs never transfer order.
        encoded = encode(target, policy.get("representation", "literal"))
        known = labels.get(encoded["signature"], set())
        status = (
            "UNKNOWN"
            if not known
            else (
                "CONTRADICTORY_CONTEXT"
                if len(known) > 1
                else (
                    "COMPATIBLE_ON_OBSERVED_K"
                    if next(iter(known)) == record["accepted"]
                    else "DISTINGUISHED"
                )
            )
        )
        output.append(
            {
                "relation": "R(u,v|observed_context)",
                "structural_scope": scope,
                "origin": "DERIVED_FROM_OPERATORS",
                "source_train_ref": digest(record),
                "source_sha256": record["source"]["sha256"],
                "source_segment_refs": [
                    s["id"]
                    for s in record.get("segments", [])
                    if s["kind"] in ("century", "quatrain", "line")
                ],
                "operator_ast": expression,
                "operator_trace": trace,
                "target_encoding_digest": encoded["signature"],
                "right_source_refs": source_refs.get(encoded["signature"], []),
                "left_membership": record["accepted"],
                "right_membership": next(iter(known)) if len(known) == 1 else None,
                "status": status,
                "claim_status": "EMPIRICAL",
                "scope": "known finite train contexts only; unknown is not false, no universal congruence",
            }
        )
    return output
