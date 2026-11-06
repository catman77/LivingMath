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
        _, discovered = grammar.relational_candidates(
            members, min(15, search["max_proposals"]), None
        )
        for row in discovered:
            if "ast" in row:
                candidate(
                    row["ast"],
                    "derivation_trace",
                    {
                        "generator": "symbolic.grammar.relational_candidates",
                        "generator_source_sha256": hashlib.sha256(
                            Path(grammar.__file__).read_bytes()
                        ).hexdigest(),
                    },
                )
        # Generic typed constructor: structural split coordinates composed with
        # equality or inequality of two complete Words. No named target class.
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
                    {
                        "generator": "bounded_structural_cut_x_literal_word_comparison",
                        "generator_source_sha256": hashlib.sha256(
                            Path(__file__).read_bytes()
                        ).hexdigest(),
                    },
                )
    compatible = []
    for ast, route, provenance in candidates[: search["max_proposals"]]:
        budget.check()
        entry = {
            "phase": "composition_discovery",
            "ast": ast,
            "ast_digest": digest(ast),
            "route": route,
            "origin": "SOURCE_SUPPLIED"
            if route == "source_run_id"
            else "AUTO_DISCOVERED",
            "train_coverage": len(records),
        }
        try:
            nodes, depth = ast_metrics(ast)
            if nodes > config["max_ast_nodes"] or depth > config["max_ast_depth"]:
                raise DomainLimit("AST_SCOPE_EXCEEDED")
            predictions = [
                execute(ast, record_state(r), domain, budget=budget)[0] for r in records
            ]
            failures = [
                digest(r) for r, d in zip(records, predictions) if d != r["accepted"]
            ]
            entry.update(
                complexity={"ast_nodes": nodes, "ast_depth": depth},
                predicted_train_labels=predictions,
                counterexample_train_refs=failures,
                status="TRAIN_COMPATIBLE" if not failures else "REJECTED_BY_TRAIN",
            )
            if not failures:
                compatible.append((nodes, depth, digest(ast), ast, route, provenance))
        except AssuranceError:
            raise
        except (ValueError, KeyError, TypeError) as exc:
            entry.update(status="NOT_PROMOTED", failed_obligation=str(exc))
        log.append(entry)
    if not compatible:
        return reject("NO_TRAIN_COMPATIBLE_TYPED_COMPOSITION")
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
