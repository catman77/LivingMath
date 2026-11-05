#!/usr/bin/env python3
"""Exact post-search reachability, provenance and invariance audit."""
from copy import deepcopy
import argparse
from pathlib import Path
import hashlib
import json
import time

from formal_core import (HERE, BASE, WS, load_case, reachability, audit_observed,
                         check_certificate, encode, locate)
from annotate import make_certificate


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mutation_audit(data, trace, frames, certificate):
    """Faults target the formal boundary, not the literary merits of prose."""
    outcomes = []
    def reject(name, changed_data=None, changed_trace=None, changed_certificate=None, replay=False):
        try:
            check_certificate(changed_data or data, changed_trace or trace, frames,
                              changed_certificate or certificate, replay=replay)
        except (ValueError, KeyError, AssertionError) as error:
            outcomes.append(dict(name=name, status="REJECTED", reason=str(error)))
        else:
            raise AssertionError(f"mutation accepted: {name}")

    changed = deepcopy(data)
    changed["concepts"][0]["evidence"][0]["quote"] = "Утро"
    reject("invented_source_quote", changed_data=changed)
    changed_trace = deepcopy(trace)
    changed_trace[5]["coordinates"][0] += 1
    reject("changed_projection", changed_trace=changed_trace, replay=True)
    changed_trace = deepcopy(trace)
    changed_trace[5]["witness"][0] += 1
    reject("changed_division_witness", changed_trace=changed_trace, replay=True)
    changed = deepcopy(certificate)
    changed["readings"][0]["bindings"][0]["state"][2] = "ALIGN"
    reject("flipped_relation", changed_certificate=changed)
    changed = deepcopy(certificate)
    changed["readings"][0]["bindings"][0]["state"][3] = "light"
    reject("flipped_dominance", changed_certificate=changed)
    changed = deepcopy(certificate)
    changed["readings"][0]["bindings"][0]["status"] = "SOURCE_ENTAILED"
    reject("creative_link_promoted_to_source_fact", changed_certificate=changed)
    changed = deepcopy(certificate)
    changed["readings"][0]["bindings"].pop()
    reject("omitted_selected_link", changed_certificate=changed)
    changed = deepcopy(certificate)
    changed["readings"][0]["bindings"][0]["prose_excerpt"]["quote"] = "Несуществующая фраза"
    reject("invented_prose_excerpt", changed_certificate=changed)
    changed = deepcopy(certificate)
    changed["semantic_fidelity"] = "PROVED"
    reject("self_report_promoted_to_proof", changed_certificate=changed)
    changed = deepcopy(certificate)
    changed["readings"][0]["additions"][0]["status"] = "SOURCE_FACT"
    reject("metaphor_promoted_to_source_fact", changed_certificate=changed)
    changed = deepcopy(certificate)
    changed["source_assertions"][1]["world_truth"] = "TRUE"
    reject("speaker_no_exit_claim_promoted_to_world_law", changed_certificate=changed)

    # A deliberately contentless response WITH honestly typed annotations can
    # meet address/schema checks. Demonstrate the limit rather than hide it.
    empty = deepcopy(certificate)
    for reading in empty["readings"]:
        chunks = [f"Заглушка {i + 1}." for i in range(len(reading["bindings"]))]
        reading["text"] = " ".join(chunks)
        reading["text_sha256"] = hashlib.sha256(reading["text"].encode()).hexdigest()
        for binding, chunk in zip(reading["bindings"], chunks):
            binding["prose_excerpt"] = locate(reading["text"], chunk)
    limited = check_certificate(data, trace, frames, empty, replay=False)
    assert limited["semantic_fidelity"] == "UNASSESSED_BY_CHECKER"
    return dict(faults=outcomes, rejected_faults=len(outcomes),
                contentless_text_control=dict(
                    structural_checks_pass=True, semantic_status=limited["semantic_fidelity"],
                    conclusion="An addressed self-annotation is not a proof of prose fidelity. This checker does not accept or grade prose semantically."))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "results")
    args = parser.parse_args()
    started = time.perf_counter()
    data, trace, frames, prose = load_case()
    reachable = reachability(data)
    observed = audit_observed(data, trace, frames, reachable)
    certificate = json.loads(encode(make_certificate(data, trace, frames, prose)))
    checked = check_certificate(data, trace, frames, certificate)
    mutations = mutation_audit(data, trace, frames, certificate)
    baseline = json.loads((BASE / "results/manifest.json").read_text())["unchanged_kernel_files"]
    unchanged = {name: hashlib.sha256((WS / name).read_bytes()).hexdigest() == expected
                 for name, expected in baseline.items()}
    if not all(unchanged.values()):
        raise ValueError("kernel changed relative to experiment 001")
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in [("reachability", reachable), ("observed", observed),
                        ("interpretation_certificate", certificate), ("certificate_check", checked),
                        ("mutation_audit", mutations), ("kernel_integrity", unchanged)]:
        write(args.output / f"{name}.json", value)
    summary = dict(experiment="NOBS_WHITE_STAR_LLM_002_FORMAL", reachable=reachable["summary"],
                   observed=observed["summary"], certificate=checked,
                   rejected_faults=mutations["rejected_faults"], kernel_unchanged=all(unchanged.values()),
                   search_algorithm_modified=False, new_interpretations_generated=False,
                   scope="Retrospective formalization and exact reachability of experiment 001",
                   elapsed_seconds=time.perf_counter() - started)
    write(args.output / "summary.json", summary)
    paths = list((BASE / "input").glob("*")) + [BASE / "results" / n for n in
             ["trace.jsonl", "frames.json", "decoder_response.json", "manifest.json"]]
    write(args.output / "input_hashes.json", {str(p.relative_to(BASE)): hashlib.sha256(p.read_bytes()).hexdigest()
                                              for p in paths if p.is_file()})
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
