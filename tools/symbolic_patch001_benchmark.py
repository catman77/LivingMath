"""External PATCH001 label holder: freeze first, grade separately, keep ambiguity."""

import argparse, copy, hashlib, json, random, statistics, time
from collections import Counter
from pathlib import Path
from lm_suti_assurance.core import digest, canonical
from lm_suti_assurance.symbolic.grammar import (
    fit,
    probability,
    prediction,
    tree_probability,
    baseline_fit,
    baseline_probability,
)
from lm_suti_assurance.symbolic.executor import Executor

TRAIN = [
    {"tokens": list(w), "accepted": label}
    for label, words in [
        (True, ["ABBA", "BAAB", "AAAA", "BBBB"]),
        (False, ["AABB", "BBAA", "ABAB", "BABA"]),
    ]
    for w in words
]
FIXED = [
    "ABCCBA",
    "ABCBCA",
    "ABCABC",
    "ABBAABBA",
    "AABBAA",
    "ABABBA",
    "BAABAB",
    "AAAAAA",
    "ABABAB",
]
ROOT = Path(__file__).resolve().parents[1]


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def serial(value):
    if isinstance(value, dict):
        return (
            [
                [serial(k), serial(v)]
                for k, v in sorted(value.items(), key=lambda kv: repr(kv[0]))
            ]
            if any(not isinstance(k, str) for k in value)
            else {k: serial(v) for k, v in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return [serial(v) for v in value]
    return value


def score(words, probs):
    labels = [w == list(reversed(w)) for w in words]
    correct = [(p >= 0.5) == y for p, y in zip(probs, labels)]
    pos = [i for i, y in enumerate(labels) if y]
    neg = [i for i, y in enumerate(labels) if not y]
    return {
        "correct": sum(correct),
        "total": len(words),
        "accuracy": sum(correct) / len(words),
        "balanced_accuracy": 0.5
        * (
            sum(correct[i] for i in pos) / len(pos)
            + sum(correct[i] for i in neg) / len(neg)
        ),
        "false_positive_rate": sum(probs[i] >= 0.5 for i in neg) / len(neg),
        "false_positive_words": ["".join(words[i]) for i in neg if probs[i] >= 0.5],
    }


def heldout(seed):
    rng = random.Random(550001 + seed)
    words = []
    for n in (6, 8, 10):
        for _ in range(10):
            while True:
                half = [rng.choice("ABCD") for _ in range(n // 2)]
                positive = half + list(reversed(half))
                if len(set(positive[1:-1])) > 1:
                    break
            negative = positive.copy()
            while negative == list(reversed(negative)):
                inside = negative[1:-1]
                rng.shuffle(inside)
                negative = negative[:1] + inside + negative[-1:]
            assert (
                Counter(positive) == Counter(negative)
                and positive[0] == negative[0]
                and positive[-1] == negative[-1]
            )
            words.extend([positive, negative])
    rng.shuffle(words)
    return words


def run(args):
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    protocol = {
        "train": TRAIN,
        "fixed_unique_words": FIXED,
        "seeds": list(range(20)),
        "OOD_lengths": [6, 8, 10],
        "samples_per_seed": 60,
        "family": "one supplied train corpus with randomized holdouts, not20 grammar discoveries",
        "label_visibility": "external holder only, after FROZEN_MODELS.json",
        "max_rules": 15,
        "max_probe_derivations": 64,
        "LLM_calls": 0,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    save(out / "FROZEN_PROTOCOL.json", protocol)
    old = json.loads(args.old_model.read_text())
    g = fit(TRAIN)
    frozen = copy.deepcopy(g)
    baselines = {
        k: baseline_fit(TRAIN, k) for k in ("unigram", "bigram", "simple_context")
    }
    save(
        out / "FROZEN_MODELS.json",
        {
            "current": g,
            "old_observed_endpoint_tree": old,
            "baselines": serial(baselines),
        },
    )
    words = [list(w) for w in FIXED]
    probs = [probability(g, w) for w in words]
    oldprobs = [tree_probability(old, w) for w in words]
    result = {
        "new_selected_candidate": score(words, probs),
        "old_observed_model": score(words, oldprobs),
        "family_decisions": [{"word": w, **prediction(g, list(w))} for w in FIXED],
        "hypothesis_digest": g["hypothesis_digest"],
        "candidate_status": g["candidate_status"],
        "identifiability_status": g["identifiability_status"],
    }
    assert (
        result["new_selected_candidate"]["correct"] == 9
        and result["old_observed_model"]["correct"] == 6
    )
    assert any(
        v["family_verdict"] == "INCONCLUSIVE" for v in result["family_decisions"]
    )
    save(out / "FIXED_HELDOUT_RESULTS.json", result)
    rows = []
    for seed in range(20):
        batch = heldout(seed)
        scores = {
            "current": score(batch, [probability(g, w) for w in batch]),
            "old_endpoint": score(batch, [tree_probability(old, w) for w in batch]),
        }
        for name, model in baselines.items():
            scores[name] = score(batch, [baseline_probability(model, w) for w in batch])
        row = {
            "seed": seed,
            "word_sha256": digest(batch),
            "scores": scores,
            "family_inconclusive": sum(
                prediction(g, w)["family_verdict"] == "INCONCLUSIVE" for w in batch
            ),
        }
        save(
            out / "heldout" / str(seed) / "test.json",
            {"words": batch, "labels": [w == list(reversed(w)) for w in batch]},
        )
        save(out / "heldout" / str(seed) / "scores.json", row)
        rows.append(row)
    assert g == frozen
    renamed = [
        {
            "tokens": [{"A": "X", "B": "Y"}[t] for t in s["tokens"]],
            "accepted": s["accepted"],
        }
        for s in TRAIN
    ]
    local = [
        {"tokens": [str(i) + ":" + t for t in s["tokens"]], "accepted": s["accepted"]}
        for i, s in enumerate(TRAIN)
    ]
    rename_checks = []
    for scope, data in [("global", renamed), ("local", local)]:
        model = fit(data, renaming_scope=scope)
        assert model["relational_rule_ast"] == g["relational_rule_ast"]
        predicted = [
            probability(
                model, [{"A": "X", "B": "Y", "C": "Z", "D": "W"}.get(t, t) for t in w]
            )
            >= 0.5
            for w in FIXED
        ]
        assert predicted == [p >= 0.5 for p in probs]
        rename_checks.append(
            {
                "scope": scope,
                "selected_structural_AST_equal": True,
                "decisions_equal": True,
            }
        )
    save(out / "RENAMING_CHECKS.json", rename_checks)
    active = []
    train = copy.deepcopy(TRAIN)
    model = g
    for step in range(2):
        probes = model["counterexample_candidates"]
        choice = next(
            (p for p in probes if len(set(p["candidate_predictions"].values())) > 1),
            None,
        )
        assert choice is not None
        tokens = choice["tokens"]
        label = tokens == list(reversed(tokens))
        before = model["hypothesis_digest"]
        updated = fit(train + [{"tokens": tokens, "accepted": label}])
        assert all(
            c["training_errors"] == 0 for c in updated["train_compatible_candidates"]
        )
        active.append(
            {
                "step": step,
                "frozen_before": before,
                "query": choice,
                "external_label": label,
                "after": updated["hypothesis_digest"],
                "compatible_candidates_before": len(
                    model["train_compatible_candidates"]
                ),
                "compatible_candidates_after": len(
                    updated["train_compatible_candidates"]
                ),
                "identifiability_status_after": updated["identifiability_status"],
            }
        )
        train.append({"tokens": tokens, "accepted": label})
        model = updated
    save(out / "ACTIVE_PROBE_CYCLE.json", active)
    pool = Executor()
    assert pool.status()["ready"]
    try:
        template = json.loads(
            (
                ROOT / "docs/LIVINGMATH_SYMBOLIC_V1/fixtures/mcp_request_example.json"
            ).read_text()
        )["request"]
        sat = copy.deepcopy(template)
        sat["source"].update(
            text="SSPPSPSP", sha256=hashlib.sha256(b"SSPPSPSP").hexdigest()
        )
        sat["search"].update(
            max_steps=128, max_nodes=256, max_word_tokens=64, history_identity="word"
        )
        a = pool.run({"action": "explore", "request": sat})["data"]
        sat["search"]["history_identity"] = "provenance"
        b = pool.run({"action": "explore", "request": sat})["data"]
        save(
            out / "SEARCH_DIAGNOSTICS.json",
            {
                "word": a["summary"],
                "certificate": a["search_diagnostics"],
                "provenance": b["summary"],
            },
        )
        source = json.loads(args.mallarme.read_text())["source"]
        assert (
            source["sha256"]
            == "fa7e64241104d5b195e9542f568a329937d11eb6a590f3af12870db63172c91a"
        )
        text = source["text"]
        letters = Counter(c for c in text if c.isascii() and c.isalpha())
        pair = next(
            (a, b)
            for a in sorted(letters)
            for b in sorted(letters)
            if a < b and letters[a] == letters[b]
        )
        translation = str.maketrans({pair[0]: pair[1], pair[1]: pair[0]})
        renamed_text = text.translate(translation)
        assert Counter(text) == Counter(renamed_text)
        sources = {
            "original": text,
            "line_permutation": "\n".join(reversed(text.split("\n"))),
            "equal_frequency_letter_bijection": renamed_text,
        }
        poetry = []
        initial = []
        for name, text in sources.items():
            req = copy.deepcopy(template)
            req["source"] = {
                **source,
                "text": text,
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
            }
            req["algebra"].update(kind="FREE", allow_reduce=False)
            req["operators"] = ["CONCAT", "SPLIT", "RENAME", "REVERSE"]
            req["observers"] = [
                "literal",
                "alpha_pattern",
                "adjacency",
                "substring_contexts",
                "composition",
                "hierarchy",
            ]
            req["segmentation"]["unit"] = "whitespace"
            req["search"].update(max_steps=16, max_nodes=256, max_word_tokens=128)
            value = pool.run({"action": "explore", "request": req})["data"]
            save(out / "mallarme" / name / "artifacts.json", value)
            initial.append(value["structural_observations"][0]["observers"])
            poetry.append(
                {
                    "control": name,
                    "source_sha256": req["source"]["sha256"],
                    "summary": value["summary"],
                    "layout_status": value["source_map"]["layout_status"],
                }
            )
        assert (
            initial[0]["literal"] != initial[1]["literal"]
            and initial[0]["composition"] != initial[1]["composition"]
        )
        assert initial[0]["alpha_pattern"] == initial[2]["alpha_pattern"]
        save(
            out / "MALLARME_CONTROLS.json",
            {
                "runs": poetry,
                "byte_offsets_preserved_by_same_width_ASCII_bijection": True,
                "literal_frequency_histogram_preserved": True,
                "letter_swap": pair,
                "literal_changed": True,
                "global_alpha_preserved": True,
                "line_permutation_composition_distinguished": True,
                "semantic_truth": "NOT_ASSESSED",
            },
        )
    finally:
        pool.close()
    summary = {
        "status": "PASS",
        "fixed_unique": result["new_selected_candidate"],
        "old_fixed_unique": result["old_observed_model"],
        "randomized_test_cases": sum(r["scores"]["current"]["total"] for r in rows),
        "mean_accuracy": {
            k: statistics.mean(r["scores"][k]["accuracy"] for r in rows)
            for k in rows[0]["scores"]
        },
        "seeds": 20,
        "family_status": "UNDERDETERMINED",
        "LLM_calls": 0,
        "execution_permission": False,
    }
    save(out / "SUMMARY.json", summary)
    save(
        out / "MANIFEST.json",
        {
            str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(out.rglob("*"))
            if p.is_file()
        },
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--old-model", type=Path, required=True)
    p.add_argument("--mallarme", type=Path, required=True)
    run(p.parse_args())
