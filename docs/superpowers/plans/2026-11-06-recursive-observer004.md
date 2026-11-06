# PATCH004 Compositional Observer Implementation Plan

> Execute inline task by task; independent review follows implementation. The supplied specification already authorizes design, implementation, deployment and GitHub publication.

**Goal:** Promote source-bound typed recursive compositions and generate bounded two-fragment comparisons, with real MCP P0/P1 acceptance.

**Architecture:** Keep the existing context promotion default. Add a closed typed evaluator, independent checker and train-only compositional promotion route; retain immutable legacy kernels for replay/verification. Reuse existing workspaces, primitive operations, HTTP/OAuth and shared worker quota.

**Tech Stack:** Existing Python3.13 package, FastMCP1.30, SQLite legacy, immutable project objects/journals, Linux Landlock workers.

**Spec:** `docs/LIVINGMATH_RECURSIVE_OBSERVER_PATCH004_20261106/{02_FORMAL_MODEL_RU.md,03_TECHNICAL_SPEC_RU.md,04_MCP_CONTRACTS_RU.md,06_ACCEPTANCE_MATRIX_RU.md}`.

## Global constraints

- Numeric/vendor, `_frozen`, `symbolic_v1`, SP model/checker and workspace semantics remain unchanged.
- No new fundamental operation, language-specific flags, eval/exec, LLM, network or arbitrary worker paths.
- Default requests retain literal-context route; optional promotion policy is additive.
- New scope: at most8 tokens,32 AST nodes,8 AST depth,8 recursive iterations,256 train witnesses; all worker CPU5s/wall6s/RAM512MiB limits remain.
- Freeze before queries; external gold never enters workers. UNKNOWN beyond scope, UNDERDETERMINED family, no universal/verified/grant claims.
- All original records, objects and hash-chain prefixes are preserved; backups before code and before cutover.

## Tasks

- [x] Archive unchanged, verify21 checksums, inspect live0.4.5, backup4 SQLite+26876 files; capture19 original runs and reference16 tests.
- [x] Add failing regression tests for PAL/COPY discovery, source binding, hostile certificates, scope, effective ablations and default compatibility.
- [x] `composition_ast.py`: exact closed shapes, static types/decrease/bounds, execution via existing SPLIT/REVERSE and literal equality, complete source-state trace.
- [x] `composition_checker.py`: independent source reconstruction and step replay; no producer calls, complete coverage and claimed scope verification.
- [x] `compositional.py`: reuse actual relational_candidates, enumerate generic structural cuts/equality, retain rejected/compatible alternatives, deterministic train-only selection and feature admission.
- [x] Wire optional policy in contracts/features/learner; freeze query-free model; produce prediction evidence digests. No builtin execution for operator-only mode.
- [x] Bind same-project source_run_id to actual saved input/result/kernel/AST/train semantics; explicit mismatch rejection, no silent fallback. Preserve old-key idempotency; approved historical verifier/replay routing.
- [x] Freeze unchanged fixture inputs and isolated scorer; complete P0/P1 controls and short P2 Dyck representation test, obey roadmap stop criteria for corpus.
- [x] Run all source/installed-wheel/legacy regressions and real staged/public MCP A01-A25/B01-B06; source old numeric/SP/Symbolic/FIX-B2 regressions retained.
- [x] Review exact code, build0.4.6 wheel, back up at quiescent cutover, restart HTTP only, validate83 tools and production data prefixes; keep URL/tunnel.
- [x] Deliver one checksummed ZIP with source patch/code, commits, fixtures, external scorer, full MCP traces and RCA_RU/CHANGELOG_RU/ACCEPTANCE_RU; GitHub prerelease and sources after positive public acceptance.
