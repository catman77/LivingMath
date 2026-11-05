# SYMBOLIC_V1 PATCH002 Implementation Plan

> Inline execution in this session; the user supplied the approved specification and explicitly authorized implementation and production deployment.

**Goal:** Escape bounded local stagnation through deterministic untried stored-node/operator proposals, preserving symbolic mathematics and all existing resource limits.

**Architecture:** Extend the existing search controller only. Keep local seeded set-inclusion proposals/selection unchanged until stagnation; select a stored node and untried operator by digest(seed, operator, node_id), execute in the next ordinary candidate slot, and retain exact DAG witnesses. Append honest diagnostics and bounded coverage counters; retain immutable installed historical profiles for replay.

**Tech Stack:** Python>=3.13, existing isolated symbolic workers, pytest, real MCP SDK over HTTPS/OAuth, existing SQLite and append-only workspaces.

**Spec:** docs/LIVINGMATH_SYMBOLIC_PATCH002/{README_RU.md,02_TZ_PATCH002_RU.md,03_PROMPT_CODE_AGENT_RU.md,04_TEST_MATRIX_RU.md}.

## Global Constraints

- Numerical White Star base_v1/cj_v1,75 supplied files, grammar.py, state.py, observers.py, contracts.py, frozen verifier and AGENTS.md unchanged.
- Same input schemas, word/provenance choice, source spans, resource ceilings and worker quotas. No new engine/DSL, full graph enumeration, LLM/network, global no-go or semantic-truth claims.
- Archive retained bytewise, SHA256549dfd97c61023b42bb26021d79b43eca6f4087faeaa909902e1450ec06c7834.
- Actual pre-edit baseline261 PASS; historical Nostradamus fixture and digest reproduced exactly. Preserve original non-task working tree changes.

## Task1: Reproduce and map policy failure

- [x] Read all7 supplied files; save archive under docs and copy to isolated worktree.
- [x] Back up all4 actual SQLite databases and2272 pre-existing workspace files; capture75 actual tools and31 read-only MCP calls.
- [x] Recompute supplied Nostradamus/Mallarme histories with exact immutable v0.4.1 worker; retain actual requests/artifacts and digests.
- [x] Save source-level RCA: empty-word proposal cycle, untried stored-node/operator pairs and an explicit admissible novel witness under identical budgets.

## Task2: Bounded frontier escape and diagnostics

**Files:** src/lm_suti_assurance/symbolic/search.py; tests/test_symbolic_patch002.py; one outdated halt assertion in tests/test_symbolic_patch001.py.
**Consumes:** search(request, history, roots, observer, clock_factory), unchanged History.add/apply/witness_set.
**Produces:** same output keys plus controller policy, LOCAL_STAGNATION/FRONTIER_FALLBACK/ACTUAL_LOCAL_EXHAUSTION and terminal diagnostics, per-operator coverage, attempted-pair frontier and fallback provenance.

- [x] Red tests for exact Nostradamus request: fallback_count>0, remaining frontier cannot cause terminal exhaustion, same result twice, correct budgets.
- [x] Add finite tried[node_id] operator sets; next frontier=min(untried pairs,key=digest([seed,operator,node_id])). No extra apply outside existing loops.
- [x] Forced fallback slot consumes one existing clock step and ordinary candidate slot; other local proposal/selection logic stays unchanged.
- [x] Retain diagnostics at MAX_NODES/MAX_TOTAL_TOKENS/MAX_STEPS; distinguish coverage of one sampled argument per node/operator from complete parameter-space exhaustion.
- [x] Test word/provenance, seed determinism, zero steps, small limits, reverse-only bounded exhaustion, no repeated forced pair, original source spans and SP/alpha invariants.

## Task3: Controlled integration and historical compatibility

**Files:** tools/symbolic_patch002_acceptance.py; optional existing symbolic/mcp.py metadata; kernel.py version/manifest; release_v01_entry.py version allowlist.

- [x] Run unchanged grammar gate9/9 with family UNDERDETERMINED; verify grammar source and golden frozen output digests.
- [x] Compare identical requests from immutable v0.4.1 and patched workers on Nostradamus,15 actual Mallarme lines and reverse; retain full artifacts, budgets and actual operator coverage.
- [x] Source mismatch, Unicode, tamper, deterministic digest, data-only export/replay and exact witnesses; old numeric profiles and old symbolic replay remain intact.
- [x] Run full pytest and legacy suite; build/install wheel and verify outside checkout. Bump version only after actual finite gates pass.

## Task4: Deploy and deliver

- [x] Rehearse on copied databases/workspaces through real MCP, unchanged schemas and exact historical replay profiles; record all calls/results.
- [x] Take fresh quiescent backups, install exact accepted manifest/wheel, restart HTTP only and preserve tunnel/address; run actual HTTPS/OAuth acceptance in separate QA project.
- [x] Assert original rows/files/hash-chain, historical run IDs, source/vendor hashes and shared resource quotas preserved; no unfinished QA run.
- [x] Write RCA, before/after table, regression JSON, golden hashes, changed files, version/deployment/manifest, reproducible small ZIP with credential exclusions and hash manifest.
- [x] Commit task-only changes and fast-forward main without overwriting pre-existing .gitignore or unrelated files.

Execution closure: source/wheel272 PASS; legacy1066 PASS/20 SKIP; controlled38 PASS; staging247 PASS; production248 PASS. Delivery/source bookkeeping is recorded by SOURCE_COMMIT.json and DELIVERY_VERIFIED.json in the delivery evidence.
