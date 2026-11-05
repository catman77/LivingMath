#!/usr/bin/env python3
"""Standalone no-dependency exact oracle checks for SYMBOLIC_V1 fixtures.

This is NOT the symbolic kernel and does not make claims about White Star.
Run: python checks/check_fixtures.py
"""
import json
import random
from pathlib import Path

F = json.loads((Path(__file__).parent.parent / "fixtures" / "symbolic_cases.json").read_text(encoding="utf-8"))


def q(w):
    assert set(w) <= {"S", "P"}
    return w.count("S") - w.count("P")


def reduce_sp(w):
    """Leftmost adjacent cancellation with a full event log."""
    current = list(w)
    log = []
    while True:
        idx = next((i for i in range(len(current)-1) if current[i] != current[i+1]), None)
        if idx is None:
            break
        log.append((idx, idx+1))
        del current[idx:idx+2]
    return "".join(current), log


def alpha(word):
    d = {}
    return tuple(d.setdefault(c, len(d)) for c in word)


def alpha_corpus(words, local=False):
    if local:
        return tuple(alpha(w) for w in words)
    d = {}
    return tuple(tuple(d.setdefault(c, len(d)) for c in w) for w in words)


def sp_inv(w):
    return w.translate(str.maketrans("SP", "PS"))


def run():
    assert F["schema"] == "livingmath-symbolic-fixtures/1"
    checks = 0
    for w in F["zero_words"]:
        result, log = reduce_sp(w)
        assert q(w) == 0 and result == ""
        checks += 1
    for a in F["alpha_single_word_pairs"]:
        assert (alpha(a["left"]) == alpha(a["right"])) == a["equivalent"], a
        checks += 1
    for a in F["alpha_corpus_pairs"]:
        assert (alpha_corpus(a["left"], local=True) == alpha_corpus(a["right"], local=True)) == a["local_equivalent"], a
        assert (alpha_corpus(a["left"]) == alpha_corpus(a["right"])) == a["global_equivalent"], a
        checks += 2
    for a in F["composition_pairs"]:
        assert a["a"]+a["b"] == a["ab"]
        assert a["b"]+a["a"] == a["ba"]
        assert a["ab"] != a["ba"]
        assert q(a["ab"]) == q(a["ba"]) == a["fold"]
        checks += 1
    for a in F["nonstrivial_q"]:
        assert q(a["w"]) == a["q"]
        checks += 1
    rng = random.Random(1731)
    for i in range(1000):
        n = rng.randrange(41)
        w = "".join(rng.choice("SP") for _ in range(n))
        folded, log = reduce_sp(w)
        assert q(folded) == q(w)
        assert reduce_sp(folded)[0] == folded
        assert sp_inv(sp_inv(w)) == w
        assert q(sp_inv(w)) == -q(w)
        k = rng.randrange(n+1)
        assert w[:k]+w[k:] == w
        insertion = rng.choice(("SP", "PS"))
        new = w[:k]+insertion+w[k:]
        assert q(new) == q(w)
        assert reduce_sp(new)[0] == folded
        checks += 6
    import hashlib
    ex = json.loads((Path(__file__).parent.parent / "fixtures" / "mcp_request_example.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(ex["request"]["source"]["text"].encode("utf-8")).hexdigest() == ex["request"]["source"]["sha256"]
    checks += 1
    print(f"PASS: {checks} exact assertions / oracle invariants, seed=1731")
    print("NOTE: does not test MCP, CAD, Udav, grammar induction or semantic novelty")


if __name__ == "__main__":
    run()
