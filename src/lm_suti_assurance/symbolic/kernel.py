"""Deterministic experiment artifacts. Runtime metrics and test labels stay outside."""

from itertools import combinations
from pathlib import Path
from ..core import digest, byte_digest
from ..white_star.contracts import integrity
from .contracts import validate, LIMITS
from .state import History, source_states, alpha
from .observers import CADObserver, compare
from .search import search
from .grammar import fit, probability, prediction


def binding():
    root = Path(__file__).parent
    return digest(
        {
            n: byte_digest((root / n).read_bytes())
            for n in (
                "state.py",
                "observers.py",
                "search.py",
                "grammar.py",
                "kernel.py",
                "contracts.py",
            )
        }
    )


def run(request, clock_factory):
    validate(request)
    history = History()
    root, records, source_map = source_states(request, history)
    observer = CADObserver(
        request["observers"],
        request["segmentation"]["renaming_scope"],
        source_map["declared_hierarchy"],
    )
    found = search(request, history, records, observer, clock_factory)
    claims = []
    for left, right in list(combinations(records, 2))[:128]:
        for claim in compare(history.states[left], history.states[right], observer):
            claims.append(
                {
                    "claim_id": "C" + str(len(claims) + 1).zfill(4),
                    "left_node_id": left,
                    "right_node_id": right,
                    **claim,
                }
            )
    task = request["task"]
    grammar = []
    predictions = []
    if task.get("train"):
        hypothesis = fit(
            task["train"],
            task.get("max_rules", 15),
            request["observers"],
            renaming_scope=request["segmentation"]["renaming_scope"],
        )
        grammar = [hypothesis]
        # Freeze before the prediction interface ever receives queries.
        frozen = hypothesis["hypothesis_digest"]
        predictions = [
            {
                "tokens": word,
                "membership_probability": probability(hypothesis, word),
                "decision": prediction(hypothesis, word),
                "kind": "empirical",
                "hypothesis_digest": frozen,
            }
            for word in task.get("predict", [])
        ]
    else:
        grammar = [
            {
                "status": "UNDERDETERMINED",
                "mode": "descriptive",
                "reason": "No labelled training membership supplied; observed contexts are not a unique grammar.",
                "competing_models": {
                    "finite_observed_words": [
                        list(history.states[i].tokens) for i in records
                    ],
                    "all_words_over_observed_alphabet": sorted(
                        set(history.states[root].tokens)
                    ),
                },
                "kind": "conjecture",
                "execution_permission": False,
            }
        ]
    nodes = list(history.nodes.values())
    states = [{"node_id": i, **s.data()} for i, s in history.states.items()]
    summary = {
        **found["search_summary"],
        "distinct_alpha_classes": len(
            {alpha(s.tokens) for s in history.states.values()}
        ),
        "proved_claims": sum(c["kind"] == "proved_exact" for c in claims),
        "empirical_claims": len(predictions),
        "underdetermined_claims": sum(
            g["status"] == "UNDERDETERMINED" for g in grammar
        ),
    }
    numeric = integrity()
    output = {
        "schema": "levinmas-white-star-symbolic-artifacts/1",
        "engine": "symbolic_v1",
        "input": request,
        "source_map": source_map,
        "root_node_id": root,
        "record_node_ids": records,
        "states": states,
        "history": nodes,
        "ops_trace": found["ops_trace"],
        "search_diagnostics": found["search_diagnostics"],
        "structural_observations": found["structural_observations"],
        "equivalence_claims": claims,
        "grammar_hypotheses": grammar,
        "heldout_eval": {
            "visibility": "queries_only_after_hypothesis_freeze",
            "status": (
                "PREDICTIONS_ONLY_NO_HELDOUT_LABELS" if predictions else "UNASSESSED"
            ),
            "predictions": predictions,
            "boundary": "Independent harness owns sealed labels and scores frozen hypotheses.",
        },
        "checks": {
            "DAG_acyclic_and_hashed": history.verify(),
            "source_hash_valid": True,
            "LLM_calls": 0,
            "execution_permission": False,
        },
        "summary": summary,
    }
    manifest = {
        "schema": "livingmath-symbolic-artifact-manifest/1",
        "symbolic_version": "symbolic_v1/1-patch002",
        "kernel_binding": binding(),
        "numeric_kernel_binding": digest(numeric),
        "numeric_kernel_files": numeric,
        "udav_clock": "actual supplied ReversibleUDAV.step; local set-inclusion controller with bounded stored-node/operator fallback symbolic-local-pareto-frontier/2",
        "request_digest": digest(request),
        "artifact_digests": {k: digest(v) for k, v in output.items()},
        "limits": LIMITS,
        "execution_permission": False,
    }
    output["manifest"] = manifest
    return output
