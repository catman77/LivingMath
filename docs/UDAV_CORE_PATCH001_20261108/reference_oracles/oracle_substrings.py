#!/usr/bin/env python3
"""Independent finite oracle: SPLIT-closure of one token word.
No LivingMath imports, no server calls, no LLM, no assertion about semantic quality.
"""
from collections import Counter

WORD = tuple('abcabcab')
TARGET = {WORD[i:j] for i in range(len(WORD) + 1) for j in range(i, len(WORD) + 1)}


def plan_greedy(word=WORD):
    seen = {word}
    plan = []
    while seen != TARGET:
        actions = []
        for state in list(seen):
            for k in range(len(state) + 1):
                children = (state[:k], state[k:])
                added = set(children) - seen
                if added:
                    actions.append((len(added), len(state), ''.join(state), k, state, children))
        if not actions:
            raise RuntimeError('No way to reach target')
        actions.sort(key=lambda x: (x[0], x[1], x[2], -x[3]), reverse=True)
        _, _, _, k, state, children = actions[0]
        assert 0 <= k <= len(state)
        assert state[:k] == children[0] and state[k:] == children[1]
        seen.update(children)
        plan.append({'input': ''.join(state), 'split_at': k,
                     'out': [''.join(child) for child in children]})
    return seen, plan


def main():
    seen, plan = plan_greedy()
    assert seen == TARGET
    assert len(plan) <= 24
    assert len(TARGET) == 22
    print('Root:', ''.join(WORD))
    print('Distinct accessible contiguous substrings: ', len(TARGET))
    print('Constructive SPLIT applications:', len(plan))
    print('Distinct counts by length:', dict(sorted(Counter(map(len, TARGET)).items())))
    for index, step in enumerate(plan, 1):
        print(f'{index:02d}: {step["input"]!r} @ {step["split_at"]} -> {step["out"]}')


if __name__ == '__main__':
    main()
