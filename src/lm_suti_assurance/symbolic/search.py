"""Bounded local word mutations with set-inclusion Pareto selection, not enumeration."""

from ..core import digest
from .state import apply, require
from .observers import witness_set


def search(request, history, roots, observer, clock_factory):
    budget = request["search"]
    clock = clock_factory(budget["seed"])
    operators = request["operators"]
    max_observations = budget.get("max_observations", 8192)
    max_total = budget.get("max_total_tokens", 131072)
    require(len(history.nodes) <= budget["max_nodes"], "INITIAL_NODE_LIMIT")
    total = sum(len(s.atoms) for s in history.states.values())
    require(total <= max_total, "INITIAL_TOKEN_LIMIT")
    observations = {
        ident: observer.observe(history.states[ident]) for ident in history.nodes
    }
    require(len(observations) <= max_observations, "INITIAL_OBSERVATION_LIMIT")
    seen = set().union(*(witness_set(o) for o in observations.values()))
    words = {s.word_hash: i for i, s in history.states.items()}
    current = roots[0]
    trace = []
    halt = "MAX_STEPS"
    attempts = 0
    for step in range(budget["max_steps"]):
        candidates = []
        stop = None
        for slot in range(budget["max_candidates_per_step"]):
            attempts += 1
            op = operators[clock.step() % len(operators)]
            state = history.states[current]
            n = len(state.atoms)
            args = {}
            parents = [current]
            other = None
            if op in ("SPLIT", "INSERT_CANCEL_PAIR"):
                args["position"] = clock.step() % (n + 1)
            if op == "INSERT_CANCEL_PAIR":
                args["kind"] = ("SP", "PS")[clock.step() % 2]
            if op in ("RENAME", "SUBSTITUTE"):
                tokens = sorted(set(state.tokens))
                mapping = {}
                if tokens:
                    if op == "RENAME":
                        if len(tokens) > 1:
                            mapping = {
                                t: tokens[(i + 1) % len(tokens)]
                                for i, t in enumerate(tokens)
                            }
                        elif request["algebra"]["kind"] == "SP":
                            mapping = {tokens[0]: "P" if tokens[0] == "S" else "S"}
                        else:
                            mapping = {tokens[0]: "opaque-" + digest(tokens[0])[:16]}
                    else:
                        mapping = {tokens[-1]: tokens[0]}
                args = {"mapping": mapping, "scope": "global"}
            if op == "CONCAT":
                parent = roots[clock.step() % len(roots)]
                parents.append(parent)
                other = history.states[parent]
            outputs, events = apply(state, op, args, other)
            if any(len(s.atoms) > budget["max_word_tokens"] for s in outputs):
                candidates.append(
                    {
                        "operator": op,
                        "parents": parents,
                        "args": args,
                        "status": "WORD_TOKEN_LIMIT",
                    }
                )
                continue
            count = len(outputs)
            if len(history.nodes) + count > budget["max_nodes"]:
                stop = "MAX_NODES"
                break
            if len(observations) + count > max_observations:
                stop = "MAX_OBSERVATIONS"
                break
            if total + sum(len(s.atoms) for s in outputs) > max_total:
                stop = "MAX_TOTAL_TOKENS"
                break
            ids = []
            novel = set()
            new_outputs = []
            for part, s in enumerate(outputs):
                if (
                    budget.get("history_identity", "word") == "word"
                    and s.word_hash in words
                ):
                    ids.append(words[s.word_hash])
                    continue
                ident = history.add(
                    s, parents, op, {**args, "output_part": part}, events
                )
                ids.append(ident)
                if ident in observations:
                    continue
                total += len(s.atoms)
                observation = observer.observe(s)
                observations[ident] = observation
                novel |= witness_set(observation) - seen
                words.setdefault(s.word_hash, ident)
                new_outputs.append(ident)
            candidates.append(
                {
                    "operator": op,
                    "parents": parents,
                    "args": args,
                    "outputs": ids,
                    "new_outputs": new_outputs,
                    "new_witnesses": sorted(novel),
                    "status": "GENERATED" if new_outputs else "DUPLICATE_WORD",
                }
            )
        usable = [i for i, c in enumerate(candidates) if c.get("new_outputs")]
        frontier = [
            i
            for i in usable
            if not any(
                set(candidates[i]["new_witnesses"])
                < set(candidates[j]["new_witnesses"])
                for j in usable
            )
        ]
        choices = usable if budget["strategy"] == "random_local" else frontier
        chosen = choices[clock.step() % len(choices)] if choices else None
        if chosen is not None:
            current = candidates[chosen]["new_outputs"][0]
        # All observed candidates become part of known witnesses, not just the winner.
        for candidate in candidates:
            seen.update(candidate.get("new_witnesses", []))
        trace.append(
            {
                "step": step,
                "input_node": parents[0] if candidates else current,
                "candidates": candidates,
                "pareto_indices": frontier,
                "selected_index": chosen,
                "current_node": current,
                "selection": (
                    "seeded_set_inclusion"
                    if budget["strategy"] != "random_local"
                    else "seeded_random_local"
                ),
            }
        )
        if stop:
            halt = stop
            break
    return {
        "ops_trace": trace,
        "structural_observations": [
            {"node_id": i, **o} for i, o in observations.items()
        ],
        "search_summary": {
            "steps": len(trace),
            "attempted_candidates": attempts,
            "halt_reason": halt,
            "nodes": len(history.nodes),
            "observations": len(observations),
            "total_stored_tokens": total,
            "unique_literal_words": len({s.word_hash for s in history.states.values()}),
            "witness_count": len(seen),
            "history_identity": budget.get("history_identity", "word"),
        },
        "final_node_id": current,
    }
