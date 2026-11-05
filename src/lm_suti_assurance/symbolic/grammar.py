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


def fit(
    samples,
    max_rules=15,
    observers=None,
    feature_mode="structural",
    renaming_scope="global",
):
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
    enrich_relations(
        hypothesis, samples, max_rules, observers, feature_mode, renaming_scope
    )
    hypothesis["hypothesis_digest"] = digest(hypothesis)
    return hypothesis


def tree_probability(model, word):
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


def relation_value(ast: dict, word: list | tuple) -> bool:
    """Interpret only finite stored compositions of existing equality/SPLIT/REVERSE."""
    operation = ast["composition"]
    if operation == "all_observed_relations":
        return all(relation_value(part, word) for part in ast["relations"])
    if operation == "iterate_on_inner_fragment":
        fragment = tuple(word)
        while len(fragment) > ast["base_max_tokens"]:
            if not relation_value(ast["relation"], fragment):
                return False
            # Two SPLITs retain the inner fragment. Strictly decreasing length.
            fragment = fragment[ast["trim_left"] : len(fragment) - ast["trim_right"]]
        return True
    require(operation == "aligned_token_equality", "UNKNOWN_RELATION_COMPOSITION")
    offset = ast["offset"]
    if len(word) <= 2 * offset + 1:
        return True
    return (word[offset] == tuple(reversed(word))[offset]) == ast["expected_equal"]


def relation_trace(ast: dict, word: list | tuple) -> list:
    """Concrete positions/tokens justify operator evaluation, never infinite truth."""
    if ast["composition"] == "all_observed_relations":
        return [
            entry for part in ast["relations"] for entry in relation_trace(part, word)
        ]
    repeat = ast["composition"] == "iterate_on_inner_fragment"
    relation = ast["relation"] if repeat else ast
    left, right = 0, len(word)
    records = []
    while right - left > (
        ast["base_max_tokens"] if repeat else 2 * relation["offset"] + 1
    ):
        a, b = left + relation["offset"], right - 1 - relation["offset"]
        records.append(
            {
                "fragment_range": [left, right],
                "left_position": a,
                "right_position": b,
                "left_token": word[a],
                "right_token": word[b],
                "expected_equal": relation["expected_equal"],
                "matches": (word[a] == word[b]) == relation["expected_equal"],
                "operations": ["REVERSE", "SPLIT", "token_equality"],
            }
        )
        if not repeat or not records[-1]["matches"]:
            break
        left += ast["trim_left"]
        right -= ast["trim_right"]
    return records


def relational_candidates(
    samples: list, max_rules: int, observers: list | None
) -> tuple:
    enabled = set(observers or ["alpha_pattern", "composition", "substring_contexts"])
    if not {"alpha_pattern", "composition"} <= enabled:
        return [], [{"reason": "REQUIRED_RELATIONAL_OBSERVERS_ABSENT"}]
    positives = [(i, s) for i, s in enumerate(samples) if s["accepted"]]
    if not positives:
        return [], [{"reason": "NO_POSITIVE_RELATION_WITNESSES"}]
    available = [len(s["tokens"]) // 2 for _, s in positives if len(s["tokens"]) > 1]
    if not available:
        return [], [{"reason": "NO_TWO_POSITION_FRAGMENT"}]
    # Only observed alignments, bounded by rule quota; not a library of languages.
    guards = []
    proposals = []
    trace = []
    for offset in range(min(4, min(available), max_rules)):
        observed = {
            s["tokens"][offset] == s["tokens"][-1 - offset]
            for _, s in positives
            if len(s["tokens"]) > 2 * offset + 1
        }
        if len(observed) != 1:
            trace.append({"offset": offset, "reason": "POSITIVE_RELATION_NOT_SHARED"})
            continue
        guard = {
            "composition": "aligned_token_equality",
            "offset": offset,
            "expected_equal": observed.pop(),
            "left_operations": ["SPLIT"],
            "right_operations": ["REVERSE", "SPLIT"],
            "base_max_tokens": 2 * offset + 1,
        }
        guards.append(guard)
        proposals.append((guard, 4, 1))
    if (
        len(guards) >= 2
        and guards[0]["offset"] == 0
        and guards[1]["offset"] == 1
        and guards[0]["expected_equal"] == guards[1]["expected_equal"]
    ):
        proposals.append(
            (
                {
                    "composition": "iterate_on_inner_fragment",
                    "relation": guards[0],
                    "trim_left": 1,
                    "trim_right": 1,
                    "fragment_operations": ["SPLIT", "SPLIT"],
                    "base_max_tokens": 1,
                },
                8,
                2,
            )
        )
        proposals.append(
            ({"composition": "all_observed_relations", "relations": guards[:2]}, 9, 2)
        )
    retained = []
    for ast, size, coverage in proposals[: min(64, 4 * max_rules)]:
        if size > max_rules:
            trace.append(
                {
                    "ast_digest": digest(ast),
                    "reason": "MAX_RULES",
                    "required_nodes": size,
                }
            )
            continue
        decisions = [relation_value(ast, s["tokens"]) for s in samples]
        failures = [
            i for i, (p, s) in enumerate(zip(decisions, samples)) if p != s["accepted"]
        ]
        witnesses = [
            {
                "train_id": i,
                "input_pointer": "/grammar_hypotheses/0/train_samples/"
                + str(i)
                + "/tokens",
                "train_sample_digest": digest(s),
                "tokens": s["tokens"],
                "supplied_membership": s["accepted"],
                "operator_decision": decisions[i],
                "positions": relation_trace(ast, s["tokens"]),
            }
            for i, s in enumerate(samples[:16])
        ]
        trace.append(
            {
                "ast": ast,
                "ast_digest": digest(ast),
                "tested_train_samples": len(samples),
                "counterexample_train_ids": failures[:16],
                "status": "TRAIN_COMPATIBLE" if not failures else "REJECTED_BY_TRAIN",
            }
        )
        if not failures:
            retained.append(
                {
                    "candidate_id": digest(ast),
                    "formalism": "observed_relation_composition",
                    "ast": ast,
                    "candidate_status": "EMPIRICAL",
                    "training_errors": 0,
                    "relation_coverage": coverage,
                    "hypothesis_complexity": {
                        "ast_nodes": size,
                        "ast_depth": (
                            3 if ast["composition"] == "aligned_token_equality" else 4
                        ),
                    },
                    "rule_witnesses": witnesses,
                }
            )
    return retained, trace


def candidate_decision(model: dict, candidate: dict, word: list | tuple) -> bool:
    if candidate["formalism"] == "observed_relation_composition":
        return relation_value(candidate["ast"], word)
    return tree_probability(model, word) >= 0.5


def active_probes(model: dict, candidates: list, samples: list) -> list:
    """At most64 local train-derived mutations; labels/predict queries unavailable."""
    if len(candidates) < 2:
        return [
            {
                "tokens": model["distinguishing_word"],
                "kind": "membership_query",
                "label": "REQUIRED_FROM_EXTERNAL_HOLDER",
                "candidate_predictions": {
                    "finite_observed_membership_set": False,
                    "finite_set_plus_distinguishing_word": True,
                },
                "scope": "two explicit finite train-compatible countermodels retained in competing_train_compatible_models",
            }
        ]
    known = {tuple(s["tokens"]) for s in samples}
    seen = set()
    probes = []
    attempts = 0
    alphabet = []
    for s in samples:
        for token in s["tokens"]:
            if token not in alphabet:
                alphabet.append(token)
    alphabet = alphabet[:2]
    for index, sample in enumerate(samples[:16]):
        word = sample["tokens"]
        n = len(word)
        proposals = []
        for position in sorted({0, max(0, n - 1), n // 2}):
            if position < n:
                for token in alphabet:
                    proposals.append(
                        (
                            word[:position] + [token] + word[position + 1 :],
                            {
                                "operations": ["SPLIT", "SUBSTITUTE", "CONCAT"],
                                "position": position,
                                "replacement": token,
                            },
                        )
                    )
        if len(alphabet) > 1:
            k = n // 2
            proposals.append(
                (
                    word[:k] + alphabet + word[k:],
                    {
                        "operations": ["SPLIT", "CONCAT", "CONCAT"],
                        "position": k,
                        "inserted_observed_atoms": alphabet,
                    },
                )
            )
            proposals.append(
                (
                    word[:k] + list(reversed(alphabet)) + word[k:],
                    {
                        "operations": ["SPLIT", "CONCAT", "CONCAT"],
                        "position": k,
                        "inserted_observed_atoms": list(reversed(alphabet)),
                    },
                )
            )
        for tokens, derivation in proposals:
            if attempts >= 64:
                return probes
            attempts += 1
            key = tuple(tokens)
            if key in known or key in seen or len(tokens) > 512:
                continue
            seen.add(key)
            predictions = {
                c["candidate_id"]: candidate_decision(model, c, tokens)
                for c in candidates
            }
            if len(set(predictions.values())) > 1:
                probes.append(
                    {
                        "tokens": tokens,
                        "kind": "membership_query",
                        "label": "REQUIRED_FROM_EXTERNAL_HOLDER",
                        "source_train_id": index,
                        "derivation": derivation,
                        "candidate_predictions": predictions,
                        "scope": "separates retained train-compatible candidates, not every possible grammar",
                    }
                )
                if len(probes) >= 8:
                    return probes
    return probes


def enrich_relations(
    model: dict,
    samples: list,
    max_rules: int,
    observers: list | None,
    feature_mode: str,
    renaming_scope: str,
) -> None:
    candidates, trace = (
        relational_candidates(samples, max_rules, observers)
        if feature_mode == "structural"
        else ([], [{"reason": "ABLATION_FEATURE_MODE"}])
    )

    def tree_shape(node):
        if "predicate" not in node:
            return {"accepted": node["accepted"]}
        return {
            "predicate": node["predicate"],
            "threshold": node["threshold"],
            "left": tree_shape(node["left"]),
            "right": tree_shape(node["right"]),
        }

    def tree_size(node):
        return (
            1
            if "predicate" not in node
            else 1 + tree_size(node["left"]) + tree_size(node["right"])
        )

    tree_id = digest(tree_shape(model["tree"]))
    errors = sum(
        (tree_probability(model, s["tokens"]) >= 0.5) != s["accepted"] for s in samples
    )
    tree = {
        "candidate_id": tree_id,
        "formalism": "bounded_observed_relation_tree",
        "candidate_status": "EMPIRICAL",
        "training_errors": errors,
        "relation_coverage": 1,
        "hypothesis_complexity": {
            "ast_nodes": tree_size(model["tree"]),
            "node_budget": max_rules,
        },
    }
    if errors == 0:
        candidates.append(tree)
    relational = [
        c for c in candidates if c["formalism"] == "observed_relation_composition"
    ]
    selected = (
        min(
            relational,
            key=lambda c: (
                -c["relation_coverage"],
                c["hypothesis_complexity"]["ast_nodes"],
                c["candidate_id"],
            ),
        )
        if relational
        else tree
    )
    model.update(
        status="UNDERDETERMINED",
        candidate_status="EMPIRICAL",
        identifiability_status="UNDERDETERMINED",
        family_status="UNDERDETERMINED",
        selected_candidate_id=selected["candidate_id"],
        selected_formalism=selected["formalism"],
        train_compatible_candidates=candidates,
        relational_rule_ast=selected.get("ast"),
        rule_witnesses=selected.get("rule_witnesses", []),
        hypothesis_complexity=selected["hypothesis_complexity"],
        candidate_derivation_trace=trace,
        scope={
            "renaming_scope": renaming_scope,
            "relation_scope": "within each word; arbitrary atom names",
            "train_lengths": sorted({len(s["tokens"]) for s in samples}),
            "training_index_namespace": "frozen grammar_hypotheses[0].train_samples; match input members by sample digest",
            "max_rules": max_rules,
            "max_candidate_derivations": min(64, 4 * max_rules),
            "max_probe_derivations": 64,
            "max_prediction_tokens": 512,
            "reason": "finite observed alignments cannot identify a unique language",
        },
        probability_semantics="Laplace score for selected empirical candidate, not posterior confidence in a unique grammar",
    )
    model["counterexample_candidates"] = active_probes(model, candidates, samples)


def probability(model: dict, word: list | tuple) -> float:
    ast = model.get("relational_rule_ast")
    if not ast:
        return tree_probability(model, word)
    accepted = relation_value(ast, word)
    counts = Counter(s["accepted"] for s in model["train_samples"])
    return (
        (counts[True] + 1) / (counts[True] + 2) if accepted else 1 / (counts[False] + 2)
    )


def prediction(model: dict, word: list | tuple) -> dict:
    decisions = {
        c["candidate_id"]: candidate_decision(model, c, word)
        for c in model.get("train_compatible_candidates", [])
    }
    disagreement = len(set(decisions.values())) > 1
    return {
        "candidate_status": model.get("candidate_status", "EMPIRICAL"),
        "identifiability_status": "UNDERDETERMINED",
        "family_verdict": (
            "INCONCLUSIVE" if disagreement else "CONSENSUS_ON_RETAINED_CANDIDATES"
        ),
        "candidate_predictions": decisions,
        "selected_candidate_id": model.get("selected_candidate_id"),
        "selected_candidate_accepts": probability(model, word) >= 0.5,
        "selected_rule_witness": (
            relation_trace(model["relational_rule_ast"], word)
            if model.get("relational_rule_ast")
            else []
        ),
        "scope": "retained finite hypothesis set; consensus is not a theorem or uniqueness proof",
    }
