#!/usr/bin/env python3
"""One geometric relaxation and three explicit formal transfer checks."""
from pathlib import Path
import argparse
from copy import deepcopy
import hashlib
import json
import statistics
import time

from rotated_atlas import (HERE, load_case, expand, exact_field, search,
                           audit_search, reference_replay, encode)
from formal_models import verify_transfers
from fast_source import native_library


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def transfer_mutations(proposal, data, prose):
    results = []
    mutations = [
        ("M1_remove_observation_loss", 0, "C", [[1,0],[0,1]]),
        ("M1_erase_hidden_change", 0, "A", [[1,0],[0,1]]),
        ("M2_control_can_change_the_invariant", 1, "B", [[1],[1]]),
        ("M2_dynamics_changes_the_invariant", 1, "A", [[1,0],[0,2]]),
        ("M3_no_order_effect", 2, "P", [[1,0],[0,1]]),
        ("M3_noninvertible_cyclic_factor", 2, "P", [[0,0],[0,1]]),
    ]
    for name, index, key, value in mutations:
        changed = deepcopy(proposal)
        changed["units"][index]["model"][key] = value
        try:
            verify_transfers(changed, data, prose)
        except ValueError as error:
            results.append(dict(name=name, status="REJECTED", reason=str(error)))
        else:
            raise AssertionError(f"invalid transfer accepted: {name}")
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "results")
    args = parser.parse_args()
    freeze = json.loads((HERE / "input_freeze.json").read_text())
    for name, expected in freeze.items():
        if hashlib.sha256((HERE.parent / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"frozen input modified: {name}")
    protocol = json.loads((HERE / "protocol.json").read_text())
    proposal = json.loads((HERE / "transfer_proposal.json").read_text())
    data, old_trace, frames, prose = load_case()
    atlas = expand(data)
    field = exact_field(data, atlas)
    native_library()
    observations, readouts, diagnostics = search(data, atlas, protocol)
    reference_replay(data, atlas, observations, protocol)
    audit = audit_search(data, atlas, readouts, field)
    transfers = verify_transfers(proposal, data, prose)
    mutations = transfer_mutations(proposal, data, prose)
    durations = []
    for _ in range(11):
        started = time.perf_counter()
        again_atlas = expand(data)
        again_trace, again_readout, again_diag = search(data, again_atlas, protocol)
        durations.append(time.perf_counter() - started)
        assert encode(again_trace) == encode(observations)
        assert encode(again_readout) == encode(readouts)
    diagnostics["aliases_emitted_are_not_extra_numeric_projections"] = True
    ws = HERE.parent / "white_star"
    old_manifest = json.loads((HERE.parent / "llm_white_star/results/manifest.json").read_text())
    unchanged = {name: hashlib.sha256((ws / name).read_bytes()).hexdigest() == expected
                 for name, expected in old_manifest["unchanged_kernel_files"].items()}
    if not all(unchanged.values()):
        raise ValueError("kernel changed")
    timing = dict(median_ms=statistics.median(durations)*1000, repeats=len(durations), seconds=durations,
                  includes="atlas expansion, native state allocation, 64 source steps, audit materialization and all alias readouts",
                  excludes="imports, compilation/load, exact reachability audit, theorem checks, file writing, LLM work")
    summary = dict(
        experiment="NOBS_WHITE_STAR_LLM_003", source_concepts=len(data["concepts"]),
        unique_numeric_maps=len(atlas["charts"]), labelled_maps=atlas["semantic_maps"],
        geometry_alias_collisions=sum(len(c["aliases"])-1 for c in atlas["charts"]),
        exact_field=field["summary"], selected_run=diagnostics, qualitative_run=audit,
        formal_transfers_passed=len(transfers["units"]), rejected_transfer_mutations=len(mutations),
        native_reference_equal=True, kernel_unchanged=all(unchanged.values()),
        search_median_ms=timing["median_ms"],
        transfer_inputs="Three frozen interpretations from experiment 001, not new prose from this expanded run",
    )
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in [("atlas", atlas),("reachability",field),("readouts",readouts),
                        ("search_audit",audit),("transfer_checks",transfers),("transfer_mutations",mutations),
                        ("timing",timing),("kernel_integrity",unchanged),("summary",summary)]:
        write(args.output / f"{name}.json", value)
    (args.output / "trace.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in observations))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
