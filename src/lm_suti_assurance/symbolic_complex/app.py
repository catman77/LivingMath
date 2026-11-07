"""Fixed worker dispatch for both additive engines; never user code or paths."""

from pathlib import Path
from ..core import digest, byte_digest
from ..symbolic.kernel import binding as symbolic_binding
from ..symbolic.state import require
from ..observer_synthesis import contracts as observer_contracts
from ..observer_synthesis.learner import fit, predict
from ..observer_synthesis.data import validate_record
from .contracts import validate, Budget
from .model import analyze
from .checker import verify


def binding():
    root = Path(__file__).parent
    return digest(
        {
            "symbolic_binding": symbolic_binding(),
            "modules": {
                str(p.relative_to(root.parent)): byte_digest(p.read_bytes())
                for folder in (root, root.parent / "observer_synthesis", root.parent / "formal_bridge")
                for p in sorted(folder.glob("*.py"))
            },
        }
    )


def execute(engine, request, resolved):
    if engine == "symbolic_complex_v1":
        data = analyze(request, resolved.get("source_artifact"))
    elif engine == "observer_synthesis_v1":
        validate(request, observer_contracts.REQUEST)
        budget = Budget(request["search"])
        train = resolved["train"]
        queries = resolved["queries"]
        require(
            0 < len(train) <= 2048 and len(queries) <= 1024,
            "BUDGET_EXCEEDED",
            "/datasets",
        )
        require(
            len({r["id"] for r in train}) == len(train)
            and len({r["id"] for r in queries}) == len(queries),
            "DUPLICATE_RECORD_ID",
            "/datasets",
        )
        require(
            sum(len(r["tokens"]) for r in train + queries) <= 131072,
            "BUDGET_EXCEEDED",
            "/datasets/tokens",
        )
        for record in train:
            validate_record(record, "train")
            budget.check()
        # Full query validation happens after fitting; no fit parameter can see queries.
        model = fit(train, request, resolved.get("source_candidates"))
        seal = model["hypothesis_digest"]
        for record in queries:
            validate_record(record, "queries")
            budget.check()
        evaluation = predict(model, queries, budget)
        require(model["hypothesis_digest"] == seal, "HYPOTHESIS_MUTATED")
        budget.check()
        data = {
            "schema": "livingmath-observer-artifacts/1",
            "engine": engine,
            "input": request,
            "resolved": resolved,
            "model": model,
            "observer_provenance": model["feature_registry"],
            "candidate_rules": [model["tree"]] if model["tree"] else [],
            "pairwise_eval": evaluation,
            "diagnostics": [
                {
                    "status": model["training_status"],
                    **model.get("composition_diagnostics",{}),
                    "promotion": model.get("promotion_statistics", {}),
                    **({"role_branching":model["role_diagnostics"]} if model.get("role_diagnostics") else {}),
                    "training_conflicts": len(model["training_conflicts"]),
                    "conditional_exclusion_applied": model[
                        "conditional_exclusion_applied"
                    ],
                }
            ],
            "checks": {
                "holdout_labels_read": False,
                "hypothesis_frozen_before_queries": True,
                "LLM_calls": 0,
                "execution_permission": False,
            },
            "summary": {
                "training_status": model["training_status"],
                "synthesis_status": model["synthesis_status"],
                "family_status": "UNDERDETERMINED",
                "train_records": len(train),
                "query_records": len(queries),
                "pair_counts": {
                    s: sum(p["status"] == s for p in evaluation["pairs"])
                    for s in [
                        "PREFERENCE",
                        "TIE",
                        "NOT_IDENTIFIABLE",
                        "UNDERDETERMINED",
                    ]
                },
                "hypothesis_digest": seal,
                "conditional_exclusion_applied": model["conditional_exclusion_applied"],
                "execution_permission": False,
            },
        }
    else:
        require(False, "UNSUPPORTED_MODEL", "/engine")
    data["manifest"] = {
        "schema": "livingmath-symbolic-extension-manifest/1",
        "engine": engine,
        "kernel_binding": binding(),
        "symbolic_binding": symbolic_binding(),
        "request_digest": digest(request),
        "resolved_digest": digest(resolved),
        "artifact_digests": {k: digest(v) for k, v in data.items()},
        "execution_permission": False,
    }
    return data


def dispatch(packet):
    action = packet["action"]
    if action == "observer_verify" and "formal_packet" in packet:
        from ..formal_bridge.engine import dispatch as formal_dispatch
        from ..errors import AssuranceError
        try:
            return formal_dispatch(packet["formal_packet"])
        except (ValueError,TypeError,KeyError) as exc:
            raise AssuranceError("FORMAL_INVALID_INPUT",details={"message":str(exc)[:256]})
    if action == "extension_run":
        return execute(packet["engine"], packet["request"], packet.get("resolved", {}))
    if action == "complex_verify":
        return verify(packet["artifact"])
    if action == "observer_verify" and "query_record" in packet:
        from ..observer_synthesis.role_ast import execute as execute_role
        from ..observer_synthesis.role_checker import verify_proof
        feature=packet["feature"];record=packet["query_record"]
        proof=packet.get("certificate")
        if proof is None:_,proof=execute_role(feature["operator_ast"],record,feature["known_invariance_scope"])
        checked=verify_proof(feature["operator_ast"],record,feature["known_invariance_scope"],proof)
        return {"status":checked["status"],"verification":checked,"certificate":proof,"record_id":record["id"],"execution_permission":False}
    if action == "observer_verify":
        from ..observer_synthesis.independent_verifier import verify as verify_observer

        return verify_observer(packet["feature"], packet["samples"])
    if action == "extension_replay":
        from .bundle import replay

        return replay(packet["bundle_base64"])
    require(False, "INVALID_INPUT", "/action")
