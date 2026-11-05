"""Pure finite structural witnesses, with explicitly separate equivalence relations."""

from collections import Counter
from ..core import digest
from .state import alpha_corpus, reduce_sp


class CADObserver:
    def __init__(self, names, scope="global", hierarchy=()):
        self.names = names
        self.scope = scope
        self.hierarchy = hierarchy

    def observe(self, state):
        tokens = state.tokens
        n = len(tokens)
        out = {}
        for name in self.names:
            if name == "literal":
                out[name] = {
                    "tokens": list(tokens),
                    "boundaries": sorted(set((p, k) for p, k, _ in state.boundaries)),
                }
            elif name == "alpha_pattern":
                # The entire corpus retains identities across records in global scope.
                cuts = sorted(
                    set(
                        [0, n]
                        + [p for p, k, _ in state.boundaries if k == "record_start"]
                    )
                )
                words = (
                    [tokens[a:b] for a, b in zip(cuts, cuts[1:])]
                    if self.scope == "local"
                    else [tokens]
                )
                out[name] = {
                    "scope": self.scope,
                    "pattern": alpha_corpus(words, self.scope),
                    "boundary_positions": sorted(
                        set(p for p, _, _ in state.boundaries)
                    ),
                }
            elif name == "adjacency":
                out[name] = {
                    "oriented_pairs": [
                        [i, tokens[i], tokens[i + 1], tokens[i] == tokens[i + 1]]
                        for i in range(max(0, n - 1))
                    ],
                    "counts": [
                        [list(k), v]
                        for k, v in sorted(Counter(zip(tokens, tokens[1:])).items())
                    ],
                    "inter_record_boundaries": [
                        p
                        for p, k, _ in state.boundaries
                        if k == "record_end" and 0 < p < n
                    ],
                }
            elif name == "substring_contexts":
                out[name] = {
                    "radius": 2,
                    "max_fragment_tokens": 2,
                    "contexts": [
                        {
                            "position": i,
                            "fragment": list(tokens[i : i + 2]),
                            "left": list(tokens[max(0, i - 2) : i]),
                            "right": list(tokens[i + 2 : i + 4]),
                        }
                        for i in range(min(n, 64))
                    ],
                    "bounded": True,
                    "total_positions": n,
                }
            elif name == "composition":
                out[name] = {
                    "ordered_tokens": list(tokens),
                    "record_cuts": [(p, k) for p, k, _ in state.boundaries],
                }
            elif name == "sp_reduce":
                normal, log = reduce_sp(tokens)
                balance = 0
                prefix = [0]
                for t in tokens:
                    balance += 1 if t == "S" else -1
                    prefix.append(balance)
                out[name] = {
                    "q": balance,
                    "normal_form": list(normal),
                    "leftmost_cancellations": log,
                    "prefix_balance": prefix,
                }
            elif name == "hierarchy":
                out[name] = {
                    "declared_source_segments": self.hierarchy,
                    "claim": "observed",
                    "syntactic_tree_inferred": False,
                }
        return {
            "state_word_hash": state.word_hash,
            "observers": out,
            "claim": "observed",
            "projection_only": True,
        }


def witness_set(observation):
    out = set()
    for name, value in observation["observers"].items():
        if name == "literal":
            value = {"tokens": value["tokens"], "boundaries": value["boundaries"]}
        out.add(name + ":" + digest(value))
    return out


def compare(left, right, observer):
    a, b = left.tokens, right.tokens
    oa, ob = observer.observe(left), observer.observe(right)
    literal_a = CADObserver(["literal"]).observe(left)["observers"]["literal"]
    literal_b = CADObserver(["literal"]).observe(right)["observers"]["literal"]
    claims = [
        {
            "relation": "literal_word_equality",
            "equal": literal_a == literal_b,
            "kind": "proved_exact",
            "certificate": {"left": literal_a, "right": literal_b},
        },
        {
            "relation": "alpha_equality",
            "equal": alpha_corpus([a]) == alpha_corpus([b])
            and literal_a["boundaries"] == literal_b["boundaries"],
            "kind": "proved_exact",
            "certificate": {
                "scope": "isolated",
                "left_boundaries": literal_a["boundaries"],
                "right_boundaries": literal_b["boundaries"],
                "left": alpha_corpus([a]),
                "right": alpha_corpus([b]),
            },
        },
        {
            "relation": "observer_indistinguishability",
            "equal": oa["observers"] == ob["observers"],
            "kind": "observed",
            "certificate": {
                "observer_index": observer.names,
                "scope": observer.scope,
                "finite": True,
                "left": oa["observers"],
                "right": ob["observers"],
            },
        },
    ]
    if set(a) | set(b) <= {"S", "P"}:
        x, l = reduce_sp(a)
        y, r = reduce_sp(b)
        claims.append(
            {
                "relation": "same_sp_normal_form",
                "equal": x == y,
                "kind": "proved_exact",
                "certificate": {
                    "left_original": list(a),
                    "right_original": list(b),
                    "left_reduction_steps": l,
                    "right_reduction_steps": r,
                    "left_normal_form": list(x),
                    "right_normal_form": list(y),
                },
                "assumptions": ["SP/PS cancellation grammar"],
                "non_claims": ["literal_word_equality", "semantic_equivalence"],
            }
        )
    return claims
