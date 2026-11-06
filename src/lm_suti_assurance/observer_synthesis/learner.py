"""Finite train-only fitting. Prediction queries enter only after the model is sealed."""

from collections import Counter, defaultdict
from ..core import digest
from ..symbolic.state import require
from ..symbolic_complex.contracts import Budget
from .features import encode, builtin_registry, admitted, vector, derive


def probability(tree, values):
    for _ in range(16):
        if "predicate" not in tree:
            return tree["probability"]
        tree = (
            tree["left"]
            if values[tree["predicate"]] <= tree["threshold"]
            else tree["right"]
        )
    raise ValueError("INVALID_TREE")


def fit(records, request):
    search = request["search"]
    policy = request["feature_policy"]
    budget = Budget(search)
    rows = [
        {"record": r, "encoded": encode(r, policy.get("representation", "literal"))}
        for r in sorted(records, key=digest)
    ]
    conflicts = defaultdict(list)
    for row in rows:
        conflicts[row["encoded"]["signature"]].append(row)
    bad = {
        key: rs
        for key, rs in conflicts.items()
        if len({r["record"]["accepted"] for r in rs}) > 1
    }
    conflict_report = [
        {
            "encoding_digest": key,
            "source_refs": [
                {
                    "record_ref": digest(r["record"]),
                    "record_id": r["record"]["id"],
                    "source_sha256": r["record"]["source"]["sha256"],
                    "accepted": r["record"]["accepted"],
                }
                for r in rs
            ],
            "status": "CONTRADICTORY_TRAINING",
        }
        for key, rs in sorted(bad.items())
    ]
    conditional = (
        request["task"].get("conflict_policy", "report_only") == "exclude_with_report"
    )
    empirical = (
        request["task"].get("conflict_policy", "report_only") == "retain_as_empirical"
    )
    use = (
        [r for r in rows if r["encoded"]["signature"] not in bad]
        if conditional
        else rows
    )
    alphabet = sorted({t for r in use for t in r["encoded"]["tokens"]})
    base = builtin_registry(
        [r["encoded"] for r in use] or [{"tokens": [], "lines": [[]]}], policy, alphabet
    )
    features = [f for f in base if admitted(f, policy)]
    from .contexts import observed_contexts

    contexts = observed_contexts(
        use, policy, search, budget, request["task"]["candidate_transformations"]
    )
    derived, derivation_log = (
        derive(use, policy, search, budget, contexts)
        if use and (not bad or conditional or empirical)
        else ([], [])
    )
    features += derived
    for feature in base + derived:
        feature["digest"] = digest(feature)
    vectors = [vector(r["encoded"], alphabet, policy, features) for r in use]
    names = sorted(f["feature_id"] for f in features)
    remaining = [search["max_proposals"]]
    trace = []

    def grow(indices, depth=0):
        counts = Counter(use[i]["record"]["accepted"] for i in indices)
        leaf = {
            "probability": (counts[True] + 1) / (len(indices) + 2),
            "support_train_refs": [digest(use[i]["record"]) for i in indices],
        }
        if (
            len(counts) < 2
            or depth >= search["max_composition_depth"]
            or not remaining[0]
        ):
            return leaf
        proposals = []
        for name in names:
            values = sorted({vectors[i][name] for i in indices})[:-1]
            if len(values) > 8:
                values = [values[j * (len(values) - 1) // 7] for j in range(8)]
            for value in values:
                if not remaining[0]:
                    break
                budget.check()
                remaining[0] -= 1
                left = [i for i in indices if vectors[i][name] <= value]
                right = [i for i in indices if vectors[i][name] > value]
                correct = set()
                for part in (left, right):
                    labels = Counter(use[i]["record"]["accepted"] for i in part)
                    major = labels[True] > labels[False]
                    correct.update(
                        i for i in part if use[i]["record"]["accepted"] == major
                    )
                proposals.append((name, value, left, right, correct))
            if not remaining[0]:
                break
        if not proposals:
            return leaf
        pareto = [p for p in proposals if not any(p[4] < q[4] for q in proposals)]
        chosen = min(pareto, key=lambda p: digest([search["seed"], p[0], p[1], depth]))
        # Tie-breaking is reproducible set-inclusion, never a universal scalar objective.
        if not chosen[2] or not chosen[3]:
            return leaf
        name, value, left, right, _ = chosen
        trace.append(
            {
                "predicate": name,
                "threshold": value,
                "candidate_count": len(proposals),
                "pareto_count": len(pareto),
                "source_train_refs": [digest(use[i]["record"]) for i in indices],
            }
        )
        return {
            "predicate": name,
            "threshold": value,
            "left": grow(left, depth + 1),
            "right": grow(right, depth + 1),
        }

    tree = (
        None
        if (bad and not (conditional or empirical)) or not use
        else grow(list(range(len(use))))
    )
    used = set()

    def selected(node):
        if node and "predicate" in node:
            used.add(node["predicate"])
            selected(node["left"])
            selected(node["right"])

    selected(tree)
    known = {
        r["encoded"]["signature"]: r["record"]["accepted"]
        for r in use
        if r["encoded"]["signature"] not in bad
    }
    positive = [key for key, label in known.items() if label]
    probe_tokens = (
        (use[0]["encoded"]["tokens"] + use[0]["encoded"]["tokens"][:1])
        if use
        else ["unobserved"]
    )
    model = {
        "schema": "livingmath-observer-hypothesis/1",
        "status": (
            "CONTRADICTORY_TRAINING"
            if bad and not conditional
            else (
                "UNDERDETERMINED"
                if tree
                else "CONTRADICTORY_TRAINING"
                if bad
                else "NO_VERIFIABLE_NEW_OBSERVER"
            )
        ),
        "candidate_status": "EMPIRICAL",
        "identifiability_status": "UNDERDETERMINED",
        "training_status": "CONTRADICTORY_TRAINING" if bad else "CONSISTENT",
        "empirical_conflict_training": empirical and bool(bad),
        "conditional_exclusion_applied": conditional and bool(bad),
        "excluded_record_refs": (
            [digest(r["record"]) for rs in bad.values() for r in rs]
            if conditional
            else []
        ),
        "training_conflicts": conflict_report,
        "train_digest": digest(records),
        "feature_policy": policy,
        "feature_registry": base + derived,
        "enabled_feature_ids": names,
        "disabled_feature_ids": [f["feature_id"] for f in base if f not in features],
        "used_feature_ids": sorted(used),
        "source_train_refs": [digest(r["record"]) for r in use],
        "alphabet": alphabet,
        "tree": tree,
        "candidate_trace": trace,
        "derivation_trace": derivation_log,
        "promotion_statistics": {
            "context_witnesses": len(contexts),
            "executed_promotion_rules": sum(
                bool(r.get("executed_rule")) for r in derivation_log
            ),
            "registered_promoted_features": sum(
                f.get("template_origin") == "LABELLED_CONTEXT_PROMOTION"
                for f in derived
            ),
            "failed_obligations": [
                r for r in derivation_log if r.get("failed_obligation")
            ],
        },
        "competing_train_compatible_models": (
            []
            if bad and not conditional
            else [
                {
                    "kind": "finite_accepted_encoding_set",
                    "accepted_encodings": positive,
                },
                {
                    "kind": "finite_accepted_encoding_set_plus_external_probe",
                    "accepted_encodings": positive,
                    "extra_tokens": probe_tokens,
                },
            ]
        ),
        "active_disambiguation_queries": [
            {
                "tokens": probe_tokens,
                "label_status": "REQUIRED_FROM_EXTERNAL_HOLDER",
                "origin": "bounded mutation of train only",
            }
        ],
        "context_relations": contexts,
        "synthesis_status": (
            "VERIFIABLE_OPERATOR_COMPOSITION_FOUND"
            if derived
            else "NO_VERIFIABLE_NEW_OBSERVER"
        ),
        "scope": "finite supplied training contexts and declared representation; neither unique grammar nor universal contextual congruence",
        "label_budget": len(records),
        "budgets": search,
        "predicate_attempts": search["max_proposals"] - remaining[0],
        "execution_permission": False,
    }
    model["hypothesis_digest"] = digest(model)
    return model


def predict(model, queries, budget=None):
    policy = model["feature_policy"]
    features = [
        f
        for f in model["feature_registry"]
        if f["feature_id"] in model["enabled_feature_ids"]
    ]
    predictions = []
    grouped = defaultdict(list)
    for record in queries:
        if budget:
            budget.check()
        require("accepted" not in record, "HELDOUT_LABEL_LEAKAGE", "/queries")
        encoded = encode(record, policy.get("representation", "literal"))
        values = vector(encoded, model["alphabet"], policy, features)
        out_of_scope = any(
            values.get(name) is None for name in model["used_feature_ids"]
        )
        p = (
            probability(model["tree"], values)
            if model["tree"] and not out_of_scope
            else None
        )
        item = {
            "record_id": record["id"],
            "pair_id": record.get("pair_id"),
            "source_sha256": record["source"]["sha256"],
            "encoding_digest": encoded["signature"],
            "feature_vector_digest": digest(values),
            "score": p,
            "status": "PREDICTION"
            if p is not None
            else "UNKNOWN"
            if out_of_scope
            else "UNDERDETERMINED",
            "kind": "empirical",
            "hypothesis_digest": model["hypothesis_digest"],
        }
        predictions.append(item)
        if record.get("pair_id"):
            grouped[record["pair_id"]].append((record, item, encoded))
    pairs = []
    for ident, rows in sorted(grouped.items()):
        require(len(rows) == 2, "INVALID_PAIR", "/queries/pair_id")
        a, b = rows
        same = a[2]["signature"] == b[2]["signature"]
        status = (
            "NOT_IDENTIFIABLE"
            if same
            else (
                "UNDERDETERMINED"
                if a[1]["score"] is None or b[1]["score"] is None
                else "TIE"
                if a[1]["score"] == b[1]["score"]
                else "PREFERENCE"
            )
        )
        preferred = (
            None
            if status != "PREFERENCE"
            else (a if a[1]["score"] > b[1]["score"] else b)[0]["id"]
        )
        diagnostic_scores = [a[1]["score"], b[1]["score"]]
        if same:
            for _, item, _ in (a, b):
                item["diagnostic_score"] = item["score"]
                item["score"] = None
                item["status"] = "NOT_IDENTIFIABLE"
        difference = None
        if not same:
            aa, bb = a[2]["lines"], b[2]["lines"]
            positions = [
                i
                for i in range(max(len(aa), len(bb)))
                if (aa[i] if i < len(aa) else None) != (bb[i] if i < len(bb) else None)
            ]
            difference = {
                "differing_line_indices": positions,
                "left_source_sha256": a[0]["source"]["sha256"],
                "right_source_sha256": b[0]["source"]["sha256"],
                "left_source_segments": a[0].get("segments", []),
                "right_source_segments": b[0].get("segments", []),
            }
        pairs.append(
            {
                "pair_id": ident,
                "record_ids": [a[0]["id"], b[0]["id"]],
                "status": status,
                "preferred_record_id": preferred,
                "scores": [a[1]["score"], b[1]["score"]],
                "diagnostic_scores": diagnostic_scores,
                "observed_difference_witness": difference,
                "equality_witness": (
                    {
                        "encoding_digest": a[2]["signature"],
                        "scope": policy.get("representation", "literal"),
                    }
                    if same
                    else None
                ),
                "kind": "empirical",
                "confidence_semantics": "Laplace leaf support of selected finite candidate; not confidence in mathematical truth or a unique grammar",
            }
        )
    return {
        "predictions": predictions,
        "pairs": pairs,
        "hypothesis_digest": model["hypothesis_digest"],
        "holdout_labels_read": False,
        "semantic_truth_claimed": False,
    }
