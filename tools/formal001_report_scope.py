"""Post-inference separation of genuinely unseen words and annotated controls."""

import argparse, json, hashlib
from pathlib import Path


def annotate(qa, fixture):
    data = json.loads((fixture / "inputs.json").read_text())
    gold = json.loads((fixture / "external-gold.json").read_text())
    raw = json.loads((qa / "FORMAL_LANGUAGE_MATRIX.json").read_text())
    pred = json.loads((qa / "predictions.json").read_text())
    comp = json.loads((qa / "comparison.json").read_text())
    out = {}
    for key, score in raw.items():
        legacy = key.endswith("-auto") or key.endswith("-role_branching_ast")
        base = (
            key.rsplit("-", 1)[0]
            if legacy
            else key.removesuffix("-enriched-pre-active").removesuffix("-enriched")
        )
        case = data["cases"][base]
        train = list(case["train"])
        if "-enriched" in key:
            train += case.get("annotation", [])
            q = qa / (base + "-ACTIVE_ANNOTATIONS.json")
            if q.exists() and not key.endswith("-pre-active"):
                train += [x["train_record"] for x in json.loads(q.read_text())]
        words = {tuple(r["tokens"]) for r in train}
        queries = case["enriched_queries"] if "-enriched" in key else case["queries"]
        seen = {r["id"] for r in queries if tuple(r["tokens"]) in words}
        rows = comp[key]["predictions"] if legacy else pred[key]
        values = {
            r["record_id"]: (None if r.get("score") is None else r["score"] >= 0.5)
            if legacy
            else r["decision"]
            for r in rows
        }
        labels = gold[base + "-enriched" if "-enriched" in key else base]
        unseen = dict(TP=0, TN=0, FP=0, FN=0, UNKNOWN=0)
        for rid, y in labels.items():
            if rid in seen:
                continue
            v = values[rid]
            if v is None:
                unseen["UNKNOWN"] += 1
            else:
                unseen["TP" if y and v else "FN" if y else "FP" if v else "TN"] += 1
        out[key] = {
            **score,
            "train_word_overlap": len(seen),
            "seen_control_ids": sorted(seen),
            "unseen_total": len(labels) - len(seen),
            "unseen_metrics": unseen,
            "evaluation_scope": "FINITE_HOLDOUT_WITH_SEPARATE_SEEN_CONTROLS"
            if seen
            else "FINITE_UNSEEN_WORDS",
        }
    (qa / "FORMAL_LANGUAGE_MATRIX_WITH_SCOPE.json").write_text(
        json.dumps(out, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "raw_matrix_sha256": hashlib.sha256(
                    (qa / "FORMAL_LANGUAGE_MATRIX.json").read_bytes()
                ).hexdigest(),
                "seen_control_cases": {
                    k: v["train_word_overlap"]
                    for k, v in out.items()
                    if v["train_word_overlap"]
                },
                "raw_results_preserved": True,
            }
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("qa", type=Path)
    p.add_argument("fixture", type=Path)
    a = p.parse_args()
    annotate(a.qa, a.fixture)
