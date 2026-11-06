"""Seal original84-word inputs and independent external labels; no runtime oracle."""

import argparse, hashlib, json, itertools
from pathlib import Path
from lm_suti_assurance.core import digest


def record(tokens, label=None, prefix="q"):
    text = " ".join(tokens)
    r = {
        "id": prefix + "-" + digest(tokens)[:20],
        "tokens": list(tokens),
        "source": {
            "text": text,
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "rights": "ORIGINAL_TEST_FIXTURE",
            "edition": "ROLE006 sealed/1",
        },
    }
    if label is not None:
        r["accepted"] = label
    return r


def expected(tokens, opener="S", closer="P"):
    level = 0
    for x in tokens:
        level += 1 if x == opener else -1 if x == closer else -10000
        if level < 0:
            return False
    return level == 0


def prepare(source, out):
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    packet = json.loads(source.read_text())
    train = packet["resolved"]["train"]
    queries = packet["resolved"]["queries"]
    assert (
        len(train) == 84
        and len(queries) == 256
        and sum(r["accepted"] for r in train) == 8
        and all("accepted" not in r for r in queries)
    )
    assert all(r["accepted"] == expected(r["tokens"]) for r in train)
    data = {
        "train": train,
        "queries": queries,
        "minimal": [record(list("SP"), True, "tr"), record(list("PS"), False, "tr")],
        "branch_train": [
            record(list("PS"), False, "tr"),
            record(list("SSPPSP"), True, "tr"),
        ],
        "probes": [record(list(w)) for w in ["SP", "PS", "SSPPSP", "", "SSSSPPPP"]],
    }
    # Complete concatenation universe for all prefix/suffix horizons<=6, including EPS.
    data["continuations"] = [
        record(list(w), prefix="p1")
        for n in range(13)
        for w in itertools.product("SP", repeat=n)
    ]
    gold = {
        "holdout": {r["id"]: expected(r["tokens"]) for r in queries},
        "continuations": {
            r["id"]: expected(r["tokens"]) for r in data["continuations"]
        },
    }
    for name, value in [("inputs.json", data), ("external-gold.json", gold)]:
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    manifest = {
        "schema": "role006-frozen-protocol/1",
        "files": {
            n: hashlib.sha256((out / n).read_bytes()).hexdigest()
            for n in ["inputs.json", "external-gold.json"]
        },
        "source_train_ref": packet["request"]["task"]["train_ref"],
        "source_query_ref": packet["request"]["task"]["predict_ref"],
        "P1_unique_concatenations": len(data["continuations"]),
        "gold_not_passed_to_runtime": True,
        "selection": "train only; structural anchored/size/hash tie-break; two seeds; full query gold loaded after inference",
    }
    (out / "PROTOCOL.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    prepare(a.source, a.output)
