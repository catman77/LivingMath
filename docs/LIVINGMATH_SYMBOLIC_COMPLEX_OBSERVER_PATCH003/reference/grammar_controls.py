#!/usr/bin/env python3
"""Independent tests for representation loss and Dyck generalization.
No language model, no text corpus, no MCP calls, no automatic discoveries claimed.
"""
from itertools import product
from math import comb


def balanced_words(n):
    return [''.join(x) for x in product('SP', repeat=n)
            if x.count('S') == x.count('P')]


def dyck(w):
    h = 0
    for x in w:
        h += 1 if x == 'S' else -1 if x == 'P' else 1000000
        if h < 0:
            return False
    return h == 0


def alpha(w):
    lookup = {}
    return tuple(lookup.setdefault(x, len(lookup)) for x in w)


def alpha_with_line_boundaries(lines):
    lookup = {}
    return tuple(tuple(lookup.setdefault(tok, len(lookup)) for tok in line)
                 for line in lines)


def same_encoding_with_conflicting_labels(accepted, rejected, encoder):
    return encoder(accepted) == encoder(rejected)


def exact_dyck_table():
    return {n: {'balanced': len(balanced_words(n)),
                'dyck': sum(dyck(w) for w in balanced_words(n))}
            for n in (2, 4, 6, 8, 10)}


if __name__ == '__main__':
    import json
    print(json.dumps(exact_dyck_table(), ensure_ascii=False, indent=2))
