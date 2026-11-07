# NL002 read-only release and coverage review

Verdict: **no reproduced blocking defects; no outstanding findings in this review scope**.

Reviewed frozen commit `429a53dbaa6659a0803cb06e05e00d667f71c46e` against `08e936a`, in `/home/catman/CatmanCode/LivingMath/.worktrees/nl002`. Scope was the new NL namespace, additive release registration, QA helpers, operational lifecycle, receipt/replay bindings, bounds and public usage/rollback documentation. Repository source was not edited. Sealed holdout gold was not opened, and no model/network calls were made by the added local probes.

## Direct evidence

- `PYTHONPATH=src python -m pytest -q tests/test_nl_proposal.py`: **17 passed in 2.86 s**. The committed tests cover exact bytes/NFC reverse maps, source tampering, ill-typed candidates, causal quantifier moves, proposed-only semantic status, exact-AST deduplication, replay tampering, real symbolic references, project isolation, request-key conflict and concurrent admission.
- Independent local lifecycle/pagination probe: **18 checks passed**, recorded in `release-review-probes.json`. Twelve simultaneous submissions of one pending key generated one start and one provider call. Completed and failed retries remained immutable. Receipt mismatch and token overrun became journaled `FAILED` results. Large result pages reconstructed all bytes with the advertised SHA256 and replayed without a second provider call. Startup recovery persistently marked a reserved but unfinished job `INTERRUPTED_REQUIRES_NEW_KEY`, was idempotent, and did not rerun the provider for its old key. Unavailable providers returned no fabricated candidate. Source-token and batch-schema boundaries were rejected correctly; the resulting journal hash chain validated.
- Compared captured pre-change `tools-before.json` with real staged `dev-p0/tools.json`: **91 old tool records unchanged**, no removals, exactly `formal_nl_propose` and `formal_nl_inspect` added, total **93**.
- `git diff --name-only 08e936a 429a53d` across `white_star`, `symbolic`, `symbolic_complex`, `observer_synthesis` and `formal_bridge`: **no changed files**.
- Read the origin specialist's final report, including real symbolic/numeric causal probes, provenance mutation rejection, four-job concurrent admission and completed-key retries at capacity. Its previously reproduced defects were already repaired in this frozen snapshot.

## Implementation and documentation assessment

`service.py` serializes admission around immutable reservation; existing-key lookup precedes capacity rejection. The append-only lifecycle records each terminal outcome, and restart recovery requires a fresh key. Inspect performs project-owned lookup and explicit byte pagination. `decoder.py` replay binds the request, policy, exact source packet, trace digests, provider raw bytes and decoded AST set. Replay is a local deterministic path.

MCP contracts cap six sources, four supplied traces/frames, eight candidates per source and one provider call. The owner pipe serializes provider access and bounds request/receipt bytes. The advertised token limit is a post-call usage check, and the CPU limit applies to measured decoding; the documentation and capabilities do not claim a hard CLI token ceiling. Provider model revision, sampling seed and temperature remain explicitly uncontrolled. These disclosed limits do not establish a hard bound on model latency or generation cost.

Origin, typing, finite checks and semantic interpretation remain separate. Traced search cues may produce a different well-typed AST, but added scope assumptions stay unadjudicated. `semantic_alignment_status` and `proof_status` remain `PROPOSED`, and execution permission remains false. Matched-ablation moves are labeled as controls rather than trace-checked origin. The usage documentation explains polling, project ownership, exact-source guards, private bundle contents, rights as a nonempty string, pages and unavailable-provider outcomes. Rollback preserves new append-only records and restores code/configuration without discarding data.

## Existing release evidence inspected

Source and installed-wheel logs each show **447 passed**. Real staged dev A/B/C/D completed for six sources; a separate symbolic B run completed for two sources; real MCP provenance controls show **10 PASS**. Historical staging logs show **31 gates / 943 checks**, edge **41**, continuation **8547**, role acceptance **333**, generator **916**, and Formal Bridge **869 checks / 667 calls** passing. These are existing coordinator-run artifacts, not additional executions by this reviewer. The coordinator reports the legacy suite as **1066 passed / 20 skipped**.

## Acceptance boundary

This review completes the engineering inspection of the frozen code snapshot. The new matched 50-source A/B/C/D blind run was still in progress when review began; its completion, candidate freeze, post-freeze independent scoring, final report/artifact assembly and production cutover/readback remain coordinator responsibilities. Do not treat this review as evidence that those pending operations have completed.

Human semantic adjudication is intentionally **NOT_EXECUTED**. Scientific acceptance remains **PARTIAL**, semantic generalization **NOT_EVALUATED**, and White Star incremental benefit **NOT_ESTABLISHED** unless separately supported by the completed controls. Synthetic reference/vector agreement and finite countermodels must not be renamed human semantic accuracy or unrestricted logical equivalence.
