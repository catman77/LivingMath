# MCP Completeness 001 Implementation Plan

**Goal:** Opt-in certified finite qualitative coverage for `cj_v1`, through the existing source compiler, CAD primitive, isolated workers and immutable Workspace.

**Architecture:** Separate constructor, independent exact-cell checker, bounded worker and project-owned journal service. Four additive tools expose immutable plans, resumable execution, record pagination with explicit delivery acknowledgement, and replay. Existing selectors, schemas, journals and vendor files remain unchanged.

**Tech Stack:** Python integers/Fraction, existing JSON Schema, FastMCP, Workspace, fork isolation and shared worker quotas.

**Spec:** Private supplied `docs/MCP_COMPLETENESS_001_20261112.zip`, `THEORY_COMPLETENESS_RU.md` and `PATCH_CONTRACT_RU.md`; pinned source `b5408c7aa040ebaa018625282196e37d9516e6d9`.

## Constraints

- Only `completeness_only`, `cj_v1`, observer `pair-sign-and-absolute-dominance/1`; coordinate bound 1000000, original worker/resource and chart limits.
- No vendor/Pair/orbit/clock/CAD/legacy-selector changes, LLM, semantic verification or execution grants.
- No source publication; private original fixture and transcripts stay outside Git. No intermediate archives or full project backups.
- No hardcoded fixture denominator: derive admitted pairs/targets and independently check every exact cell.

## Execution (inline, authorized by the supplied prompt)

- [x] Constructor/checker: compile through installed atlas, synthesize adjugate witnesses, verify exact target domain and all bindings. Test missing/forged targets, source, aliases, coordinate boundaries, collinearity and base rejection.
- [x] Worker: invoke the unchanged `cad.project` on actual division witnesses, check orbit addresses without prefix execution, preserve matrices/aliases/provenance. Reuse existing bounded transport and numeric shared budget. Test real isolated execution/replay.
- [x] Service: immutable plans, atomic verified prefix receipts/checkpoints, retries and conflict rejection; explicit PARTIAL/ERROR, stable 64/64/64/32 pages, digest-bound client acknowledgement. Test restart, concurrency and interrupted commit.
- [x] MCP: four strict additive tools and opt-in release registration; compare all old tool schemas and traces. Run a real MCP client with complete wire requests/responses and the private supplied fixture.
- [x] Delivery: independent checker plus supplied 25 reference tests and relevant legacy regressions, safe usage/architecture documentation, diff/hashes/pinned commit, receipts, RCA and deployment/rollback status. Recheck unmodified kernel and original working changes; production deployment requires a factual separate receipt.
