"""Short fixed FIX-B2 experiments; labels read only after all bounded jobs finish."""

import argparse, copy, json
from pathlib import Path
from lm_suti_assurance.core import digest
from lm_suti_assurance.symbolic.executor import Executor


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def requests(fixture):
    base = json.loads((fixture / "request.json").read_text())
    base["feature_policy"]["feature_denylist"] = [
        "pair_0_max",
        "pair_0_min",
        "pair_0_final",
    ]
    rows = {}
    for name, groups, derived in [
        ("promoted", [], True),
        ("no_derivation", [], False),
        ("literal_only", ["literal"], False),
        (
            "builtin_only",
            ["literal", "adjacency", "composition", "alpha_pattern"],
            False,
        ),
        ("majority", [], False),
        (
            "builtin_all",
            ["literal", "adjacency", "composition", "alpha_pattern"],
            False,
        ),
    ]:
        q = copy.deepcopy(base)
        q["feature_policy"].update(enabled_builtins=groups, derive_relations=derived)
        if name == "builtin_all":
            q["feature_policy"]["feature_denylist"] = []
        rows[name] = q
    return rows


def score(predictions, labels):
    total = {"TP": 0, "TN": 0, "FP": 0, "FN": 0, "abstain": 0}
    for p in predictions:
        if p["score"] is None:
            total["abstain"] += 1
            continue
        truth = labels[p["record_id"]]
        guess = p["score"] >= 0.5
        total[
            "TP" if truth and guess else "FN" if truth else "FP" if guess else "TN"
        ] += 1
    return {
        **total,
        "total": len(predictions),
        "correct": total["TP"] + total["TN"],
        "accuracy": (total["TP"] + total["TN"]) / len(predictions),
        "coverage": 1 - total["abstain"] / len(predictions),
    }


def experiment(fixture, out):
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    train = json.loads((fixture / "train.json").read_text())
    queries = json.loads((fixture / "queries.json").read_text())
    protocol = json.loads((fixture / "PROTOCOL.json").read_text())
    if (
        digest(train) != protocol["train_digest"]
        or digest(queries) != protocol["query_digest"]
    ):
        raise ValueError("FROZEN_INPUT_MISMATCH")
    pool = Executor()
    results = {}
    configs = requests(fixture)
    try:
        for name, request in configs.items():
            result = pool.run(
                {
                    "action": "extension_run",
                    "engine": "observer_synthesis_v1",
                    "request": request,
                    "resolved": {"train": train, "queries": queries},
                }
            )
            save(out / (name + ".json"), result)
            data = result["data"]
            results[name] = {
                "result_digest": digest(data),
                "hypothesis_digest": data["model"]["hypothesis_digest"],
                "status": data["summary"]["synthesis_status"],
                "used_feature_ids": data["model"]["used_feature_ids"],
                "promotion_statistics": data["model"]["promotion_statistics"],
            }
            print(name, results[name]["status"], flush=True)
        promoted = json.loads((out / "promoted.json").read_text())["data"]["model"]
        feature = next(
            f for f in promoted["feature_registry"] if f.get("role") == "PREDICTIVE"
        )
        name = "parent_disabled"
        q = copy.deepcopy(configs["promoted"])
        q["feature_policy"]["feature_denylist"].append(
            feature["parent_feature_refs"][0]
        )
        configs[name] = q
        result = pool.run(
            {
                "action": "extension_run",
                "engine": "observer_synthesis_v1",
                "request": q,
                "resolved": {"train": train, "queries": queries},
            }
        )
        save(out / (name + ".json"), result)
        data = result["data"]
        results[name] = {
            "result_digest": digest(data),
            "hypothesis_digest": data["model"]["hypothesis_digest"],
            "status": data["summary"]["synthesis_status"],
            "used_feature_ids": data["model"]["used_feature_ids"],
            "promotion_statistics": data["model"]["promotion_statistics"],
        }
    finally:
        pool.close()
    save(out / "CONFIGURATIONS.json", configs)
    labels = json.loads((fixture / "external-label-holder/labels.json").read_text())
    if digest(labels) != protocol["external_labels_digest"]:
        raise ValueError("LABEL_HOLDER_MISMATCH")
    for name, row in results.items():
        values = json.loads((out / (name + ".json")).read_text())["data"][
            "pairwise_eval"
        ]["predictions"]
        row["scores"] = {
            str(n): score(
                [
                    r
                    for r in values
                    if len(
                        next(q for q in queries if q["id"] == r["record_id"])["tokens"]
                    )
                    == n
                ],
                labels,
            )
            for n in [4, 5]
        }
    save(out / "RESULTS.json", results)
    print(json.dumps({"status": "PASS", "results": results}), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--fixture", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    experiment(a.fixture, a.output)
