"""Discover, select and independently promote bounded existing-operator ASTs."""

from pathlib import Path
import hashlib
from ..core import digest
from ..errors import AssuranceError
from ..symbolic import grammar
from ..symbolic_complex.contracts import Budget
from .composition_ast import (
    settings,
    declared_domain,
    ast_metrics,
    execute,
    DomainLimit,
)
from .composition_checker import verify
from .contexts import record_state


def typed_skeletons(records):
    """Finite structural constructors, not filters on the shortest positive.

    Every observed coordinate proposes a literal comparison and its strictly
    decreasing closure, before membership validation. Additional conjunctions
    refine positive-safe observations; they never control recursive generation.
    """
    coordinates = min(4, max(1, max(len(r["tokens"]) for r in records) // 2))
    guards = []
    for offset in range(coordinates):
        for expected in [True, False]:
            guard = {
                "composition": "aligned_token_equality",
                "offset": offset,
                "expected_equal": expected,
                "left_operations": ["SPLIT"],
                "right_operations": ["REVERSE", "SPLIT"],
                "base_max_tokens": 2 * offset + 1,
            }
            guards.append(guard)
            yield guard
            yield {
                "composition": "iterate_on_inner_fragment",
                "relation": guard,
                "trim_left": 1,
                "trim_right": 1,
                "fragment_operations": ["SPLIT", "SPLIT"],
                "base_max_tokens": 1,
            }
    positives = [r for r in records if r["accepted"]]
    safe = [
        g
        for g in guards
        if positives and all(grammar.relation_value(g, r["tokens"]) for r in positives)
    ]
    for count in range(2, min(4, len(safe)) + 1):
        yield {"composition": "all_observed_relations", "relations": safe[:count]}


def generation_diagnostics(log, records, search):
    from collections import Counter

    candidates = [r for r in log if r.get("phase") == "composition_discovery"]
    generated = [r for r in candidates if r["generation_status"] == "GENERATED"]
    catalog = next((r for r in log if r.get("phase") == "composition_catalog"), {})
    return {
        "grammar_version": "mixed_length_typed_composition/1",
        "search_budget": {**search, **catalog.get("construction_bounds", {})},
        "train_length_histogram": dict(
            sorted(Counter(str(len(r["tokens"])) for r in records).items())
        ),
        "generated_by_ast_kind": dict(Counter(r["kind"] for r in generated)),
        "seen": len(generated),
        "generated_count": len(generated),
        "type_checked_count": sum(r["type_status"] == "TYPED" for r in generated),
        "train_compatible": sum(
            r["train_status"] == "TRAIN_COMPATIBLE" for r in generated
        ),
        "train_compatible_count": sum(
            r["train_status"] == "TRAIN_COMPATIBLE" for r in generated
        ),
        "candidate_records": [
            {k: v for k, v in r.items() if k not in ("ast", "predicted_train_labels")}
            for r in candidates
        ],
        "bounded_search_complete": catalog.get("bounded_search_complete", False),
        "bounded_search_reason": catalog.get(
            "bounded_search_reason", "GENERATION_NOT_APPLICABLE"
        ),
        "candidate_budget_exhausted": catalog.get("candidate_budget_exhausted", False),
        "search_status": catalog.get("search_status", "NOT_GENERATED"),
        "no_unique_grammar_claim": True,
    }


def promote(
    samples: list[dict],
    policy: dict,
    search: dict,
    promotion_policy: dict,
    admitted,
    source: dict | None = None,
) -> tuple[list, list]:
    config = settings(promotion_policy)
    log = []

    def reject(reason, **extra):
        log.append(
            {
                "phase": "composition_promotion",
                "status": "NOT_PROMOTED",
                "failed_obligation": reason,
                **extra,
            }
        )
        return [], log

    if not policy.get("derive_relations", True):
        return [], []
    if policy.get("representation", "literal") != "literal":
        return reject("LITERAL_SOURCE_REPRESENTATION_REQUIRED")
    if (
        not 0
        < len(samples)
        <= min(256, config["max_train_witnesses"], search["max_witnesses"])
    ):
        return reject("COMPOSITION_TRAIN_WITNESS_BOUND")
    records = sorted([s["record"] for s in samples], key=digest)
    train_digest = digest(records)
    domain = declared_domain(config)
    if any(len(r["tokens"]) > domain["max_tokens"] for r in records):
        return reject("TRAIN_OUT_OF_DECLARED_SCOPE")
    members = [{"tokens": r["tokens"], "accepted": r["accepted"]} for r in records]
    budget = Budget(
        {**search, "max_cpu_ms": min(search["max_cpu_ms"], config["max_runtime_ms"])}
    )
    candidates = []
    seen = set()

    def candidate(ast, route, provenance=None):
        ident = digest(ast)
        if ident in seen:
            return
        seen.add(ident)
        candidates.append((ast, route, provenance or {}))

    sources = config["candidate_sources"]
    if "source_run_id" in sources and source:
        for supplied in source["candidates"]:
            candidate(supplied["ast"], "source_run_id", source["binding"])
    if "derivation_trace" in sources:
        provenance = {
            # Retain the approved closed generator identity; its exact source
            # hash now binds both structural cut and recursive constructors.
            "generator": "bounded_structural_cut_x_literal_word_comparison",
            "generator_source_sha256": hashlib.sha256(
                Path(__file__).read_bytes()
            ).hexdigest(),
        }
        for ast in typed_skeletons(records):
            candidate(ast, "derivation_trace", provenance)
        shortest = min(len(r["tokens"]) for r in records)
        for position in ["MIDPOINT_EXACT_EVEN", *range(1, min(4, shortest) + 1)]:
            for expected in [True, False]:
                candidate(
                    {
                        "composition": "compare_fragments",
                        "cut": {"operator": "SPLIT", "position": position},
                        "comparison": "literal_word_equality",
                        "expected_equal": expected,
                    },
                    "derivation_trace",
                    provenance,
                )
    compatible = []
    incomplete = len(candidates) > search["max_proposals"]
    for index, (ast, route, provenance) in enumerate(candidates):
        entry = {
            "phase": "composition_discovery",
            "ast": ast,
            "ast_digest": digest(ast),
            "kind": ast["composition"],
            "route": route,
            "origin": "SOURCE_SUPPLIED"
            if route == "source_run_id"
            else "AUTO_DISCOVERED",
            "train_coverage": len(records),
            "generation_status": "GENERATED",
            "type_status": "NOT_CHECKED",
            "train_status": "NOT_CHECKED",
            "promotion_status": "NOT_APPLICABLE",
            "counterexamples": [],
        }
        if index >= search["max_proposals"]:
            entry.update(
                generation_status="NOT_GENERATED",
                status="NOT_GENERATED",
                pruning_reason="max_proposals",
            )
            log.append(entry)
            continue
        budget.check()
        try:
            nodes, depth = ast_metrics(ast)
            entry.update(
                type_status="TYPED", complexity={"ast_nodes": nodes, "ast_depth": depth}
            )
        except (ValueError, KeyError, TypeError) as exc:
            termination = "RECURSION" in str(exc)
            entry.update(
                status="GENERATED_REJECTED_BY_TERMINATION"
                if termination
                else "GENERATED_REJECTED_BY_TYPE",
                type_status="TERMINATION_REJECTED" if termination else "TYPE_REJECTED",
                pruning_reason=str(exc),
            )
            log.append(entry)
            continue
        try:
            if nodes > config["max_ast_nodes"] or depth > config["max_ast_depth"]:
                raise DomainLimit("AST_SCOPE_EXCEEDED")
            predictions = [
                execute(ast, record_state(r), domain, budget=budget)[0] for r in records
            ]
            failures = [
                {
                    "sample_id": r["id"],
                    "record_ref": digest(r),
                    "length": len(r["tokens"]),
                    "expected": r["accepted"],
                    "observed": d,
                }
                for r, d in zip(records, predictions)
                if d != r["accepted"]
            ]
            entry.update(
                predicted_train_labels=predictions,
                counterexample_train_refs=[x["record_ref"] for x in failures],
                counterexamples=failures,
                train_status="TRAIN_COMPATIBLE"
                if not failures
                else "GENERATED_REJECTED_BY_TRAIN",
                status="TRAIN_COMPATIBLE" if not failures else "REJECTED_BY_TRAIN",
                pruning_reason="TRAIN_COUNTEREXAMPLE" if failures else None,
            )
            if not failures:
                entry["promotion_status"] = "TRAIN_COMPATIBLE_NOT_PROMOTED"
                compatible.append((nodes, depth, digest(ast), ast, route, provenance))
        except AssuranceError:
            raise
        except DomainLimit as exc:
            incomplete = True
            entry.update(
                status="GENERATED_REJECTED_BY_BOUND",
                train_status="NOT_CHECKED_RESOURCE_BOUND",
                pruning_reason=str(exc),
            )
        log.append(entry)
    log.append(
        {
            "phase": "composition_catalog",
            "construction_bounds": {
                k: config[k]
                for k in (
                    "max_ast_nodes",
                    "max_ast_depth",
                    "max_recursion_steps",
                    "max_tokens",
                    "max_runtime_ms",
                )
            },
            "grammar_version": "mixed_length_typed_composition/1",
            "catalog_size": len(candidates),
            "bounded_search_complete": not incomplete,
            "candidate_budget_exhausted": len(candidates) > search["max_proposals"],
            "search_status": "BOUNDED_SEARCH_INCOMPLETE"
            if incomplete
            else "BOUNDED_CATALOG_CHECKED",
            "bounded_search_reason": "max_proposals"
            if len(candidates) > search["max_proposals"]
            else "declared_AST_or_recursion_bound"
            if incomplete
            else "all_declared_candidates_checked",
            "scope": "Declared finite typed skeleton catalog only; not completeness over all programs",
        }
    )
    if not compatible:
        return reject(
            "BOUNDED_SEARCH_INCOMPLETE"
            if incomplete
            else "NO_TRAIN_COMPATIBLE_TYPED_COMPOSITION"
        )
    # All fully covered candidates have equal empirical coverage. Minimize the
    # explicit AST construction size/depth, then canonical hash; never query score.
    selected = min(compatible, key=lambda x: x[:3])
    _, _, _, ast, route, provenance = selected
    state_sha = hashlib.sha256(
        (Path(__file__).resolve().parent.parent / "symbolic/state.py").read_bytes()
    ).hexdigest()
    evaluator_sha = hashlib.sha256(
        Path(__file__).with_name("composition_ast.py").read_bytes()
    ).hexdigest()
    parents = ["operator:SPLIT", "primitive:literal_word_equality"]
    if ast["composition"] != "compare_fragments":
        parents.append("operator:REVERSE")
    feature = {
        "feature_id": "derived_"
        + digest(
            {
                "ast": ast,
                "domain": domain,
                "operator_bindings": {
                    "state_sha256": state_sha,
                    "evaluator_sha256": evaluator_sha,
                },
            }
        )[:20],
        "feature_version": "2",
        "semantic_type": "bounded_operator_composition",
        "origin": "DERIVED_FROM_OPERATORS",
        "operator_ast": ast,
        "operator_ast_digest": digest(ast),
        "operator_bindings": {
            "state_sha256": state_sha,
            "evaluator_sha256": evaluator_sha,
        },
        "required_observers": [],
        "parent_feature_refs": sorted(parents),
        "semantic_alias_of": "endpoint_equal"
        if ast["composition"] == "aligned_token_equality" and ast["offset"] == 0
        else None,
        "source_code_binding_sha256": evaluator_sha,
        "template_origin": "COMPOSITIONAL_AST_PROMOTION",
        "construction_trace": [],
        "candidate_provenance": {
            **provenance,
            "route": route,
            "origin": "SOURCE_SUPPLIED"
            if route == "source_run_id"
            else "AUTO_DISCOVERED",
            "ast_digest": digest(ast),
            "train_digest": train_digest,
        },
        "train_digest": train_digest,
        "train_only_witness_refs": [digest(r) for r in records],
        "claim_status": "CHECKED_FINITE_INSTANCE",
        "derived_claim_allowed": True,
        "known_invariance_scope": domain,
        "execution_verified": False,
        "role": "PREDICTIVE",
        "novelty": "Selected finite composition of existing operators; empirical, not a new primitive or unique grammar",
    }
    if not admitted(feature, policy):
        return reject(
            "PARENT_OR_FEATURE_DISABLED",
            feature_id=feature["feature_id"],
            selection_policy="full_train_coverage_then_ast_nodes_depth_hash",
        )
    for r in records:
        budget.check()
        state = record_state(r)
        answer, trace, states = execute(
            ast, state, domain, digest(r), certify=True, budget=budget
        )
        feature["construction_trace"].append(
            {
                "record_ref": digest(r),
                "source_sha256": r["source"]["sha256"],
                "input_state_ref": digest(state.data()),
                "decision": answer,
                "operator_trace": trace,
                "states": states,
            }
        )
    feature["witness_set_digest"] = digest(feature["construction_trace"])
    checked = verify(feature, samples)
    budget.check()
    feature["verifier_result"] = checked
    feature["execution_verified"] = checked["status"] == "CHECKED_INSTANCE"
    if not feature["execution_verified"]:
        return reject("INDEPENDENT_COMPOSITION_CHECK_FAILED", verifier_result=checked)
    for row in log:
        if row.get("phase") == "composition_discovery" and row["ast_digest"] == digest(
            ast
        ):
            row["promotion_status"] = "PROMOTED_VERIFIED"
    log.append(
        {
            "phase": "composition_promotion",
            "status": "PROMOTED_OPERATOR_COMPOSITION",
            "executed_rule": True,
            "feature_id": feature["feature_id"],
            "ast_digest": digest(ast),
            "selection_policy": "full_train_coverage_then_ast_nodes_depth_hash",
            "compatible_candidates": len(compatible),
            "independent_check": checked,
            "limits_used": config,
        }
    )
    return [feature], log
