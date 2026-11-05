"""One additional CAD orientation; the kernel and its score are unchanged."""
from collections import defaultdict
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "llm_white_star_formal"))
from formal_core import (load_case, compile_atlas, pair_cells, qualitative, encode,
                         reachability as old_reachability)
from fast_source import FastWhiteStarSource


def rotate(matrix):
    a, b, c, d = matrix
    # Right multiplication by J=[[0,-1],[1,0]]. The original source witness
    # remains in N^2. Only the observation matrix changes.
    return (b, -a, d, -c)


def expand(data):
    old = compile_atlas(data)
    matrices, chart_index, charts = [], {}, []
    for orientation in ("I", "J"):
        for original in old["charts"]:
            matrix = tuple(original["matrix"])
            if orientation == "J":
                matrix = rotate(matrix)
            if matrix not in chart_index:
                index = len(matrices)
                chart_index[matrix] = index
                matrices.append(matrix)
                charts.append(dict(view=index, matrix=matrix, aliases=[]))
            charts[chart_index[matrix]]["aliases"].append(dict(
                concepts=original["pair"], orientation=orientation,
                original_view=original["view"], original_matrix=original["matrix"]))
    return dict(charts=charts, semantic_maps=sum(len(c["aliases"]) for c in charts),
                old_maps=len(old["charts"]),
                omitted_collinear_pairs=old["omitted_collinear_pairs"])


def exact_field(data, atlas):
    by_pair = defaultdict(dict)
    cells = []
    for chart in atlas["charts"]:
        matrix = chart["matrix"]
        for alias in chart["aliases"]:
            i, j = alias["concepts"]
            # The reverse ordered map has the same qualitative possibilities.
            # Retain one canonical ordering for the exact field audit.
            if i > j:
                continue
            audit = pair_cells(i, j, matrix[:2], matrix[2:])
            cells.append(dict(view=chart["view"], alias=alias, **audit))
            for state in audit["states"]:
                by_pair[i, j].setdefault(tuple(state["state"]),
                                         dict(view=chart["view"], alias=alias, **state))
    old = old_reachability(data)
    old_states = {tuple(s["state"]) for pair in old["pairs"] for s in pair["states"]}
    states = {s for pair in by_pair.values() for s in pair}
    expected = set()
    for i, j in by_pair:
        for relation in ("ALIGN", "TENSION"):
            for dominant in (i, j, "BALANCED"):
                expected.add((i, j, relation, dominant))
        expected.add((i, j, "UNRESOLVED", i))
        expected.add((i, j, "UNRESOLVED", j))
    assert states == expected and old_states <= states
    return dict(cells=cells, pairs=[dict(concepts=pair, witnesses=list(witnesses.values()))
                                   for pair, witnesses in sorted(by_pair.items())],
                summary=dict(old_modes=len(old_states), new_modes=len(states),
                             added_modes=len(states - old_states), old_modes_preserved=True,
                             modes_per_pair=8, covered_pairs=len(by_pair),
                             fixed_relation_pairs=0,
                             both_align_and_tension_for_every_pair=True,
                             scope="All allowed (chart,nonzero witness) combinations; not a guarantee that a fixed-budget trajectory visits them all"))


def search(data, atlas, protocol):
    with FastWhiteStarSource(seed=protocol["frozen_seed"], k=protocol["candidates_per_step"],
                             charts=[c["matrix"] for c in atlas["charts"]]) as controller:
        records = controller.read(protocol["steps"], audit=True).observations()
        diagnostics = controller.snapshot()
    observations = [r.to_dict() for r in records]
    return observations, decode_observations(atlas, observations), diagnostics


def decode_observations(atlas, observations):
    readouts = []
    for record in observations:
        if not any(record["witness"]):
            continue
        chart = atlas["charts"][record["view"]]
        readouts.append(dict(step=record["step"], geometric_view=record["view"],
                             alternatives=[dict(alias=alias,
                                                state=qualitative(alias["concepts"], *record["coordinates"]))
                                           for alias in chart["aliases"]],
                             status="ALL_ALIASES_PRESERVED_NOT_INDEPENDENT_SEARCHES"))
    return readouts


def audit_search(data, atlas, readouts, field):
    old = old_reachability(data)
    old_states = {tuple(s["state"]) for pair in old["pairs"] for s in pair["states"]}
    old_types = {tuple(pair["concepts"]): set(pair["relation_types"]) for pair in old["pairs"]}
    possible = {tuple(w["state"]) for pair in field["pairs"] for w in pair["witnesses"]}
    seen, new_examples, unlocked_pairs = set(), [], set()
    for readout in readouts:
        for alternative in readout["alternatives"]:
            state = tuple(alternative["state"])
            assert state in possible
            if state not in old_states and state not in seen:
                new_examples.append(dict(step=readout["step"], view=readout["geometric_view"],
                                         **alternative))
            if len(old_types[state[:2]]) == 1 and state[2] not in old_types[state[:2]]:
                unlocked_pairs.add(state[:2])
            seen.add(state)
    return dict(unique_modes=len(seen), newly_possible_modes_visited=len(seen - old_states),
                formerly_fixed_pairs_with_new_relation_visited=len(unlocked_pairs),
                unlocked_pairs_observed=sorted(unlocked_pairs),
                emitted_alias_records=sum(len(r["alternatives"]) for r in readouts),
                ambiguous_numeric_observations=sum(len(r["alternatives"]) > 1 for r in readouts),
                first_new_mode_examples=new_examples[:6],
                first_examples_selection="First occurrence in time; no literary ranking")


def reference_replay(data, atlas, observations, protocol):
    import cad
    import source
    from math import gcd
    matrices = tuple(tuple(c["matrix"]) for c in atlas["charts"])
    assert gcd(11, len(matrices)) == 1
    old_cad, old_source = cad.CHARTS, source.CHARTS
    try:
        cad.CHARTS = source.CHARTS = matrices
        controller = source.WhiteStarSource(seed=protocol["frozen_seed"], k=protocol["candidates_per_step"])
        expected = [controller.next().to_dict() for _ in range(protocol["steps"])]
    finally:
        cad.CHARTS, source.CHARTS = old_cad, old_source
    if encode(expected) != encode(observations):
        raise ValueError("expanded native run differs from the unchanged reference chooser")
    return True
