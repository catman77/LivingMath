"""Train-only data-role bindings times bounded generic instruction shuffles."""

import hashlib
from pathlib import Path
from ..core import digest
from ..symbolic_complex.contracts import Budget
from .role_ast import catalog, domain, metrics, execute
from .role_checker import verify, PARENTS


def promote(samples, policy, search, options, admitted):
    log = []

    def failure(reason):
        log.append(
            {
                "phase": "role_promotion",
                "status": "NOT_PROMOTED",
                "failed_obligation": reason,
            }
        )
        return [], log

    if not policy.get("derive_relations", True):
        return [], []
    if policy.get("representation", "literal") != "literal":
        return failure("LITERAL_ROLE_SOURCE_REQUIRED")
    if "derivation_trace" not in options.get(
        "candidate_sources", ["derivation_trace", "source_run_id"]
    ):
        return failure("ROLE_DERIVATION_SOURCE_REQUIRED")
    records = sorted([x["record"] for x in samples], key=digest)
    scope = domain(options)
    if (
        not 0
        < len(records)
        <= min(options.get("max_train_witnesses", 256), search["max_witnesses"], 256)
    ):
        return failure("ROLE_WITNESS_BOUND")
    budget = Budget(
        {
            **search,
            "max_cpu_ms": min(
                search["max_cpu_ms"], options.get("max_runtime_ms", 4000)
            ),
        }
    )
    compatible = []
    truncated = False
    unknown = False
    count = 0
    untried = []
    # No heldout values, fixed language names or arithmetic direction feature.
    for program in catalog(records):
        budget.check()
        if count >= search["max_proposals"]:
            truncated = True
            untried.append(digest(program))
            break
        count += 1
        ident = digest(program)
        entry = {
            "phase": "role_discovery",
            "ast": program,
            "ast_digest": ident,
            "generation_status": "CANDIDATE_GENERATED",
            "type_status": "NOT_CHECKED",
            "train_status": "NOT_CHECKED",
            "promotion_status": "NOT_PROMOTED",
            "counterexamples": [],
        }
        nodes, depth = metrics(program)
        entry["type_status"] = "TYPED"
        if nodes > scope["max_ast_nodes"] or depth > min(
            scope["max_ast_depth"], search["max_composition_depth"]
        ):
            entry.update(pruning_reason="AST_BOUND", train_status="UNKNOWN")
            unknown = True
            log.append(entry)
            continue
        failures = []
        undecided = []
        for r in records:
            budget.check()
            value, proof = execute(program, r, scope, certify=False, budget=budget)
            if value is None:
                undecided.append({"record_ref": digest(r), "reason": proof["reason"]})
            elif value != r["accepted"]:
                failures.append(
                    {
                        "sample_id": r["id"],
                        "record_ref": digest(r),
                        "expected": r["accepted"],
                        "observed": value,
                    }
                )
        entry.update(
            counterexamples=failures,
            unknown_train=undecided,
            train_status="GENERATED_REJECTED_BY_TRAIN"
            if failures
            else "UNKNOWN"
            if undecided
            else "TRAIN_COMPATIBLE",
        )
        unknown = unknown or bool(undecided)
        if not failures and not undecided:
            # Prefer an anchored rule, then construction size, then canonical digest.
            anchored = program["sequence"][0]["op"] == "ATOM_ROLE"
            compatible.append((not anchored, nodes, ident, program))
            entry["promotion_status"] = "TRAIN_COMPATIBLE_NOT_PROMOTED"
        log.append(entry)
    complete = not truncated and not unknown
    log.append(
        {
            "phase": "role_catalog",
            "grammar_version": "roles_x_nullable_rule_shuffles/1",
            "generated": count,
            "untried_ast_digests": untried,
            "untried_preview_only": True,
            "bounds": {
                **scope,
                "max_proposals": search["max_proposals"],
                "max_cpu_ms": min(
                    search["max_cpu_ms"], options.get("max_runtime_ms", 4000)
                ),
            },
            "retained_compatible_ast_digests": [x[2] for x in compatible],
            "compatible": len(compatible),
            "candidate_budget_exhausted": truncated,
            "search_status": "BOUNDED_CATALOG_CHECKED"
            if complete
            else "BOUNDED_SEARCH_INCOMPLETE",
            "untried": "remaining alphabet bindings/base/rule shuffles"
            if truncated
            else "none in declared finite catalog",
            "no_global_exhaustion_claim": True,
        }
    )
    if not compatible:
        return failure(
            "NO_COMPATIBLE_ROLE_PROGRAM_IN_DECLARED_CATALOG"
            if complete
            else "BOUNDED_SEARCH_INCOMPLETE"
        )
    program = min(compatible, key=lambda x: x[:3])[3]
    root = Path(__file__).parent
    hashes = {
        "state_sha256": hashlib.sha256(
            (root.parent / "symbolic/state.py").read_bytes()
        ).hexdigest(),
        "evaluator_sha256": hashlib.sha256(
            (root / "role_ast.py").read_bytes()
        ).hexdigest(),
    }
    f = {
        "feature_id": "derived_"
        + digest({"ast": program, "domain": scope, "operator_bindings": hashes})[:20],
        "feature_version": "3",
        "semantic_type": "typed_role_language",
        "origin": "DERIVED_FROM_OPERATORS",
        "template_origin": "ROLE_BRANCHING_PROMOTION",
        "operator_ast": program,
        "operator_ast_digest": digest(program),
        "operator_bindings": hashes,
        "source_code_binding_sha256": hashes["evaluator_sha256"],
        "candidate_provenance": {
            "catalog": "roles_x_nullable_rule_shuffles/1",
            "route": "derivation_trace",
            "origin": "AUTO_DISCOVERED",
            "ast_digest": digest(program),
            "train_digest": digest(records),
            "generator_source_sha256": hashlib.sha256(
                Path(__file__).read_bytes()
            ).hexdigest(),
        },
        "required_observers": [],
        "parent_feature_refs": sorted(PARENTS),
        "semantic_alias_of": None,
        "train_digest": digest(records),
        "train_only_witness_refs": [digest(r) for r in records],
        "known_invariance_scope": scope,
        "claim_status": "CHECKED_FINITE_INSTANCE",
        "derived_claim_allowed": True,
        "construction_trace": [],
        "execution_verified": False,
        "role": "PREDICTIVE",
        "novelty": "Finite data-bound role program; neither unique grammar nor universal invariant",
    }
    if not admitted(f, policy):
        return failure("ROLE_PARENT_OR_FEATURE_DISABLED")
    for r in records:
        value, proof = execute(program, r, scope, budget=budget)
        f["construction_trace"].append({"record_ref": digest(r), "proof": proof})
    f["witness_set_digest"] = digest(f["construction_trace"])
    checked = verify(f, samples)
    budget.check()
    f["verifier_result"] = checked
    f["execution_verified"] = checked["status"] == "CHECKED_INSTANCE"
    if not f["execution_verified"]:
        return failure("ROLE_INDEPENDENT_CHECK_FAILED: " + str(checked))
    for row in log:
        if row.get("ast_digest") == digest(program):
            row["promotion_status"] = "CHECKED_FINITE_INSTANCE"
    log.append(
        {
            "phase": "role_promotion",
            "status": "CHECKED_FINITE_INSTANCE",
            "feature_id": f["feature_id"],
            "executed_rule": True,
            "compatible_candidates": len(compatible),
            "independent_check": checked,
            "scope": scope,
        }
    )
    return [f], log
