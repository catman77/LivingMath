import math

"""External label holder. Freeze real sources/splits before any worker inference."""

import argparse, copy, hashlib, json, re, random
from pathlib import Path
from collections import Counter
from itertools import product
from lm_suti_assurance.core import digest
from lm_suti_assurance.observer_synthesis.features import encode
from lm_suti_assurance.symbolic.executor import Executor


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def source_record(name, lines, edition, rights, metadata, pair_id=None, label=None):
    text = "\n".join(lines)
    raw = text.encode()
    segments = [
        {
            "id": "century",
            "parent_id": None,
            "kind": "century",
            "byte_start": 0,
            "byte_end": len(raw),
        },
        {
            "id": "quatrain",
            "parent_id": "century",
            "kind": "quatrain",
            "byte_start": 0,
            "byte_end": len(raw),
        },
    ]
    offset = 0
    tokens = []
    for i, line in enumerate(lines):
        end = offset + len(line.encode())
        ident = "line" + str(i)
        segments.append(
            {
                "id": ident,
                "parent_id": "quatrain",
                "kind": "line",
                "byte_start": offset,
                "byte_end": end,
            }
        )
        for j, m in enumerate(re.finditer(r"\S+", line)):
            tokens.append(m.group())
            segments.append(
                {
                    "id": ident + "word" + str(j),
                    "parent_id": ident,
                    "kind": "word",
                    "byte_start": offset + len(line[: m.start()].encode()),
                    "byte_end": offset + len(line[: m.end()].encode()),
                }
            )
        offset = end + 1
    record = {
        "id": name,
        "tokens": tokens,
        "lines": [l.split() for l in lines],
        "source": {
            "text": text,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "edition": edition,
            "rights": rights,
        },
        "segments": segments,
        "metadata": metadata,
    }
    if pair_id is not None:
        record["pair_id"] = pair_id
    if label is not None:
        record["accepted"] = label
    return record


def request(representation="global_alpha", enabled=None):
    return {
        "schema": "livingmath-symbolic-observer-synthesis-request/1",
        "task": {
            "mode": "context_relation_induction",
            "train_ref": "0" * 64,
            "predict_ref": "1" * 64,
            "holdout_labels_visible": False,
            "structure_levels": ["word", "line", "quatrain", "century"],
            "candidate_transformations": ["SWAP_LINES_2_3"],
            "conflict_policy": "retain_as_empirical",
        },
        "feature_policy": {
            "enabled_builtins": (
                enabled
                if enabled is not None
                else [
                    "literal",
                    "alpha_pattern",
                    "adjacency",
                    "composition",
                    "substring_contexts",
                    "hierarchy",
                ]
            ),
            "prohibit_undocumented_builtins": True,
            "synthesis_origin_required": True,
            "renaming_scope": "per_variant",
            "strict_source_boundaries": True,
            "representation": representation,
            "derive_relations": True,
        },
        "search": {
            "seed": 137,
            "max_composition_depth": 4,
            "max_proposals": 128,
            "max_contexts": 256,
            "max_witnesses": 128,
            "max_cpu_ms": 4000,
        },
    }


def freeze(source_dir, out):
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    poems = []
    sources = []
    anomalies = []
    for file in sorted(source_dir.glob("*.json")):
        data = json.loads(file.read_text())
        source = data["input"]["source"]
        row = data["archive_fixture"]
        century = int(row["century"])
        start = 1 if row["quatrains"].startswith("1") else 51
        text = source["text"]
        assert hashlib.sha256(text.encode()).hexdigest() == source["sha256"]
        matches = list(re.finditer(r"[^\n]+(?:\n[^\n]+)*", text))
        assert len(matches) == (42 if century == 7 else 50)
        sources.append(
            {
                "run_id": row["run_id"],
                "source_sha256": source["sha256"],
                "input_ref": data["record"]["input_ref"],
                "century": century,
                "edition": source["edition"],
                "rights": source["rights"],
            }
        )
        for j, m in enumerate(matches):
            number = start + j
            lines = m.group().splitlines()
            assert len(lines) == 4
            metadata = {
                "century": century,
                "quatrain": number,
                "parent_source_ref": data["record"]["input_ref"],
                "parent_byte_start": len(text[: m.start()].encode()),
                "parent_byte_end": len(text[: m.end()].encode()),
                "edition_confidence": "mixed archival first French reading; not a critical edition",
            }
            poems.append(
                {
                    "century": century,
                    "quatrain": number,
                    "lines": lines,
                    "metadata": metadata,
                    "edition": source["edition"],
                    "rights": source["rights"],
                }
            )
            bad = sorted(
                {
                    f"U+{ord(c):04X}"
                    for c in m.group()
                    if ord(c) < 32 or 127 <= ord(c) <= 159
                }
            )
            if bad or (century, number) in [(1, 51), (2, 32), (2, 38)]:
                anomalies.append(
                    {
                        "century": century,
                        "quatrain": number,
                        "known_editorial_anomaly": (century, number)
                        in [(1, 51), (2, 32), (2, 38)],
                        "control_codepoints_preserved": bad,
                    }
                )
    assert (
        len(poems) == 942 and len({(p["century"], p["quatrain"]) for p in poems}) == 942
    )
    train = []
    queries = []
    labels = {}
    encoding_counts = Counter()
    nonidentifiable = []
    rng = random.Random(137)
    for p in poems:
        c, n = p["century"], p["quatrain"]
        pair = digest(["pair", c, n])[:24]
        swapped = [p["lines"][i] for i in [0, 2, 1, 3]]
        variants = []
        for correct, lines in [(True, p["lines"]), (False, swapped)]:
            ident = digest(
                ["variant", pair, hashlib.sha256("\n".join(lines).encode()).hexdigest()]
            )[:32]
            r = source_record(
                ident,
                lines,
                p["edition"],
                p["rights"],
                p["metadata"],
                pair,
                correct if c <= 8 else None,
            )
            variants.append(r)
            if c > 8:
                labels[ident] = correct
        rng.shuffle(variants)
        (train if c <= 8 else queries).extend(variants)
        equal = {
            mode: encode(variants[0], mode)["signature"]
            == encode(variants[1], mode)["signature"]
            for mode in [
                "global_alpha",
                "local_alpha",
                "literal",
                "punctuation",
                "length",
            ]
        }
        equal["global_alpha_without_boundaries"] = (
            encode(variants[0], "global_alpha")["tokens"]
            == encode(variants[1], "global_alpha")["tokens"]
        )
        for mode, same in equal.items():
            encoding_counts[mode] += same
        if equal["global_alpha"]:
            nonidentifiable.append({"century": c, "quatrain": n, "pair_id": pair})
    assert len(train) == 1484 and len(queries) == 400 and len(labels) == 400
    save(out / "train.json", train)
    save(out / "queries.json", queries)
    holder = out / "external-label-holder"
    holder.mkdir(mode=0o700)
    save(holder / "labels.json", labels)
    protocol = {
        "schema": "patch003-preregistered-corpus-protocol/1",
        "source_kind": "19 immutable production inputs, no refetch/repair/translation",
        "sources": sources,
        "quatrains": 942,
        "century_counts": dict(Counter(p["century"] for p in poems)),
        "train_centuries": list(range(1, 9)),
        "test_centuries": [9, 10],
        "train_records": len(train),
        "query_records": len(queries),
        "train_digest": digest(train),
        "query_digest": digest(queries),
        "sealed_labels_digest": digest(labels),
        "representation_equal_pair_counts_all942": dict(encoding_counts),
        "global_alpha_nonidentifiable_pairs": nonidentifiable,
        "anomalies": anomalies,
        "metrics": [
            "pairwise_wins",
            "losses",
            "ties",
            "NOT_IDENTIFIABLE",
            "UNDERDETERMINED",
            "decided_accuracy",
            "expected_random_tie_credit_accuracy",
            "binary_confusion_on_decided",
            "abstention_coverage",
        ],
        "synthetic_label_boundary": "original versus SWAP_LINES_2_3 benchmark labels; not semantic negation",
        "budgets": request()["search"],
        "configs": [
            "global_alpha",
            "local_alpha",
            "literal",
            "punctuation",
            "length",
            "majority",
            "no_builtin_attempt",
            "strict_global_alpha",
        ],
    }
    save(out / "FROZEN_PROTOCOL.json", protocol)
    print(
        json.dumps(
            {
                "frozen": True,
                "quatrains": 942,
                "equal_pairs": dict(encoding_counts),
                "queries_contain_no_labels": all("accepted" not in r for r in queries),
            }
        )
    )


def score(evaluation, labels):
    counts = Counter()
    tp = tn = fp = fn = abstain = 0
    for pair in evaluation["pairs"]:
        status = pair["status"]
        counts[status] += 1
        if status == "PREFERENCE":
            counts["wins" if labels[pair["preferred_record_id"]] else "losses"] += 1
    for p in evaluation["predictions"]:
        if p["score"] is None:
            abstain += 1
            continue
        y = labels[p["record_id"]]
        guess = p["score"] >= 0.5
        if y and guess:
            tp += 1
        elif y:
            fn += 1
        elif guess:
            fp += 1
        else:
            tn += 1
    pairs = len(evaluation["pairs"])
    wins, losses = counts["wins"], counts["losses"]
    unresolved = pairs - wins - losses
    return {
        "pairs": pairs,
        "wins": wins,
        "losses": losses,
        "ties": counts["TIE"],
        "not_identifiable": counts["NOT_IDENTIFIABLE"],
        "underdetermined": counts["UNDERDETERMINED"],
        "decided_accuracy": wins / (wins + losses) if wins + losses else None,
        "expected_random_tie_credit_accuracy": (
            (wins + 0.5 * unresolved) / pairs if pairs else None
        ),
        "abstention_pair_coverage": unresolved / pairs if pairs else None,
        "binary_confusion_on_scored_records": {
            "TP": tp,
            "TN": tn,
            "FP": fp,
            "FN": fn,
            "unscored": abstain,
        },
        "balanced_accuracy_on_scored_records": (
            0.5 * (tp / (tp + fn) + tn / (tn + fp)) if tp + fn and tn + fp else None
        ),
        "MCC": (
            (tp * tn - fp * fn)
            / math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
            if (tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)
            else None
        ),
        "ordinary_accuracy_on_scored_records": (
            (tp + tn) / (tp + tn + fp + fn) if tp + tn + fp + fn else None
        ),
        "confidence": "No inferential interval claimed; one fixed historical corpus and synthetic permutation task.",
    }


def query_control(queries, name):
    output = []
    mapping = {}
    vocabulary = sorted({t for r in queries for t in r["tokens"]})
    rename = {t: "opaque" + str(i) for i, t in enumerate(vocabulary)}
    for record in queries:
        r = copy.deepcopy(record)
        if name == "provenance_control":
            r["id"] = digest(["new-lineage", record["id"]])[:32]
            r["pair_id"] = digest(["new-lineage", record["pair_id"]])[:24]
        elif name == "renaming_control":
            lines = [" ".join(rename[t] for t in line) for line in record["lines"]]
            r = source_record(
                record["id"],
                lines,
                record["source"]["edition"],
                record["source"]["rights"],
                record["metadata"],
                record["pair_id"],
            )
        elif name == "boundary_control":
            lines = copy.deepcopy(record["lines"])
            if lines[1]:
                lines[0].append(lines[1].pop(0))
            r = source_record(
                record["id"],
                [" ".join(l) for l in lines],
                record["source"]["edition"],
                record["source"]["rights"],
                record["metadata"],
                record["pair_id"],
            )
        mapping[r["id"]] = record["id"]
        output.append(r)
    return output, mapping


def research(frozen, out):
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    train = json.loads((frozen / "train.json").read_text())
    queries = json.loads((frozen / "queries.json").read_text())
    protocol = json.loads((frozen / "FROZEN_PROTOCOL.json").read_text())
    assert (
        digest(train) == protocol["train_digest"]
        and digest(queries) == protocol["query_digest"]
    )
    configurations = {
        name: request(name)
        for name in ["global_alpha", "local_alpha", "literal", "punctuation", "length"]
    }
    configurations["majority"] = request("literal", [])
    configurations["no_builtin_attempt"] = request("global_alpha")
    configurations["no_builtin_attempt"]["feature_policy"]["feature_allowlist"] = [
        "derived:*"
    ]
    configurations["strict_global_alpha"] = request("global_alpha")
    configurations["strict_global_alpha"]["task"]["conflict_policy"] = "report_only"
    configurations["conditional_global_alpha"] = request("global_alpha")
    configurations["conditional_global_alpha"]["task"][
        "conflict_policy"
    ] = "exclude_with_report"
    for name in ("punctuation", "length", "majority"):
        configurations[name]["feature_policy"]["derive_relations"] = False
    for control in [
        "renaming_control",
        "boundary_control",
        "provenance_control",
        "seed_control",
    ]:
        configurations[control] = request("global_alpha")
    configurations["seed_control"]["search"]["seed"] = 271
    save(out / "FROZEN_CONFIGURATIONS.json", configurations)
    save(
        out / "PROTOCOL_AMENDMENT.json",
        {
            "reason": "Train-only origin/encoding audit found representation-dependent exclusions; primary empirical runs retain all1484 labels and keep CONTRADICTORY_TRAINING. Conditional exclusion remains a secondary control. NOT_IDENTIFIABLE records abstain, never score as successful predictions.",
            "train_digest": digest(train),
            "query_digest": digest(queries),
            "same_primary_training_rows": 1484,
            "holdout_labels_used_to_choose_protocol": False,
        },
    )
    pool = Executor()
    assert pool.status()["ready"]
    results = {}
    try:
        for name, q in configurations.items():
            control_queries, mapping = (
                query_control(queries, name)
                if name
                in ("renaming_control", "boundary_control", "provenance_control")
                else (queries, {r["id"]: r["id"] for r in queries})
            )
            save(out / (name + ".label-map.json"), mapping)
            packet = {
                "action": "extension_run",
                "engine": "observer_synthesis_v1",
                "request": q,
                "resolved": {"train": train, "queries": control_queries},
            }
            try:
                response = pool.run(packet)
                data = response["data"]
                save(out / (name + ".artifacts.json"), data)
                save(out / (name + ".metrics.json"), response["metrics"])
                results[name] = {
                    "status": "INFERENCE_COMPLETED",
                    "hypothesis_digest": data["model"]["hypothesis_digest"],
                    "training_status": data["model"]["training_status"],
                    "synthesis_status": data["model"]["synthesis_status"],
                    "conflicting_encoding_groups": len(
                        data["model"]["training_conflicts"]
                    ),
                    "conditional_excluded_records": len(
                        data["model"]["excluded_record_refs"]
                    ),
                    "result_digest": digest(data),
                }
            except Exception as error:
                results[name] = {
                    "status": "FAIL",
                    "code": getattr(error, "code", type(error).__name__),
                    "message": str(error),
                }
            save(out / "INFERENCE_RESULTS.json", results)
            print(name, json.dumps(results[name]), flush=True)
    finally:
        pool.close()
    # This is the first read of the sealed labels, outside and after all workers.
    labels = json.loads((frozen / "external-label-holder/labels.json").read_text())
    assert digest(labels) == protocol["sealed_labels_digest"]
    for name, row in results.items():
        if row["status"] == "FAIL":
            continue
        data = json.loads((out / (name + ".artifacts.json")).read_text())
        mapping = json.loads((out / (name + ".label-map.json")).read_text())
        control_labels = {new: labels[old] for new, old in mapping.items()}
        row.update(status="SCORED", scores=score(data["pairwise_eval"], control_labels))
        save(out / "RESULTS.json", results)
    print(
        json.dumps(
            {
                "status": (
                    "PASS"
                    if all(r["status"] == "SCORED" for r in results.values())
                    else "FAIL"
                ),
                "results": results,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("freeze")
    p.add_argument("--source-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("run")
    p.add_argument("--frozen", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.source_dir, args.output)
    else:
        research(args.frozen, args.output)
