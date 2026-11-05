"""Train-only bounded relation induction. No grammar generators or heldout labels here."""

from collections import Counter, defaultdict
import math
from ..core import digest
from .state import alpha, require


def features(word, alphabet, observers=None):
    enabled = set(
        observers
        or [
            "alpha_pattern",
            "adjacency",
            "substring_contexts",
            "composition",
            "sp_reduce",
        ]
    )
    n = len(word)
    out = {"length": n, "length_mod_2": n % 2}
    if "alpha_pattern" in enabled:
        out["distinct_atoms"] = len(set(word))
        out["endpoint_equal"] = int(n > 0 and word[0] == word[-1])
        for gap in range(1, 5):
            out["lag_" + str(gap) + "_mismatches"] = sum(
                word[i] != word[i + gap] for i in range(max(0, n - gap))
            )
    if "adjacency" in enabled:
        out["adjacent_equal"] = sum(a == b for a, b in zip(word, word[1:]))
    if "composition" in enabled:
        # Generic pair-count observations, for train alphabet roles only: not a built-in parser.
        for left, right in zip(alphabet[:4], alphabet[1:5]):
            balance = 0
            values = [0]
            for t in word:
                balance += int(t == left) - int(t == right)
                values.append(balance)
            key = "pair_" + str(alphabet.index(left))
            out[key + "_final"] = balance
            out[key + "_min"] = min(values)
            out[key + "_max"] = max(values)
    return out


def contexts(samples):
    observed = defaultdict(dict)
    for i, s in enumerate(samples):
        w = s["tokens"]
        for k, t in enumerate(w):
            context = (tuple(w[max(0, k - 2) : k]), tuple(w[k + 1 : k + 3]))
            observed[t].setdefault(context, []).append([i, s["accepted"]])
    records = []
    for a in sorted(observed):
        for b in sorted(observed):
            if a >= b:
                continue
            shared = sorted(set(observed[a]) & set(observed[b]))
            witness = []
            counter = []
            for context in shared[:32]:
                l = {v for _, v in observed[a][context]}
                r = {v for _, v in observed[b][context]}
                entry = {
                    "context": [list(x) for x in context],
                    "left_train": observed[a][context],
                    "right_train": observed[b][context],
                }
                (witness if l == r else counter).append(entry)
            records.append(
                {
                    "left": a,
                    "right": b,
                    "relation": "finite_context_compatibility",
                    "kind": "empirical",
                    "K": len(shared[:32]),
                    "support": witness,
                    "counterexamples": counter,
                    "status": (
                        "COMPATIBLE_ON_OBSERVED_K"
                        if witness and not counter
                        else "DISTINGUISHED" if counter else "UNDERDETERMINED"
                    ),
                }
            )
            if len(records) >= 32:
                return records
    return records


def fit(samples, max_rules=15, observers=None, feature_mode="structural"):
    require(0 < len(samples) <= 256, "TRAIN_REQUIRED")
    samples = sorted(samples, key=digest)
    labels = {}
    for s in samples:
        key = tuple(s["tokens"])
        require(
            key not in labels or labels[key] == s["accepted"], "CONTRADICTORY_TRAINING"
        )
        labels[key] = s["accepted"]
    alphabet = sorted({t for s in samples for t in s["tokens"]})
    require(len(alphabet) <= 256, "ALPHABET_LIMIT")
    vectors = [features(s["tokens"], alphabet, observers) for s in samples]
    if feature_mode == "2d":
        vectors = [{k: v[k] for k in ("length", "adjacent_equal")} for v in vectors]
    if feature_mode == "q":
        vectors = [{"count_difference": v.get("pair_0_final", 0)} for v in vectors]
    if feature_mode == "adjacency":
        vectors = [{"adjacent_equal": v.get("adjacent_equal", 0)} for v in vectors]
    names = sorted(vectors[0])
    remaining = [max_rules]

    def grow(indices, depth=0):
        counts = Counter(samples[i]["accepted"] for i in indices)
        p = (counts[True] + 1) / (len(indices) + 2)
        leaf = {
            "probability": p,
            "accepted": p >= 0.5,
            "support_train_ids": indices,
            "kind": "empirical",
        }
        if len(counts) < 2 or depth >= 4 or remaining[0] < 3:
            return leaf
        parent_error = min(counts.values())
        best = None
        for name in names:
            values = sorted({vectors[i][name] for i in indices})
            # At most 16 train-derived thresholds per predicate; no unseen grammar enumeration.
            thresholds = values[:-1]
            if len(thresholds) > 16:
                thresholds = [
                    thresholds[int(j * (len(thresholds) - 1) / 15)] for j in range(16)
                ]
            for threshold in thresholds:
                left = [i for i in indices if vectors[i][name] <= threshold]
                right = [i for i in indices if vectors[i][name] > threshold]
                if not left or not right:
                    continue
                a = Counter(samples[i]["accepted"] for i in left)
                b = Counter(samples[i]["accepted"] for i in right)
                error = sum(min(c.get(False, 0), c.get(True, 0)) for c in (a, b))
                impurity = sum(
                    len(part)
                    * (1 - sum((c.get(v, 0) / len(part)) ** 2 for v in (False, True)))
                    for c, part in ((a, left), (b, right))
                )
                candidate = (error, impurity, name, threshold, left, right)
                if best is None or candidate[:4] < best[:4]:
                    best = candidate
        if best is None or (best[0] >= parent_error and depth >= 2):
            return leaf
        _, _, name, value, left, right = best
        remaining[0] -= 2
        return {
            "predicate": name,
            "threshold": value,
            "left": grow(left, depth + 1),
            "right": grow(right, depth + 1),
            "support_train_ids": indices,
            "kind": "empirical",
        }

    tree = grow(list(range(len(samples))))
    positives = [s["tokens"] for s in samples if s["accepted"]]
    known = {tuple(s["tokens"]) for s in samples}
    token = alphabet[0] if alphabet else "opaque-0"
    witness = [token]
    while tuple(witness) in known:
        witness.append(token)
    competing = [
        {"formalism": "finite_membership_set", "accepted_words": positives},
        {"formalism": "finite_membership_set", "accepted_words": positives + [witness]},
    ]
    hypothesis = {
        "schema": "livingmath-symbolic-grammar/1",
        "status": (
            "UNDERDETERMINED"
            if len(samples) < 8 or len(set(labels.values())) < 2
            else "EMPIRICAL"
        ),
        "formalism": "bounded_observed_relation_tree",
        "train_digest": digest(samples),
        "train_samples": samples,
        "alphabet_roles": alphabet,
        "observers": observers,
        "feature_mode": feature_mode,
        "tree": tree,
        "context_relations": contexts(samples),
        "identifiability": "FINITE_TRAIN_DOES_NOT_IDENTIFY_UNIQUE_GRAMMAR",
        "competing_train_compatible_models": competing,
        "distinguishing_word": witness,
        "distinguishing_predictions": [False, True],
        "max_rules": max_rules,
        "execution_permission": False,
    }
    hypothesis["hypothesis_digest"] = digest(hypothesis)
    return hypothesis


def probability(model, word):
    v = features(word, model["alphabet_roles"], model["observers"])
    mode = model["feature_mode"]
    if mode == "q":
        v = {"count_difference": v.get("pair_0_final", 0)}
    if mode == "adjacency":
        v = {"adjacent_equal": v.get("adjacent_equal", 0)}
    node = model["tree"]
    while "predicate" in node:
        node = (
            node["left"] if v[node["predicate"]] <= node["threshold"] else node["right"]
        )
    return node["probability"]


def baseline_fit(samples, kind):
    # Generative class models use exactly the same train samples and no test vocabulary.
    counts = {False: Counter(), True: Counter()}
    totals = {False: 0, True: 0}
    vocabulary = set()
    for s in samples:
        events = events_for(s["tokens"], kind)
        counts[s["accepted"]].update(events)
        totals[s["accepted"]] += len(events)
        vocabulary.update(events)
    return {
        "kind": kind,
        "counts": counts,
        "totals": totals,
        "vocabulary_size": len(vocabulary) + 1,
        "train_digest": digest(samples),
    }


def events_for(word, kind):
    if kind == "unigram":
        return list(word) or ["<empty>"]
    w = ["<bos>"] + list(word) + ["<eos>"]
    width = 2 if kind == "bigram" else 3
    return [tuple(w[max(0, i - width + 1) : i + 1]) for i in range(1, len(w))]


def baseline_probability(model, word):
    events = events_for(word, model["kind"])
    scores = []
    for label in (False, True):
        counts = model["counts"][label]
        total = model["totals"][label]
        v = model["vocabulary_size"]
        scores.append(
            sum(math.log((counts[event] + 1) / (total + v)) for event in events)
        )
    delta = max(-60, min(60, scores[0] - scores[1]))
    return 1 / (1 + math.exp(delta))
