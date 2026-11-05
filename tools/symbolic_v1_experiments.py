"""Independent sealed-data harness. The learner imports neither this file nor its generators."""

import argparse, copy, hashlib, json, math, random, statistics, time, resource
from collections import Counter, defaultdict
from pathlib import Path
from lm_suti_assurance.core import canonical, digest
from lm_suti_assurance.symbolic.grammar import (
    fit,
    probability,
    baseline_fit,
    baseline_probability,
)
from lm_suti_assurance.symbolic.state import (
    Atom,
    SymbolicState,
    History,
    apply,
    alpha_corpus,
    reduce_sp,
)
from lm_suti_assurance.symbolic.executor import Executor
from lm_suti_assurance.white_star.pool import Pool, prepare

ROOT = Path(__file__).resolve().parents[1]
MODELS = [
    "structural",
    "unigram",
    "bigram",
    "simple_context",
    "2d",
    "q",
    "adjacency",
    "without_alpha",
]
PROTOCOL = {
    "schema": "livingmath-symbolic-sealed-protocol/1",
    "seeds": list(range(20)),
    "families": ["periodic", "matching_endpoints", "balanced_prefixes"],
    "samples": {"train": 128, "validation": 64, "test": 128},
    "max_rules": 15,
    "max_features": 64,
    "max_thresholds_per_feature": 16,
    "decision_depth": 4,
    "lengths": {
        "periodic": [[4, 12], [14, 18], [20, 32]],
        "matching_endpoints": [[6, 12], [14, 18], [20, 32]],
        "balanced_prefixes": [[6, 14], [16, 20], [22, 32]],
    },
    "member_threshold": 0.5,
    "all_models_observe": "same raw opaque token train samples and labels; no test labels or generator",
    "test_rename": "periodic only: completely unseen bijective symbol IDs",
    "semantic_axes": False,
    "LLM_calls": 0,
    "upper_budget_per_fit": {
        "train_samples": 256,
        "features": 64,
        "rules": 15,
        "predicate_thresholds": 16,
    },
    "note": "Budgets are equal upper quotas and observation access, not identical measured CPU time. Baselines use fewer parameters; no padding computation.",
}


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def serial(value):
    if isinstance(value, dict):
        return (
            {
                "map_entries": [
                    [serial(k), serial(v)]
                    for k, v in sorted(value.items(), key=lambda kv: repr(kv[0]))
                ]
            }
            if any(not isinstance(k, str) for k in value)
            else {k: serial(v) for k, v in value.items()}
        )
    if isinstance(value, (tuple, list)):
        return [serial(v) for v in value]
    return value


def sample_pair(family, rng, n):
    if family == "periodic":
        positive = [i % 2 for i in range(n)]
        negative = positive.copy()
        while all(negative[i] != negative[i + 1] for i in range(n - 1)):
            rng.shuffle(negative)
    elif family == "matching_endpoints":
        positive = [rng.randrange(2) for _ in range(n)]
        positive[-1] = positive[0]
        choices = [i for i in range(1, n - 1) if positive[i] != positive[-1]]
        if not choices:
            return sample_pair(family, rng, n)
        negative = positive.copy()
        i = rng.choice(choices)
        negative[i], negative[-1] = negative[-1], negative[i]
    else:
        positive = []
        balance = 0
        for i in range(n):
            if balance == 0:
                c = 0
            elif balance == n - i:
                c = 1
            else:
                c = rng.randrange(2)
            positive.append(c)
            balance += 1 if c == 0 else -1
        negative = positive.copy()
        while True:
            rng.shuffle(negative)
            s = 0
            low = 0
            for c in negative:
                s += 1 if c == 0 else -1
                low = min(low, s)
            if low < 0:
                break
    assert len(positive) == len(negative) and Counter(positive) == Counter(negative)
    return positive, negative


def dataset(family, seed):
    rng = random.Random(18000 + seed * 113 + PROTOCOL["families"].index(family))
    mapping = ["atom-" + digest([seed, family, i])[:12] for i in range(2)]
    splits = {}
    for role, (low, high), size in zip(
        ("train", "validation", "test"), PROTOCOL["lengths"][family], (128, 64, 128)
    ):
        values = []
        for _ in range(size // 2):
            n = rng.choice(list(range(low, high + 1, 2)))
            positive, negative = sample_pair(family, rng, n)
            names = (
                ["hidden-" + digest([seed, i])[:12] for i in range(2)]
                if family == "periodic" and role == "test"
                else mapping
            )
            values.extend(
                [
                    {"tokens": [names[c] for c in positive], "accepted": True},
                    {"tokens": [names[c] for c in negative], "accepted": False},
                ]
            )
        rng.shuffle(values)
        splits[role] = values
    assert not {tuple(s["tokens"]) for s in splits["train"]} & {
        tuple(s["tokens"]) for s in splits["test"]
    }
    return splits


def train_models(train, measured=None):
    models = {}
    for name in MODELS:
        started_cpu = time.process_time()
        started_wall = time.perf_counter()
        if name in ("unigram", "bigram", "simple_context"):
            # A stronger repetition/context control explicitly uses local alpha tokens.
            observed = (
                [
                    {
                        "tokens": [str(v) for v in alpha_corpus([s["tokens"]])[0]],
                        "accepted": s["accepted"],
                    }
                    for s in train
                ]
                if name == "simple_context"
                else train
            )
            models[name] = baseline_fit(observed, name)
        else:
            models[name] = fit(
                train,
                15,
                ["adjacency"] if name == "without_alpha" else None,
                name if name in ("2d", "q", "adjacency") else "structural",
            )
        if measured is not None:
            measured[name] = {
                "fit_CPU_s": time.process_time() - started_cpu,
                "fit_wall_s": time.perf_counter() - started_wall,
                "process_peak_RSS_kib": resource.getrusage(
                    resource.RUSAGE_SELF
                ).ru_maxrss,
                "RSS_scope": "shared harness cumulative process peak, not isolated model allocation",
                "serialized_program_bytes": len(
                    canonical(serial(models[name])).encode()
                ),
            }
    return models


def predict(name, model, word):
    if name in ("unigram", "bigram", "simple_context"):
        if name == "simple_context":
            word = [str(v) for v in alpha_corpus([word])[0]]
        return baseline_probability(model, word)
    return probability(model, word)


def metrics(samples, scores):
    positive = [i for i, s in enumerate(samples) if s["accepted"]]
    negative = [i for i, s in enumerate(samples) if not s["accepted"]]
    correct = [(p >= 0.5) == s["accepted"] for p, s in zip(scores, samples)]
    return {
        "accuracy": sum(correct) / len(correct),
        "balanced_accuracy": 0.5
        * (
            sum(correct[i] for i in positive) / len(positive)
            + sum(correct[i] for i in negative) / len(negative)
        ),
        "false_positive_rate": sum(scores[i] >= 0.5 for i in negative) / len(negative),
        "membership_logloss": -sum(
            math.log(max(1e-12, min(1 - 1e-12, p if s["accepted"] else 1 - p)))
            for s, p in zip(samples, scores)
        )
        / len(samples),
    }


def token_model(train, order):
    counts = defaultdict(Counter)
    vocabulary = {t for s in train for t in s["tokens"]}
    vocabulary.add("<UNK>")
    for s in train:
        w = s["tokens"]
        for i, t in enumerate(w):
            counts[tuple(w[max(0, i - order + 1) : i])][t] += 1
    return counts, vocabulary


def token_nll(train, test, order):
    counts, vocab = token_model(train, order)
    loss = 0
    n = 0
    for s in test:
        w = [t if t in vocab else "<UNK>" for t in s["tokens"]]
        for i, t in enumerate(w):
            c = counts[tuple(w[max(0, i - order + 1) : i])]
            loss -= math.log((c[t] + 1) / (sum(c.values()) + len(vocab)))
            n += 1
    return loss / max(1, n)


def induced_nll(model, test):
    vocab = model["alphabet_roles"] + ["<UNK>"]
    loss = 0
    n = 0
    for s in test:
        w = [t if t in vocab else "<UNK>" for t in s["tokens"]]
        for i, t in enumerate(w):
            scores = [probability(model, w[:i] + [v]) for v in vocab]
            loss -= math.log(scores[vocab.index(t)] / sum(scores))
            n += 1
    return loss / max(1, n)


def bootstrap(values):
    rng = random.Random(7901)
    means = sorted(
        statistics.mean(rng.choices(values, k=len(values))) for _ in range(2000)
    )
    return [means[49], means[1949]]


def run(out):
    out.mkdir(parents=True, exist_ok=False)
    protocol = {
        **PROTOCOL,
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    save(out / "FROZEN_PROTOCOL.json", protocol)
    all_results = []
    efficiency = []
    freeze_events = []
    for family in PROTOCOL["families"]:
        for seed in PROTOCOL["seeds"]:
            folder = out / family / str(seed)
            data = dataset(family, seed)
            save(folder / "train.json", data["train"])
            save(folder / "validation.json", data["validation"])
            save(
                folder / "SEALED_COMMITMENT.json",
                {
                    "train_sha": digest(data["train"]),
                    "validation_sha": digest(data["validation"]),
                    "sealed_test_sha": digest(data["test"]),
                },
            )
            began = time.process_time()
            measured = {}
            models = train_models(data["train"], measured)
            elapsed = time.process_time() - began
            frozen = {name: serial(model) for name, model in models.items()}
            save(folder / "FROZEN_MODELS.json", frozen)
            model_hash = digest(frozen)
            freeze_events.append(
                {
                    "family": family,
                    "seed": seed,
                    "action": "MODELS_FROZEN",
                    "models_digest": model_hash,
                    "test_labels_visible_to_learner": False,
                }
            )
            # The scorer receives sealed data only after every model and digest have been written.
            save(folder / "TEST_REVEAL.json", data["test"])
            freeze_events.append(
                {
                    "family": family,
                    "seed": seed,
                    "action": "TEST_REVEALED",
                    "after_models_digest": model_hash,
                }
            )
            result = {
                "family": family,
                "seed": seed,
                "model_digest": model_hash,
                "data_hashes": {k: digest(v) for k, v in data.items()},
                "all_models_fit_CPU_s": elapsed,
                "per_model_cost": measured,
                "metrics": {},
                "validation": {},
                "next_token_nll": {},
                "budget": PROTOCOL["upper_budget_per_fit"],
                "train_unique_words": len({tuple(s["tokens"]) for s in data["train"]}),
            }
            predictions = {}
            for name, model in models.items():
                scores = [predict(name, model, s["tokens"]) for s in data["test"]]
                result["metrics"][name] = metrics(data["test"], scores)
                predictions[name] = scores
                result["validation"][name] = metrics(
                    data["validation"],
                    [predict(name, model, s["tokens"]) for s in data["validation"]],
                )
            for order, name in ((1, "unigram"), (2, "bigram"), (3, "simple_context")):
                result["next_token_nll"][name] = token_nll(
                    data["train"], data["test"], order
                )
            result["next_token_nll"]["structural_membership_induced"] = induced_nll(
                models["structural"], data["test"]
            )
            result["nll_boundary"] = (
                "structural distribution is normalized membership(prefix+token), not a generative grammar or a semantic likelihood"
            )
            assert (
                digest({name: serial(model) for name, model in models.items()})
                == model_hash
            ), "MODEL_CHANGED_AFTER_REVEAL"
            permuted = fit(list(reversed(data["train"])))
            result["train_order_invariant"] = permuted == models["structural"]
            assert result["train_order_invariant"]
            save(folder / "predictions.json", predictions)
            save(folder / "result.json", result)
            all_results.append(result)
            if seed < 3:
                for size in (16, 32, 64, 128):
                    model = fit(data["train"][:size])
                    efficiency.append(
                        {
                            "family": family,
                            "seed": seed,
                            "train_samples": size,
                            "test_balanced_accuracy": metrics(
                                data["test"],
                                [probability(model, s["tokens"]) for s in data["test"]],
                            )["balanced_accuracy"],
                        }
                    )
            print(
                "DONE",
                family,
                seed,
                round(result["metrics"]["structural"]["balanced_accuracy"], 3),
                flush=True,
            )
    save(out / "FREEZE_REVEAL_EVENTS.json", freeze_events)
    save(out / "PER_SEED_RESULTS.json", all_results)
    save(out / "SAMPLE_EFFICIENCY.json", efficiency)
    summary = {}
    for family in PROTOCOL["families"]:
        rows = [r for r in all_results if r["family"] == family]
        means = {
            name: statistics.mean(r["metrics"][name]["balanced_accuracy"] for r in rows)
            for name in MODELS
        }
        best = max(("unigram", "bigram", "simple_context"), key=lambda n: means[n])
        delta = [
            r["metrics"]["structural"]["balanced_accuracy"]
            - r["metrics"][best]["balanced_accuracy"]
            for r in rows
        ]
        ci = bootstrap(delta)
        summary[family] = {
            "seeds": 20,
            "mean_balanced_accuracy": means,
            "std_balanced_accuracy": {
                n: statistics.stdev(r["metrics"][n]["balanced_accuracy"] for r in rows)
                for n in MODELS
            },
            "best_simple_baseline": best,
            "paired_gain": statistics.mean(delta),
            "paired_bootstrap_95_CI": ci,
            "predictive_gain": (
                "EVIDENCE_OF_FINITE_STRUCTURAL_GAIN"
                if statistics.mean(delta) >= 0.05 and ci[0] > 0
                else "NO_EVIDENCE_OF_GAIN"
            ),
        }
    save(out / "SUMMARY.json", summary)
    g4 = fit([{"tokens": list(w), "accepted": True} for w in ("AB", "AABB")])
    assert g4["status"] == "UNDERDETERMINED"
    save(out / "G4_UNDERDETERMINED.json", g4)
    # Exact ablations C/G: membership in a declared quotient, not raw metric equality.
    history = History()
    s = SymbolicState(tuple(Atom(t, ()) for t in "SSPP"))
    a = history.add(s, (), "SOURCE", {})
    inserted, _ = apply(s, "INSERT_CANCEL_PAIR", {"position": 2, "kind": "SP"})
    b = history.add(
        inserted[0], [a], "INSERT_CANCEL_PAIR", {"position": 2, "kind": "SP"}
    )
    reduced, events = apply(inserted[0], "REDUCE_SP", {})
    c = history.add(reduced[0], [b], "REDUCE_SP", {}, events)
    empty = SymbolicState(())
    z = history.add(empty, (), "SOURCE", {})
    save(
        out / "EXACT_ABLATIONS.json",
        {
            "A_q_collision": {
                "left": "SSPP",
                "right": "SPSP",
                "same_q": True,
                "different_literal": True,
            },
            "C_global_vs_local": {
                "left": ["AB", "AB"],
                "right": ["AB", "CD"],
                "local_equal": alpha_corpus(["AB", "AB"], "local")
                == alpha_corpus(["AB", "CD"], "local"),
                "global_equal": alpha_corpus(["AB", "AB"])
                == alpha_corpus(["AB", "CD"]),
            },
            "G_history_vs_word": {
                "same_final_word_hash": history.states[c].word_hash
                == history.states[z].word_hash,
                "different_operation_node_ids": c != z,
                "nodes": list(history.nodes.values()),
            },
            "B_D_F": "paired predictive metrics in PER_SEED_RESULTS.json: adjacency, without_alpha, 2d",
        },
    )
    assert prepare()["ready"]
    executor = Executor()
    numerical = Pool()
    try:
        search_ablations = []
        template = json.loads(
            (
                ROOT / "docs/LIVINGMATH_SYMBOLIC_V1/fixtures/mcp_request_example.json"
            ).read_text()
        )["request"]
        for seed in PROTOCOL["seeds"]:
            pair = {}
            for strategy in ("local_structural_novelty", "random_local"):
                req = copy.deepcopy(template)
                req["search"].update(
                    seed=seed, max_steps=32, max_nodes=1024, strategy=strategy
                )
                response = executor.run({"action": "explore", "request": req})
                pair[strategy] = {
                    "input_digest": digest(req),
                    "result_digest": digest(response["data"]),
                    "summary": response["data"]["summary"],
                }
            search_ablations.append(
                {"seed": seed, "same_upper_budget": True, "runs": pair}
            )
        save(out / "E_UDAV_RANDOM_SEARCH.json", search_ablations)
        # Actual old numerical source: identical length/position encoding, different literal histories.
        controls = []
        for words in (
            ["ABBA", "BAAB", "ABAB", "BABA"],
            ["AABB", "BBAA", "ABAB", "BABA"],
        ):
            req = json.loads(
                (
                    ROOT
                    / "docs/LEVINMAS_WHITESTAR_MCP_001/fixtures/original_request.json"
                ).read_text()
            )
            text = "\n".join(words)
            raw = text.encode()
            req["encoding"]["source"].update(
                text=text,
                sha256=hashlib.sha256(raw).hexdigest(),
                title="Lossy position-length control",
            )
            for i, (concept, w) in enumerate(zip(req["encoding"]["concepts"], words)):
                start = sum(len(x.encode()) + 1 for x in words[:i])
                concept.update(
                    label=w,
                    coordinates=[i + 1, len(w)],
                    evidence=[
                        {
                            "line": i + 1,
                            "byte_start": start,
                            "byte_end": start + len(w.encode()),
                            "quote": w,
                        }
                    ],
                )
            req["encoding"]["protocol"]["steps"] = 32
            reply = numerical.run({"action": "explore", "request": req})["data"]
            controls.append(
                {
                    "source": req["encoding"]["source"],
                    "trace_digest": digest(reply["trace"]),
                    "summary": reply["summary"],
                }
            )
        assert controls[0]["trace_digest"] == controls[1]["trace_digest"]
        save(out / "ACTUAL_OLD_2D_COLLISION.json", controls)
        poetry = []
        for name in ("mallarme", "nostradamus"):
            source = json.loads(
                (ROOT / "docs/symbolic-v1/sources" / (name + ".json")).read_text()
            )
            req = copy.deepcopy(template)
            req["source"] = source
            req["algebra"].update(kind="FREE", allow_reduce=False)
            req["operators"] = ["CONCAT", "SPLIT", "RENAME", "REVERSE", "SUBSTITUTE"]
            req["observers"] = [
                "literal",
                "alpha_pattern",
                "adjacency",
                "substring_contexts",
                "composition",
                "hierarchy",
            ]
            req["segmentation"]["unit"] = "whitespace"
            req["search"].update(max_steps=32, max_nodes=1024, max_word_tokens=1024)
            response = executor.run({"action": "explore", "request": req})
            result = response["data"]
            lines = source["text"].splitlines()
            train = [{"tokens": list(line), "accepted": True} for line in lines[:4]]
            heldout = [{"tokens": list(line), "accepted": True} for line in lines[4:]]
            g = fit(train)
            record = {
                "author": name,
                "source_sha256": source["sha256"],
                "edition": source["edition"],
                "url": source["url"],
                "layout_status": "UNAVAILABLE",
                "result_digest": digest(result),
                "summary": result["summary"],
                "train_lines": [1, 4],
                "heldout_lines": [5, 8],
                "hypothesis_digest": g["hypothesis_digest"],
                "grammar_status": g["status"],
                "heldout_membership_predictions": [
                    probability(g, s["tokens"]) for s in heldout
                ],
                "membership_accuracy": "NOT_ASSESSED_NO_NATURAL_GRAMMAR_ORACLE",
                "heldout_next_token_nll": {
                    str(order): token_nll(train, heldout, order) for order in (1, 2, 3)
                },
                "LLM_calls": 0,
                "source_extraction": "French edition transcription; footnote markers omitted, inline drop cap Estant joined; no spelling variants substituted; UTF-8 text/hash frozen separately",
            }
            save(out / "poetry" / name / "artifacts.json", result)
            save(out / "poetry" / name / "evaluation.json", record)
            poetry.append(record)
        save(out / "POETRY_SUMMARY.json", poetry)
    finally:
        executor.close()
        numerical.close()
    rows = [
        "# Blind grammar comparison",
        "",
        "| Family | Structural BA | Unigram | Bigram | Context | Lossy 2D | Paired gain / 95% CI |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for name, s in summary.items():
        m = s["mean_balanced_accuracy"]
        rows.append(
            f"| {name} | {m['structural']:.4f} | {m['unigram']:.4f} | {m['bigram']:.4f} | {m['simple_context']:.4f} | {m['2d']:.4f} | {s['paired_gain']:.4f} / {s['paired_bootstrap_95_CI']} |"
        )
    (out / "RESULTS_TABLE.md").write_text("\n".join(rows) + "\n")
    save(
        out / "MANIFEST.json",
        {
            str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(out.rglob("*"))
            if p.is_file()
        },
    )
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    run(parser.parse_args().output)
