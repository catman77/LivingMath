#!/usr/bin/env python3
"""Reproduce bounded CAD search; prose decoding belongs to the current LLM."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import platform
import statistics
import time

from bridge import HERE, WS, compile_atlas, decoder_packet, digest, run_search
from fast_source import native_library


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def numeric_fingerprint(result):
    return digest([{k: o[k] for k in ("witness", "matrix", "coordinates", "signature", "candidate_scores")}
                   for o in result["observations"]])


def controls(data, original):
    reordered = deepcopy(data)
    reordered["concepts"].reverse()
    permuted = run_search(reordered)
    renamed = deepcopy(data)
    names = {c["id"]: f"opaque_{i}" for i, c in enumerate(data["concepts"])}
    for concept in renamed["concepts"]:
        concept["id"] = names[concept["id"]]
    for relation in renamed["source_relations"]:
        relation["concepts"] = [names[c] for c in relation["concepts"]]
    renamed_result = run_search(renamed)
    intervention = deepcopy(data)
    for concept in intervention["concepts"]:
        if concept["id"] == "no_exit":
            concept["coordinates"][0] *= -1
    changed = run_search(intervention)
    replay = run_search(data)
    different = sum(a["matrix"] != b["matrix"] for a, b in zip(
        original["observations"], changed["observations"]))
    result = dict(
        deterministic_replay=digest(original) == digest(replay),
        json_order_invariant=numeric_fingerprint(original) == numeric_fingerprint(permuted),
        concept_id_renaming_invariant=numeric_fingerprint(original) == numeric_fingerprint(renamed_result),
        coordinate_intervention=dict(
            concept="no_exit", before=[-4, -1], after=[4, -1],
            purpose="Causal adapter check, not an alternate reading or quality baseline",
            different_selected_matrices=different, steps=data["protocol"]["steps"],
            observed_change=numeric_fingerprint(original) != numeric_fingerprint(changed),
            baseline_fingerprint=numeric_fingerprint(original), changed_fingerprint=numeric_fingerprint(changed)),
    )
    assert result["deterministic_replay"] and result["json_order_invariant"]
    assert result["concept_id_renaming_invariant"] and result["coordinate_intervention"]["observed_change"]
    return result, changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=HERE / "input" / "concepts.json")
    parser.add_argument("--output", type=Path, default=HERE / "results")
    args = parser.parse_args()
    data = json.loads(args.input.read_text())
    # Verify the input freeze; hashing is a reproducibility aid, not a trusted
    # timestamp or a cryptographic attestation of an author's actions.
    freeze = json.loads((args.input.parent / "freeze.json").read_text())
    for name, expected in freeze.items():
        if hashlib.sha256((args.input.parent / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"frozen input modified: {name}")
    native_library()  # build/load excluded from steady-state measurements
    started = time.perf_counter()
    result = run_search(data)
    first_s = time.perf_counter() - started
    checks, changed = controls(data, result)
    timings = []
    for _ in range(31):
        started = time.perf_counter()
        replay = run_search(data)
        timings.append(time.perf_counter() - started)
        assert numeric_fingerprint(replay) == numeric_fingerprint(result)
    args.output.mkdir(parents=True, exist_ok=True)
    for name in ("atlas", "frames", "selected_frames", "summary"):
        write(args.output / f"{name}.json", result[name])
    (args.output / "trace.jsonl").write_text("".join(
        json.dumps(record, ensure_ascii=False) + "\n" for record in result["observations"]))
    write(args.output / "decoder_packet.json", decoder_packet(data, result))
    write(args.output / "controls.json", checks)
    write(args.output / "coordinate_intervention_trace.json", changed)
    write(args.output / "timing.json", dict(
        first_search_s=first_s, median_search_s=statistics.median(timings),
        min_search_s=min(timings), max_search_s=max(timings), repeats=len(timings), raw_seconds=timings,
        includes="input validation, full atlas construction, native context allocation, 64 source steps, audit expansion, semantic readout",
        excludes="imports, C++ build/load, disk serialization, LLM encoding/decoding",
        llm_latency_measured=False,
    ))
    paths = [WS / "source.py", WS / "fast_source.py", WS / "native" / "white_star.cpp"]
    paths += sorted((WS / "source_primitives").glob("*.py"))
    write(args.output / "manifest.json", dict(
        experiment="NOBS_WHITE_STAR_LLM_001", input_sha256=result["input_sha256"],
        input_file_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(), input_freeze=freeze,
        python=platform.python_version(), platform=platform.platform(),
        unchanged_kernel_files={str(p.relative_to(WS)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        optimizer="existing native WhiteStar/CAD/UDAV; unchanged",
        new_code="concept-to-atlas compiler and projection-to-concept readout only",
        tsp_solver_invoked=False,
        llm="current conversation assistant supplies the input annotation and decodes the fixed first six frames",
        external_llm_api_calls=0, literary_quality_independently_evaluated=False,
    ))
    print(json.dumps(dict(summary=result["summary"], controls=checks,
                          median_search_ms=statistics.median(timings) * 1000), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
