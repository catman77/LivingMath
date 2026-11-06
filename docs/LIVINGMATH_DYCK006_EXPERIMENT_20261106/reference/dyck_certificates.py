"""Independent finite-instance test oracle for the oriented grammar

    D := epsilon | OPEN D CLOSE D

This is NOT an automatically induced LivingMath rule, and is NOT deployed
on the user's MCP server. It is a reference generator and independently
checkable finite certificate format used to test a future grammar generator.

SP normal-form reduction (SP->empty, PS->empty) is deliberately a separate
operation with different semantics.
"""
from __future__ import annotations

import hashlib
import json
from itertools import product
from math import comb
from typing import Any

ALPHABET = ("S", "P")
RULE_VERSION = "dyck-branch-proof/1"


def words(n: int, alphabet=ALPHABET):
    return (tuple(p) for p in product(alphabet, repeat=n))


def sha(tokens) -> str:
    src = json.dumps(list(tokens), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(src.encode("utf-8")).hexdigest()


def dyck_prefix(tokens, opener="S", closer="P") -> bool:
    """Independent prefix-height membership oracle, O(length)."""
    level = 0
    for x in tokens:
        if x == opener:
            level += 1
        elif x == closer:
            level -= 1
        else:
            raise ValueError("token outside declared alphabet")
        if level < 0:
            return False
    return level == 0


def cancel_normal_form(tokens):
    """Orientation-INDEPENDENT cancellation normal form.

    Both S P and P S reduce to empty, hence this loses Dyck ordering.
    """
    stack = []
    for x in tokens:
        if stack and stack[-1] != x:
            stack.pop()
        else:
            stack.append(x)
    return tuple(stack)


def make_positive_witness(tokens, opener="S", closer="P") -> dict | None:
    """Canonical first-return decomposition, not grammar synthesis.

    Witnesses both recursive branches of D ::= eps | opener D closer D.
    Token spans are local to the current recursive node.
    """
    tokens = tuple(tokens)
    if not tokens:
        return {"kind": "EPS", "length": 0, "sha256": sha(tokens)}
    if tokens[0] != opener:
        return None
    level = 0
    for j, x in enumerate(tokens):
        level += 1 if x == opener else -1
        if level < 0:
            return None
        if level == 0:
            inner = tokens[1:j]
            after = tokens[j + 1:]
            left = make_positive_witness(inner, opener, closer)
            right = make_positive_witness(after, opener, closer)
            if left is None or right is None:
                return None
            return {
                "kind": "OPEN_INNER_CLOSE_AFTER",
                "length": len(tokens),
                "sha256": sha(tokens),
                "roles": {"open": opener, "close": closer},
                "split": {"open_at": 0, "close_at": j, "inner": [1, j], "after": [j + 1, len(tokens)]},
                "inner_proof": left,
                "after_proof": right,
            }
    return None


def check_positive_witness(tokens, proof, opener="S", closer="P") -> bool:
    """Independent structural checker; never trusts an attached digest alone."""
    tokens = tuple(tokens)
    if not isinstance(proof, dict) or proof.get("length") != len(tokens) or proof.get("sha256") != sha(tokens):
        return False
    if proof.get("kind") == "EPS":
        return len(tokens) == 0 and set(proof) == {"kind", "length", "sha256"}
    if proof.get("kind") != "OPEN_INNER_CLOSE_AFTER":
        return False
    if proof.get("roles") != {"open": opener, "close": closer}:
        return False
    s = proof.get("split")
    if not isinstance(s, dict) or set(s) != {"open_at", "close_at", "inner", "after"}:
        return False
    j = s["close_at"]
    if type(j) is not int or not 1 <= j < len(tokens):
        return False
    if s != {"open_at": 0, "close_at": j, "inner": [1, j], "after": [j + 1, len(tokens)]}:
        return False
    if tokens[0] != opener or tokens[j] != closer:
        return False
    # Both branches strictly shorter; the recursion is manifestly terminating.
    left, right = tokens[1:j], tokens[j + 1:]
    return (check_positive_witness(left, proof.get("inner_proof"), opener, closer)
            and check_positive_witness(right, proof.get("after_proof"), opener, closer))


def build_full_table(tokens, opener="S", closer="P"):
    """Dynamic-programming truth table for one *fixed* branching grammar.

    For a nonmember this is a bounded NONMEMBERSHIP certificate, not a theorem
    that no other grammar or other proof could recognize the word.
    The recurrence enumerates possible close positions and both children.
    """
    tokens = tuple(tokens)
    n = len(tokens)
    T = {(i, i): True for i in range(n + 1)}
    for length in range(1, n + 1):
        for i in range(n - length + 1):
            j = i + length
            valid = False
            if tokens[i] == opener and length % 2 == 0:
                for k in range(i + 1, j):
                    if tokens[k] == closer and T[(i + 1, k)] and T[(k + 1, j)]:
                        valid = True
                        break
            T[(i, j)] = valid
    return {"schema": RULE_VERSION, "token_sha256": sha(tokens), "n": n,
            "roles": {"open": opener, "close": closer},
            "table": [{"i": i, "j": j, "value": T[(i, j)]}
                      for i in range(n + 1) for j in range(i, n + 1)]}


def independently_check_full_table(tokens, cert, opener="S", closer="P") -> bool:
    """Checks every DP cell using the recurrence, not just the final bit."""
    tokens = tuple(tokens)
    n = len(tokens)
    if not isinstance(cert, dict) or cert.get("schema") != RULE_VERSION or cert.get("n") != n:
        return False
    if cert.get("token_sha256") != sha(tokens) or cert.get("roles") != {"open": opener, "close": closer}:
        return False
    items = cert.get("table")
    if not isinstance(items, list) or len(items) != (n + 1) * (n + 2) // 2:
        return False
    found = {}
    for e in items:
        if not isinstance(e, dict) or set(e) != {"i", "j", "value"}:
            return False
        i, j, value = e["i"], e["j"], e["value"]
        if type(i) is not int or type(j) is not int or type(value) is not bool or not (0 <= i <= j <= n):
            return False
        if (i, j) in found:
            return False
        found[i, j] = value
    for length in range(n + 1):
        for i in range(n - length + 1):
            j = i + length
            if length == 0:
                expected = True
            elif length % 2 or tokens[i] != opener:
                expected = False
            else:
                expected = any(tokens[k] == closer and found[i + 1, k] and found[k + 1, j]
                               for k in range(i + 1, j))
            if found[i, j] != expected:
                return False
    return True


def census(length):
    allwords = list(words(length))
    zero = [w for w in allwords if not cancel_normal_form(w)]
    dyck = [w for w in allwords if dyck_prefix(w)]
    return {"length": length, "all": len(allwords), "zero": len(zero),
            "dyck": len(dyck), "zero_but_not_dyck": len(zero) - len(dyck),
            "balanced_closed_formula": comb(length, length // 2) if length % 2 == 0 else 0}


if __name__ == "__main__":
    for n in (2, 4, 6, 8, 10):
        print(json.dumps(census(n), ensure_ascii=False))


def prefix_future_signature(prefix, suffix_horizon: int, opener="S", closer="P"):
    """Finite *right-context* signature, no training labels involved.

    The signature is a SET OF ACCEPTED CONTINUATIONS, not a scalar probability.
    """
    alphabet = (opener, closer)
    prefix = tuple(prefix)
    return frozenset(s for length in range(suffix_horizon + 1)
                     for s in product(alphabet, repeat=length)
                     if dyck_prefix(prefix + s, opener, closer))


def future_class_census(max_prefix_len: int):
    prefixes = [p for n in range(max_prefix_len + 1) for p in words(n)]
    signatures = {prefix_future_signature(p, max_prefix_len) for p in prefixes}
    return {"max_prefix_len": max_prefix_len,
            "prefixes": len(prefixes),
            "distinguishable_future_classes": len(signatures)}


def utf8_token_spans(tokens):
    """Exact source-to-token byte spans for single-whitespace-separated atoms.

    This serializer is only a reference input fixture, not a generic tokenizer.
    """
    tokens = tuple(tokens)
    if any(not isinstance(t, str) or not t or any(c.isspace() for c in t) for t in tokens):
        raise ValueError("tokens must be nonempty atoms without whitespace")
    text = " ".join(tokens)
    position = 0
    spans = []
    for idx, token in enumerate(tokens):
        if idx:
            position += 1
        start = position
        position += len(token.encode("utf-8"))
        spans.append({"token": token, "byte_start": start, "byte_end": position})
    return {"text": text, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "tokens": list(tokens), "spans": spans}


def check_utf8_token_spans(source):
    if not isinstance(source, dict):
        return False
    text, tokens, spans = source.get("text"), source.get("tokens"), source.get("spans")
    if not isinstance(text, str) or not isinstance(tokens, list) or not isinstance(spans, list):
        return False
    if source.get("sha256") != hashlib.sha256(text.encode("utf-8")).hexdigest():
        return False
    try:
        gold = utf8_token_spans(tokens)
    except (ValueError, TypeError):
        return False
    if text != gold["text"]:
        return False
    if spans != gold["spans"]:
        return False
    buf = text.encode("utf-8")
    return all(buf[s["byte_start"]:s["byte_end"]].decode("utf-8") == s["token"] for s in spans)
