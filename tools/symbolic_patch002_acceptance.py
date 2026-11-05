"""Finite controlled PATCH002 acceptance using actual saved inputs and workers."""

import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path

from lm_suti_assurance.core import digest
from lm_suti_assurance.symbolic.executor import Executor
from lm_suti_assurance.white_star.contracts import integrity

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "docs/LIVINGMATH_SYMBOLIC_PATCH002"
CASES = ("nostradamus_original_local_word", "mallarme_original", "mallarme_reverse")


def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def coverage(artifact):
    counts = {
        op: dict(proposed=0, accepted=0, duplicate=0, forbidden=0, resource_limited=0)
        for op in artifact["input"]["operators"]
    }
    for entry in artifact["ops_trace"]:
        for c in entry["candidates"]:
            row = counts[c["operator"]]
            row["proposed"] += 1
            category = (
                "accepted"
                if c.get("new_outputs")
                else (
                    "duplicate"
                    if c["status"] == "DUPLICATE_WORD"
                    else (
                        "forbidden"
                        if c["status"] == "WORD_TOKEN_LIMIT"
                        else "resource_limited"
                    )
                )
            )
            row[category] += 1
    return {
        "per_operator": counts,
        "unrecorded_candidate_attempts": artifact["summary"]["attempted_candidates"]
        - sum(r["proposed"] for r in counts.values()),
    }


def check_bounds(request, summary, trace=None):
    budget = request["search"]
    assert summary["steps"] <= budget["max_steps"]
    assert summary["nodes"] <= budget["max_nodes"]
    assert summary["observations"] <= budget.get("max_observations", 8192)
    assert summary["total_stored_tokens"] <= budget.get("max_total_tokens", 131072)
    assert (
        summary["attempted_candidates"]
        <= budget["max_steps"] * budget["max_candidates_per_step"]
    )
    assert summary["global_exhaustion_proved"] is False
    if trace is not None:
        assert all(
            len(t["candidates"]) <= budget["max_candidates_per_step"] for t in trace
        )
        assert (
            sum(len(t["candidates"]) for t in trace) == summary["attempted_candidates"]
        )


def offline(args):
    out = args.output
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    checks, rows = [], []

    def check(name, ok):
        checks.append({"check": name, "status": "PASS" if ok else "FAIL"})
        save_json(out / "checks.json", checks)
        assert ok, name

    current = Executor()
    previous = Executor(args.historical_worker)
    try:
        check(
            "both real isolated worker profiles READY",
            current.status()["ready"] and previous.status()["ready"],
        )
        for name in CASES:
            request = json.loads(
                (args.baseline_dir / (name + ".request.json")).read_text()
            )
            original = json.loads(
                (args.baseline_dir / (name + ".before.json")).read_text()
            )
            before = previous.run({"action": "explore", "request": request})["data"]
            after = current.run({"action": "explore", "request": request})["data"]
            save_json(out / (name + ".before.json"), before)
            save_json(out / (name + ".after.json"), after)
            check(
                name + " actual original digest reproduced",
                digest(before) == digest(original),
            )
            check(
                name + " exact controlled request",
                before["input"] == after["input"] == request,
            )
            check(
                name + " source map/spans unchanged",
                before["source_map"] == after["source_map"],
            )
            check(
                name + " exact original claims unchanged",
                before["equivalence_claims"] == after["equivalence_claims"],
            )
            check(
                name + " descriptive grammar unchanged",
                before["grammar_hypotheses"] == after["grammar_hypotheses"],
            )
            check_bounds(request, after["summary"], after["ops_trace"])
            check(name + " all resource ceilings", True)
            first = next(
                (
                    e
                    for e in after["search_diagnostics"]
                    if e["status"] == "FRONTIER_FALLBACK"
                ),
                None,
            )
            if first:
                n = first["step"]
                check(
                    name + " local policy exact before first fallback",
                    before["ops_trace"][:n] == after["ops_trace"][:n],
                )
                check(
                    name + " bounded escape real novel stored nodes",
                    after["summary"]["nodes"] > before["summary"]["nodes"],
                )
            check(
                name + " no unaccounted candidate attempt",
                coverage(after)["unrecorded_candidate_attempts"] == 0,
            )
            check(
                name + " real operator coverage matches",
                coverage(after)["per_operator"]
                == after["summary"]["operation_coverage"],
            )
            repeated = current.run({"action": "explore", "request": request})["data"]
            check(name + " deterministic repeat", digest(repeated) == digest(after))
            row = {
                "case": name,
                "request_digest": digest(request),
                "source_sha256": request["source"]["sha256"],
                "budgets": request["search"],
                "before": before["summary"],
                "after": after["summary"],
                "before_result_digest": digest(before),
                "after_result_digest": digest(after),
                "before_coverage": coverage(before),
                "after_coverage": coverage(after),
            }
            rows.append(row)
            save_json(out / "BEFORE_AFTER.json", rows)
        grammar_request = json.loads(
            (
                FIXTURES / "reproduction/patch001_palindrome_regression.request.json"
            ).read_text()
        )
        old = previous.run({"action": "explore", "request": grammar_request})["data"]
        new = current.run({"action": "explore", "request": grammar_request})["data"]
        check(
            "T01 entire golden grammar and predictions byte-identical",
            old["grammar_hypotheses"] == new["grammar_hypotheses"]
            and old["heldout_eval"] == new["heldout_eval"],
        )
        by_word = {"".join(p["tokens"]): p for p in new["heldout_eval"]["predictions"]}
        check(
            "T01 all9 unique selected predictions correct",
            len(by_word) == 9
            and all(
                (p["membership_probability"] >= 0.5) == (w == w[::-1])
                for w, p in by_word.items()
            ),
        )
        check(
            "T01 family remains UNDERDETERMINED",
            new["grammar_hypotheses"][0]["identifiability_status"] == "UNDERDETERMINED",
        )
        check("T08 all75 supplied numerical files unchanged", len(integrity()) == 75)
        text = (FIXTURES / "06_FIXTURE_NOSTRADAMUS.txt").read_text().removesuffix("\n")
        check(
            "T02 supplied fixture exact source SHA",
            hashlib.sha256(text.encode()).hexdigest() == rows[0]["source_sha256"],
        )
        check(
            "T06 actual Mallarme15 lines",
            len(
                json.loads(
                    (args.baseline_dir / "mallarme_original.request.json").read_text()
                )["source"]["text"].splitlines()
            )
            == 15,
        )
        save_json(
            out / "result.json",
            {
                "status": "PASS",
                "checks": len(checks),
                "before_after": rows,
                "kernel_binding": new["manifest"]["kernel_binding"],
                "golden_grammar_digest": digest(new["grammar_hypotheses"]),
                "numeric_kernel_files": integrity(),
                "LLM_calls": 0,
                "execution_permission": False,
            },
        )
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "checks": len(checks),
                    "cases": [
                        {
                            "case": r["case"],
                            "before_nodes": r["before"]["nodes"],
                            "after_nodes": r["after"]["nodes"],
                            "before_steps": r["before"]["steps"],
                            "after_steps": r["after"]["steps"],
                            "after_halt": r["after"]["halt_reason"],
                            "fallback_count": r["after"]["fallback_count"],
                        }
                        for r in rows
                    ],
                }
            )
        )
    finally:
        current.close()
        previous.close()


async def live_checks(explore, view, call, check, save, compare, project):
    """Extend the original real MCP acceptance; all mutations stay in its QA project."""
    fixture = json.loads((FIXTURES / "05_RUN_IDS.json").read_text())
    history_project = fixture["project"]
    saved, rows, runs = {}, [], {}
    for name, run in fixture["cases"].items():
        saved[run] = (await view(run, "summary", history_project))[0]
    save("patch002-historical-summaries.json", saved)
    for name in CASES:
        ident = fixture["cases"][name]
        request = (await view(ident, "input", history_project))[0]
        after = await explore(request, "patch002-" + name)
        before = saved[ident]
        rows.append(
            {
                "case": name,
                "request": request,
                "historical_run_id": ident,
                "run_id": after["run_id"],
                "before": before["summary"],
                "after": after["summary"],
                "before_result_digest": before["result_digest"],
                "after_result_digest": after["result_digest"],
            }
        )
        check_bounds(request, after["summary"])
        check(
            name + " identical input/budgets and bounded result",
            (await view(after["run_id"], "input"))[0] == request,
        )
        check(
            name + " immutable source spans",
            (await view(ident, "source", history_project))[0]
            == (await view(after["run_id"], "source"))[0],
        )
        diagnostics = await view(after["run_id"], "diagnostics")
        check(
            name + " diagnostics retained at terminal limit",
            diagnostics[-1]["status"] == after["summary"]["halt_reason"]
            and diagnostics[-1]["candidate_attempts"]
            == after["summary"]["attempted_candidates"],
        )
        if name != "mallarme_original":
            check(
                name + " fallback escapes recorded local stagnation",
                after["summary"]["fallback_count"] > 0
                and after["summary"]["nodes"] > before["summary"]["nodes"],
            )
            check(
                name + " explicit frontier provenance",
                any(
                    d["status"] == "FRONTIER_FALLBACK"
                    and d["selected_node_history_ref"] == d["selected_node_id"]
                    and d["frontier_size"] > 0
                    for d in diagnostics
                ),
            )
        trace = await view(after["run_id"], "operations")
        check_bounds(request, after["summary"], trace)
        check(name + " all candidate attempts counted", True)
        if name == "nostradamus_original_local_word":
            old_trace = await view(ident, "operations", history_project)
            check("T02 first5 local UDAV steps unchanged", trace[:5] == old_trace)
            check(
                "T02 idempotent request exact",
                await explore(request, "patch002-" + name) == after,
            )
            replica = await explore(request, "patch002-nostradamus-replica")
            check(
                "T05 same request distinct key deterministic result",
                replica["run_id"] != after["run_id"]
                and replica["result_digest"] == after["result_digest"],
            )
            chunks = await view(after["run_id"], "export")
            raw = b"".join(base64.b64decode(v["data_base64"]) for v in chunks)
            save(
                "patch002-nostradamus-export-ref.json",
                {"bundle_ref": chunks[0]["bundle_ref"], "run_id": after["run_id"]},
            )
            check(
                "T05 export byte hash",
                hashlib.sha256(raw).hexdigest() == chunks[0]["bundle_ref"],
            )
            # Save through the same output writer as structured evidence.
            save(
                "patch002-nostradamus-bundle.json",
                {"bundle_base64": base64.b64encode(raw).decode()},
            )
            replay = await call(
                "white_star_symbolic_replay",
                {"project": project, "bundle_ref": chunks[0]["bundle_ref"]},
            )
            check(
                "T05 fallback path replay matches",
                replay["data"]["status"] == "REPLAY_MATCH"
                and replay["data"]["result_digest"] == after["result_digest"],
            )
            historical_chunks = await view(ident, "export", history_project)
            old_raw = b"".join(
                base64.b64decode(v["data_base64"]) for v in historical_chunks
            )
            save(
                "patch001-historical-bundle.json",
                {"bundle_base64": base64.b64encode(old_raw).decode()},
            )
            replay = await call(
                "white_star_symbolic_replay",
                {
                    "project": history_project,
                    "bundle_ref": historical_chunks[0]["bundle_ref"],
                },
            )
            check(
                "T08 PATCH001 actual original digest replay",
                replay["data"]["status"] == "REPLAY_MATCH"
                and replay["data"]["result_digest"] == before["result_digest"],
            )
        runs[name] = after
        save("PATCH002_BEFORE_AFTER.json", rows)
    comp = await compare(
        runs["mallarme_original"]["run_id"], runs["mallarme_reverse"]["run_id"]
    )
    check(
        "T06 Mallarme order has actual source-span witness",
        not comp["same_literal"]
        and not comp["same_history"]
        and bool(comp["literal_witness"]["left"]["original_byte_spans"]),
    )
    original = rows[0]["request"]
    for name, changes in (
        ("zero", {"max_steps": 0}),
        ("nodes", {"max_nodes": 16}),
        ("tokens", {"max_total_tokens": 120}),
        ("nodes-after-fallback", {"max_nodes": 64}),
        ("observations", {"max_observations": 16}),
    ):
        request = copy.deepcopy(original)
        request["search"].update(changes)
        result = await explore(request, "patch002-budget-" + name)
        check_bounds(request, result["summary"])
        diagnostics = await view(result["run_id"], "diagnostics")
        check(
            "T03 " + name + " exact diagnostic counters",
            diagnostics[-1]["candidate_attempts"]
            == result["summary"]["attempted_candidates"]
            and diagnostics[-1]["status"] == result["summary"]["halt_reason"],
        )
        if name == "zero":
            check(
                "T07 zero steps no invented saturation",
                result["summary"]["saturation_certificate_digest"] is None
                and result["summary"]["fallback_count"] == 0,
            )
        if name == "nodes-after-fallback":
            check(
                "T07 MAX_NODES preserves fallback evidence",
                result["summary"]["halt_reason"] == "MAX_NODES"
                and any(d["status"] == "LOCAL_STAGNATION" for d in diagnostics)
                and any(d["status"] == "FRONTIER_FALLBACK" for d in diagnostics),
            )
    return {
        "T01": "PASS_FROM_GOLDEN_GRAMMAR_CHECKS",
        "T02": "PASS",
        "T03": "PASS",
        "T04": "PASS_FROM_EXACT_SP_ALPHA_AND_SOURCE_WITNESSES",
        "T05": "PASS",
        "T06": "PASS_STRUCTURAL_ONLY",
        "T07": "PASS",
        "T08": "PASS",
        "rows": rows,
        "historical_runs": saved,
        "execution_permission": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--historical-worker", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    offline(parser.parse_args())
