"""Bounded local word mutations with set-inclusion Pareto selection, not enumeration."""

import heapq

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
    stale_steps = 0
    stale_clocks = {}
    diagnostics = []
    window = max(8, min(32, len(operators) * 4))
    # Only already stored nodes enter this scheduler. A pair gets one forced
    # proposal, with the existing clock supplying its arguments. This is not
    # enumeration of parameter variants, words, trees, or possible programs.
    tried = {}
    waiting = []
    remaining = {op: 0 for op in operators}
    coverage = {
        op: dict(proposed=0, accepted=0, duplicate=0, forbidden=0, resource_limited=0)
        for op in operators
    }
    visits = {}
    fallback_count = 0
    pending = None

    def register(node):
        tried[node] = set()
        for op in operators:
            rank = digest([budget["seed"], op, node])
            heapq.heappush(waiting, (rank, op, node))
            remaining[op] += 1

    def next_frontier():
        # Each heap entry can be removed only once; the heap is bounded by
        # max_nodes * len(operators), independently of word/argument spaces.
        for _ in range(len(waiting)):
            rank, op, node = waiting[0]
            if op not in tried[node]:
                return {
                    "selected_node_id": node,
                    "selected_operator": op,
                    "rank_digest": rank,
                }
            heapq.heappop(waiting)
        return None

    def counters():
        return {
            "frontier_size": sum(remaining.values()),
            "frontier_unit": "untried stored-node/operator pairs",
            "untried_allowed_operators": [op for op in operators if remaining[op]],
            "candidate_attempts": attempts,
            "fallback_count": fallback_count,
            "history_identity": budget.get("history_identity", "word"),
            "global_exhaustion_proved": False,
        }

    for ident in history.nodes:
        register(ident)
    for step in range(budget["max_steps"]):
        forced = None
        if pending is not None:
            forced = pending["selected_operator"]
            before = current
            current = pending["selected_node_id"]
            fallback_count += 1
            diagnostics.append(
                {
                    "kind": "observed",
                    "status": "FRONTIER_FALLBACK",
                    "step": step,
                    **counters(),
                    **pending,
                    "previous_node_id": before,
                    "selected_node_history_ref": current,
                    "boundary": "One untried stored-node/operator proposal in an ordinary budgeted slot; no new operation or identity change.",
                }
            )
            pending = None
        input_node = current
        visits[current] = visits.get(current, 0) + 1
        candidates = []
        stop = None
        for slot in range(budget["max_candidates_per_step"]):
            attempts += 1
            op = operators[clock.step() % len(operators)]
            fallback_slot = forced is not None and slot == 0
            if fallback_slot:
                op = forced
            if op not in tried[current]:
                tried[current].add(op)
                remaining[op] -= 1
            coverage[op]["proposed"] += 1
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
            proposal = {"proposal": "frontier_fallback"} if fallback_slot else {}
            outputs, events = apply(state, op, args, other)
            if any(len(s.atoms) > budget["max_word_tokens"] for s in outputs):
                coverage[op]["forbidden"] += 1
                candidates.append(
                    {
                        **proposal,
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
            elif len(observations) + count > max_observations:
                stop = "MAX_OBSERVATIONS"
            elif total + sum(len(s.atoms) for s in outputs) > max_total:
                stop = "MAX_TOTAL_TOKENS"
            if stop:
                coverage[op]["resource_limited"] += 1
                candidates.append(
                    {
                        **proposal,
                        "operator": op,
                        "parents": parents,
                        "args": args,
                        "status": stop,
                    }
                )
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
                register(ident)
                total += len(s.atoms)
                observation = observer.observe(s)
                observations[ident] = observation
                novel |= witness_set(observation) - seen
                words.setdefault(s.word_hash, ident)
                new_outputs.append(ident)
            candidates.append(
                {
                    **proposal,
                    "operator": op,
                    "parents": parents,
                    "args": args,
                    "outputs": ids,
                    "new_outputs": new_outputs,
                    "new_witnesses": sorted(novel),
                    "status": "GENERATED" if new_outputs else "DUPLICATE_WORD",
                }
            )
            coverage[op]["accepted" if new_outputs else "duplicate"] += 1
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
                "input_node": input_node,
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
        grew = any(c.get("new_outputs") for c in candidates)
        if grew:
            stale_steps = 0
            stale_clocks.clear()
        else:
            stale_steps += 1
            clock_state = [getattr(clock, "a", None), getattr(clock, "b", None)]
            signature = (
                digest([current, clock_state]) if None not in clock_state else None
            )
            cycle = signature is not None and signature in stale_clocks
            if signature is not None:
                stale_clocks.setdefault(signature, step)
            if cycle or stale_steps >= window:
                start = step - stale_steps + 1
                actual = {}
                for entry in trace[start:]:
                    for c in entry["candidates"]:
                        actual.setdefault(digest(c), c)
                sampled = sorted({c["operator"] for c in actual.values()})
                reason = (
                    "repeated_local_clock_state"
                    if cycle
                    else "bounded_local_stagnation_window"
                )
                candidate = next_frontier()
                diagnostics.append(
                    {
                        "kind": "observed",
                        "status": "LOCAL_STAGNATION",
                        "halt_reason": "NO_NOVEL_CANDIDATES",
                        **counters(),
                        "fallback_reason": reason,
                        "selected_frontier": candidate,
                        "remaining_step_budget": budget["max_steps"] - step - 1,
                        "scope": (
                            "actual deterministic proposal cycle"
                            if cycle
                            else "bounded sampled local candidate window"
                        ),
                        "global_exhaustion_proved": False,
                        "unseen_variants_may_exist": True,
                        "current_node_id": current,
                        "current_word_hash": history.states[current].word_hash,
                        "history_identity": budget.get("history_identity", "word"),
                        "allowed_operators": operators,
                        "sampled_operators": sampled,
                        "unproposed_operators": [
                            o for o in operators if o not in sampled
                        ],
                        "steps_without_new_paths": stale_steps,
                        "window_step_range": [start, step],
                        "clock_state": clock_state,
                        "repeated_clock_first_step": (
                            stale_clocks.get(signature) if cycle else None
                        ),
                        "tested_variants": list(actual.values()),
                        "boundary": "No new accepted path in this actual bounded proposal set; not closure of the full operation algebra.",
                    }
                )
                if candidate is None:
                    halt = "ACTUAL_LOCAL_EXHAUSTION"
                    break
                if step + 1 < budget["max_steps"]:
                    pending = {
                        **candidate,
                        "fallback_reason": reason,
                        "stagnation_diagnostic_index": len(diagnostics) - 1,
                    }
                stale_steps = 0
                stale_clocks.clear()
    diagnostics.append(
        {
            "kind": "observed",
            "status": halt,
            "halt_reason": halt,
            **counters(),
            "current_node_id": current,
            "current_word_hash": history.states[current].word_hash,
            "current_node_history_ref": current,
            "fallback_reason": "terminal_budget_or_bounded_sampled_frontier",
            "scope": "one sampled argument variant per tried stored-node/operator pair and actual local proposal windows",
            "unseen_variants_may_exist": True,
            "sampled_operators": [op for op in operators if coverage[op]["proposed"]],
            "unproposed_operators": [
                op for op in operators if not coverage[op]["proposed"]
            ],
            "operation_coverage": coverage,
            "boundary": "No global exhaustion claim; parameter variants and unstored states are outside this frontier certificate.",
        }
    )
    return {
        "ops_trace": trace,
        "structural_observations": [
            {"node_id": i, **o} for i, o in observations.items()
        ],
        "search_diagnostics": diagnostics,
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
            **counters(),
            "policy": "symbolic-local-pareto-frontier/2",
            "operation_coverage": coverage,
            "revisited_nodes": sum(n > 1 for n in visits.values()),
            "revisit_count": sum(n - 1 for n in visits.values()),
            "distinct_provenance_traces": len(history.nodes),
            "provenance_trace_unit": "content-addressed DAG nodes, including source records",
            "budgets": {
                **budget,
                "max_observations": max_observations,
                "max_total_tokens": max_total,
            },
            "stagnation_window": window,
            "saturation_certificate_digest": (
                digest(
                    next(d for d in diagnostics if d["status"] == "LOCAL_STAGNATION")
                )
                if any(d["status"] == "LOCAL_STAGNATION" for d in diagnostics)
                else None
            ),
            "termination_diagnostic_digest": digest(diagnostics[-1]),
        },
        "final_node_id": current,
    }
