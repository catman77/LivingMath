"""Seal mixed-length fixtures; labels are external to all inference packets."""

import argparse, copy, hashlib, json
from itertools import product
from pathlib import Path
from lm_suti_assurance.core import digest


def record(tokens, label=None, prefix="tr"):
    text = " ".join(tokens)
    r = {
        "id": prefix + "-" + digest(tokens)[:20],
        "tokens": list(tokens),
        "source": {
            "text": text,
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "rights": "ORIGINAL_TEST_FIXTURE",
            "edition": "PATCH005 sealed/1",
        },
    }
    if label is not None:
        r["accepted"] = label
    return r


def prepare(historical, output):
    output.mkdir(mode=0o700, parents=True, exist_ok=False)

    def load(n):
        return json.loads((historical / (n + ".json")).read_text())["packet"][
            "resolved"
        ]["train"]

    base = load("PAL4_base")
    cases = {"B": base}
    for word in ["SS", "PP", "SP", "PS"]:
        cases["B_" + word] = (
            load("PAL4_plus_" + word)
            if (historical / ("PAL4_plus_" + word + ".json")).exists()
            else copy.deepcopy(base) + [record(list(word), word == word[::-1])]
        )
        assert [r for r in cases["B_" + word] if len(r["tokens"]) == 4] == base
    for name, old in [
        ("even24", "PAL_even24"),
        ("mix1234", "PAL_mix1234"),
        ("odd135", "PAL_odd135"),
        ("even246", "PAL_even246"),
        ("odd13", "PAL_odd13"),
        ("copy52", "COPY_52"),
    ]:
        cases[name] = load(old)
    cases["copy20"] = [
        record(w, w[: len(w) // 2] == w[len(w) // 2 :])
        for n in [2, 4]
        for w in product("SP", repeat=n)
    ]
    cases["mix126"] = [
        record(w, w == w[::-1]) for n in range(1, 7) for w in product("SP", repeat=n)
    ]
    queries = {
        str(n): [record(w, prefix="q" + str(n)) for w in product("SP", repeat=n)]
        for n in [6, 7, 8]
    }
    gold = {
        str(n): {
            kind: {
                r["id"]: r["tokens"] == r["tokens"][::-1]
                if kind == "mirror"
                else r["tokens"][: n // 2] == r["tokens"][n // 2 :] and n % 2 == 0
                for r in queries[str(n)]
            }
            for kind in ["mirror", "copy"]
        }
        for n in [6, 7, 8]
    }
    data = {"cases": cases, "queries": queries}
    (output / "inputs.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    )
    (output / "external-gold.json").write_text(json.dumps(gold, indent=2) + "\n")
    manifest = {
        "schema": "patch005-sealed-fixtures/1",
        "inputs_sha256": hashlib.sha256(
            (output / "inputs.json").read_bytes()
        ).hexdigest(),
        "external_gold_sha256": hashlib.sha256(
            (output / "external-gold.json").read_bytes()
        ).hexdigest(),
        "B_records_byte_equal": True,
        "missing_original_PS_run": "3019b940f764993de7d687569f1f0ee5c9ce4674a18790a343a725bae8e77c3",
        "PS_recreated_as_new_control": True,
        "query_labels_passed_to_worker": False,
    }
    (output / "PROTOCOL.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--historical", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    prepare(a.historical, a.output)
