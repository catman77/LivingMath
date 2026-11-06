"""PATCH004 finite frozen worker experiment. Gold is loaded only after inference."""

import argparse, copy, hashlib, json
from itertools import product
from pathlib import Path
from lm_suti_assurance.core import digest
from lm_suti_assurance.symbolic.executor import Executor


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def prepare(source, target):
    target.mkdir(mode=0o700, parents=True, exist_ok=False)
    external = target / "external-label-holder"
    external.mkdir(mode=0o700)
    hashes = {}
    for name in ["pal_train", "copy_train", "query_6", "query_8"]:
        raw = (source / (name + ".json")).read_bytes()
        original = json.loads(raw)
        records = []
        for old in original["records"]:
            record = copy.deepcopy(old)
            s = record["source"]
            text = s["text"]
            start = 0
            spans = []
            for token in record["tokens"]:
                where = text.encode().find(token.encode(), start)
                spans.append([where, where + len(token.encode())])
                start = spans[-1][1]
            assert (
                s["spans"] == spans
                and hashlib.sha256(text.encode()).hexdigest() == s["sha256"]
            )
            record["source"] = {k: s[k] for k in ["text", "sha256"]}
            record["source"].update(
                rights="ORIGINAL_TEST_FIXTURE supplied PATCH004",
                edition="PATCH004 sealed fixture/1",
            )
            records.append(record)
        save(target / (name + ".json"), records)
        hashes[name] = {
            "original_sha256": hashlib.sha256(raw).hexdigest(),
            "converted_digest": digest(records),
        }
    for n in [6, 8]:
        raw = (source / ("external_gold_" + str(n) + ".json")).read_bytes()
        (external / ("gold_" + str(n) + ".json")).write_bytes(raw)
        hashes["gold_" + str(n)] = {"sha256": hashlib.sha256(raw).hexdigest()}
    save(
        target / "PROTOCOL.json",
        {
            "schema": "recursive-observer-frozen-protocol/1",
            "source": "unchanged supplied PATCH004 fixtures",
            "hashes": hashes,
            "converted_source_spans_rechecked": True,
            "train_query_ids_disjoint": True,
            "label_holder": "external-only; not part of worker request or fit arguments",
            "selection": "full train compatibility, AST construction size, depth, canonical AST digest; no query labels",
            "P2_stop": "No long text/corpus run if short Dyck grammar has no new compatible operator observer",
        },
    )


def request(seed=137):
    return {
        "schema": "livingmath-symbolic-observer-synthesis-request/1",
        "task": {
            "mode": "context_relation_induction",
            "train_ref": "0" * 64,
            "predict_ref": "1" * 64,
            "holdout_labels_visible": False,
            "structure_levels": ["word"],
            "candidate_transformations": ["REVERSE", "RENAME"],
        },
        "feature_policy": {
            "enabled_builtins": [],
            "feature_denylist": ["pair_0_max", "pair_0_min", "pair_0_final"],
            "derive_relations": True,
            "prohibit_undocumented_builtins": True,
            "synthesis_origin_required": True,
            "renaming_scope": "per_variant",
            "strict_source_boundaries": True,
        },
        "search": {
            "seed": seed,
            "max_composition_depth": 4,
            "max_proposals": 128,
            "max_contexts": 128,
            "max_witnesses": 512,
            "max_cpu_ms": 4000,
        },
        "promotion_policy": {
            "mode": "compositional_ast",
            "candidate_sources": ["derivation_trace", "source_run_id"],
            "max_ast_nodes": 32,
            "max_ast_depth": 8,
            "max_recursion_steps": 8,
            "max_tokens": 8,
            "max_train_witnesses": 256,
            "require_independent_checker": True,
        },
    }


def score(predictions, labels):
    out = {"TP": 0, "TN": 0, "FP": 0, "FN": 0, "UNKNOWN": 0}
    for p in predictions:
        if p["score"] is None:
            out["UNKNOWN"] += 1
            continue
        y = labels[p["record_id"]]
        guess = p["score"] >= 0.5
        out["TP" if y and guess else "FN" if y else "FP" if guess else "TN"] += 1
    pos = out["TP"] + out["FN"]
    neg = out["TN"] + out["FP"]
    n = len(predictions)
    sensitivity = out["TP"] / sum(labels.values()) if any(labels.values()) else None
    specificity = (
        out["TN"] / (n - sum(labels.values())) if not all(labels.values()) else None
    )
    return {
        **out,
        "total": n,
        "accuracy": (out["TP"] + out["TN"]) / n,
        "sensitivity": sensitivity,
        "specificity": specificity,
        "balanced_accuracy": (sensitivity + specificity) / 2
        if sensitivity is not None and specificity is not None
        else None,
        "coverage": 1 - out["UNKNOWN"] / n,
        "majority_accuracy": max(sum(labels.values()), n - sum(labels.values())) / n,
    }


def run(fixture, out):
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    protocol = json.loads((fixture / "PROTOCOL.json").read_text())
    data = {}
    for name in ["pal_train", "copy_train", "query_6", "query_8"]:
        data[name] = json.loads((fixture / (name + ".json")).read_text())
        assert digest(data[name]) == protocol["hashes"][name]["converted_digest"]
    assert all(
        "accepted" not in r for name in ["query_6", "query_8"] for r in data[name]
    )
    assert {
        r["id"] for name in ["pal_train", "copy_train"] for r in data[name]
    }.isdisjoint(r["id"] for name in ["query_6", "query_8"] for r in data[name])
    pool = Executor()
    results = {}
    full = {}

    def job(name, train, queries, q):
        packet = {
            "action": "extension_run",
            "engine": "observer_synthesis_v1",
            "request": q,
            "resolved": {"train": train, "queries": queries},
        }
        result = pool.run(packet)
        save(out / (name + ".json"), result)
        full[name] = result["data"]
        model = result["data"]["model"]
        results[name] = {
            "status": model["synthesis_status"],
            "hypothesis_digest": model["hypothesis_digest"],
            "result_digest": digest(result["data"]),
            "feature_ids": model["used_feature_ids"],
            "metrics": result.get("metrics"),
            "worker_wall_s": result.get("worker_wall_s"),
        }
        print(name, model["synthesis_status"], flush=True)
        return model

    try:
        for kind in ["pal", "copy"]:
            seals = []
            for seed in [137, 42]:
                for n in [6, 8]:
                    name = f"{kind}-seed{seed}-n{n}"
                    model = job(
                        name,
                        data[kind + "_train"],
                        data["query_" + str(n)],
                        request(seed),
                    )
                    seals.append(model["hypothesis_digest"])
                    assert model["used_feature_ids"], name
                    feature = next(
                        f
                        for f in model["feature_registry"]
                        if f["feature_id"] in model["used_feature_ids"]
                    )
                    assert feature["verifier_result"]["status"] == "CHECKED_INSTANCE"
                    if seed == 137:
                        no = request()
                        no["feature_policy"]["derive_relations"] = False
                        job(
                            f"{kind}-no-derive-n{n}",
                            data[kind + "_train"],
                            data["query_" + str(n)],
                            no,
                        )
                        denied = request()
                        denied["feature_policy"]["feature_denylist"].append(
                            feature["feature_id"]
                        )
                        job(
                            f"{kind}-denied-n{n}",
                            data[kind + "_train"],
                            data["query_" + str(n)],
                            denied,
                        )
            assert seals[0] == seals[1] and seals[2] == seals[3]
        repeated = []
        for i in range(16):
            for old in data["pal_train"]:
                r = copy.deepcopy(old)
                r["id"] = str(i) + "-" + r["id"]
                repeated.append(r)
        m = job("train256-scope", repeated, data["query_6"][:1], request())
        f = next(
            f for f in m["feature_registry"] if f["feature_id"] in m["used_feature_ids"]
        )
        assert f["verifier_result"]["verified_witnesses"] == 256
    finally:
        pool.close()
    # This is the first access to gold in this process, after every inference.
    for kind in ["pal", "copy"]:
        for name, artifact in full.items():
            if not name.startswith(kind + "-"):
                continue
            n = 6 if name.endswith("n6") else 8
            gold_path = fixture / "external-label-holder" / ("gold_" + str(n) + ".json")
            raw = gold_path.read_bytes()
            assert (
                hashlib.sha256(raw).hexdigest()
                == protocol["hashes"]["gold_" + str(n)]["sha256"]
            )
            labels = json.loads(raw)["labels"][kind.upper()]
            results[name]["score"] = score(
                artifact["pairwise_eval"]["predictions"], labels
            )
    save(out / "RESULTS.json", results)
    print(json.dumps({k: v.get("score") for k, v in results.items()}))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["prepare", "run"])
    p.add_argument("--source", type=Path)
    p.add_argument("--fixture", type=Path, required=True)
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    if a.action == "prepare":
        prepare(a.source, a.fixture)
    else:
        run(a.fixture, a.output)
