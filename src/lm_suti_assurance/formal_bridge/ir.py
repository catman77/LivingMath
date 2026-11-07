"""Closed data-only IR and declared finite bounds. No search or evaluation."""

import hashlib
import re
import time
from ..core import digest


DEFAULTS = {"max_tokens": 12, "max_steps": 100000, "max_forest_edges": 4096,
            "max_trees": 32, "max_candidates": 128, "max_cpu_ms": 4000,
            "max_rules": 6, "max_nt": 2, "max_ast_nodes": 32,
            "max_rhs": 5, "max_states": 4, "max_length": 6,
            "max_words": 512, "max_models": 512}


def need(value, message):
    if not value:
        raise ValueError(message)


def limits(value=None):
    value = value or {}
    need(isinstance(value, dict) and not (set(value) - set(DEFAULTS)), "INVALID_BOUND")
    result = dict(DEFAULTS)
    for k, n in value.items():
        need(type(n) is int and 1 <= n <= DEFAULTS[k], "INVALID_BOUND:" + k)
        result[k] = n
    return result


class Bound(Exception):
    pass


class Budget:
    def __init__(self, bounds):
        self.bounds = bounds
        self.started = time.process_time()
        self.steps = 0

    def tick(self, n=1):
        self.steps += n
        if self.steps > self.bounds["max_steps"] or (time.process_time() - self.started) * 1000 > self.bounds["max_cpu_ms"]:
            raise Bound("SEARCH_OR_CPU_BOUND")


def grammar(value):
    need(isinstance(value, dict) and set(value) == {"schema", "terminals", "nonterminals", "start", "productions"}, "INVALID_GRAMMAR")
    need(value["schema"] == "formal-grammar-ir/1", "INVALID_GRAMMAR_SCHEMA")
    ts, ns, ps = value["terminals"], value["nonterminals"], value["productions"]
    for xs, cap, minimum in [(ts, 8, 0), (ns, 2, 1)]:
        need(isinstance(xs, list) and minimum <= len(xs) <= cap and all(isinstance(x, str) and 0 < len(x) <= 128 for x in xs), "INVALID_SYMBOLS")
        need(len(set(xs)) == len(xs), "DUPLICATE_SYMBOL")
    need(value["start"] in ns and isinstance(ps, list) and 0 < len(ps) <= 6, "INVALID_START_OR_RULES")
    ids = []
    for p in ps:
        need(isinstance(p, dict) and set(p) == {"id", "lhs", "rhs"}, "INVALID_PRODUCTION")
        need(isinstance(p["id"], str) and 0 < len(p["id"]) <= 128 and p["lhs"] in ns, "INVALID_PRODUCTION_BINDING")
        ids.append(p["id"])
        need(isinstance(p["rhs"], list) and 1 <= len(p["rhs"]) <= 5, "INVALID_SEQ")
        for s in p["rhs"]:
            need(isinstance(s, dict), "INVALID_SYMBOL")
            if s.get("op") == "EPS":
                need(s == {"op": "EPS"} and len(p["rhs"]) == 1, "INVALID_EPS")
            elif s.get("op") == "TERM":
                need(set(s) == {"op", "value"} and s["value"] in ts, "INVALID_TERM")
            else:
                need(set(s) == {"op", "name"} and s["op"] == "NT_REF" and s["name"] in ns, "INVALID_NT_REF")
    need(len(set(ids)) == len(ids) and set(p["lhs"] for p in ps) == set(ns), "INVALID_RULE_IDS_OR_NT")
    return value


def complexity(g):
    return 1 + len(g["nonterminals"]) + sum(2 + len(p["rhs"]) for p in g["productions"])


def dfa(value):
    need(isinstance(value, dict) and set(value) == {"schema", "states", "alphabet", "start", "accepting", "delta"}, "INVALID_DFA")
    need(value["schema"] == "formal-dfa-ir/1", "INVALID_DFA_SCHEMA")
    q, a = value["states"], value["alphabet"]
    need(isinstance(q, list) and 1 <= len(q) <= 4 and q == list(range(len(q))) and all(type(x) is int for x in q), "INVALID_STATES")
    need(isinstance(a, list) and 1 <= len(a) <= 8 and all(isinstance(x, str) and 0 < len(x) <= 128 for x in a) and len(set(a)) == len(a), "INVALID_ALPHABET")
    need(type(value["start"]) is int and value["start"] in q and isinstance(value["accepting"], list) and len(set(value["accepting"])) == len(value["accepting"]) and all(type(x) is int and x in q for x in value["accepting"]), "INVALID_ACCEPTING")
    need(isinstance(value["delta"], list) and len(value["delta"]) == len(q)*len(a), "INCOMPLETE_DELTA")
    keys = []
    for e in value["delta"]:
        need(isinstance(e, dict) and set(e) == {"from", "token", "to"} and type(e["from"]) is int and type(e["to"]) is int and e["from"] in q and e["to"] in q and e["token"] in a, "INVALID_TRANSITION")
        keys.append((e["from"], e["token"]))
    need(len(set(keys)) == len(keys), "DUPLICATE_TRANSITION")
    return value


def source(record):
    raw = record["source"]["text"].encode("utf8")
    need(len(raw) <= 48000 and hashlib.sha256(raw).hexdigest() == record["source"]["sha256"], "SOURCE_MISMATCH")
    need(isinstance(record["source"]["rights"], str) and bool(record["source"]["rights"].strip()) and bool(record["source"]["edition"].strip()), "RIGHTS_REQUIRED")
    matches = list(re.finditer(r"\S+", record["source"]["text"]))
    need([m.group() for m in matches] == record["tokens"], "TOKEN_SOURCE_MISMATCH")
    return [[len(record["source"]["text"][:m.start()].encode()), len(record["source"]["text"][:m.end()].encode())] for m in matches]


def header(ast, record, bounds):
    return {"schema": "formal-membership-proof/1", "grammar_sha256": digest(ast),
            "record_ref": digest(record), "source_sha256": record["source"]["sha256"],
            "tokens": list(record["tokens"]), "token_spans": source(record),
            "bounds_sha256": digest(bounds)}
