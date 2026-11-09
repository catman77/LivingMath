# Semantic Bridge PATCH002 Implementation Plan

**Goal:** eliminate direction/pair starvation and certify the specified mixed-prefix/negation rules without changing the 102 MCP schemas or historical kernels.

**Architecture:** retain the existing contextual worker, Workspace, immutable service and contracts. Extend only contextual proof generation/checking and replace serial directional searches with one deterministic finite-model stream shared by every unresolved pair. Each world is evaluated for both directions, with per-world formula caching. Existing FOL evaluation remains the reference semantics.

**Spec:** [original TZ](../SEMANTIC_BRIDGE_PATCH002_20261109/TZ_RU.md) and its fixtures. The prompt's `reference/REPORT_RU.md` is named `reference/EXP02_REPORT_RU.md` in the actual archive; read that exact supplied file. Baseline `b48c44e0793490d7157df710cf9b2faa9cd3acb2`, deployed code `23c4aac0d2793170def4642e0e53bde59e741ac4`.

## Constraints

- Preserve all 102 complete MCP schemas, source hypotheses, OPEN obligations, SQLite and historical journal prefixes. No new production database or migration.
- No modifications to `formal_bridge/`, numerical/native/UDAV/CAD/NOPS kernels. No server-side NLP or LLM. No automatic semantic license or execution grant.
- Model bound ≤512; principal cases use 32/64. Atoms ≤10; existing worker 5 CPU seconds, 6 wall seconds, 512 MiB, shared 2-active/16-queued admission unchanged.
- User instruction: GitHub Actions disabled at repository level and workflows archived; all builds, checks and deployments local. No CI workflow dispatch or build polling.
- Preserve root's 87 pre-existing tracked changes in an isolated worktree. Execute the approved specification inline; no additional design approval requested.

## Tasks and checks

- [x] Copy immutable ZIP and verify every supplied SHA; verify six actual runtime/source blobs and real public baseline schemas. Write precise initial RCA.
- [x] Add failing tests in `tests/test_contextual_semantic_bridge002.py` for existential projection, mixed-prefix monotonicity, NNF, adversarial certificates and swap/fairness. Record initial failures.
- [x] Add bounded canonical NNF and mixed-prefix proof certificates in contextual proof code. Independently reconstruct original AST bindings and proof tables in `checker.py`; never import producer normalization there. Check strict JSON types and reject malformed/captured/sorted/forged certificates.
- [x] Add `finite.py`: sorted signature/domain/cell traversal for sizes 1,2, ≤16 relation cells; global unique world count, no duplicate model search per direction. Replace `pair`/`engine.analyze` scheduling with prepare-all-proofs, shared worlds for all unresolved directions, explicit directional and run coverage. Preserve found witnesses when other work exhausts bounds. Test 32/64 swap and permutation invariance.
- [x] Deliver client semantic audit/repair instructions using existing assumptions, obligations and construction traces. T4 message/fact and referent alternatives remain PROPOSED/OPEN; T6 static proxy remains lossy and temporal unsupported remains LANGUAGE_INSUFFICIENT. Provide a frozen, unexecuted blind A/B protocol without uplift claims.
- [x] Extend real MCP QA and stdlib-only independent verifier using supplied five logical fixtures, historical SB-EXP01 and EXP02 scenarios. Save exact calls/responses, certs, both countermodels, resource receipts, pagination, replay/tamper and scoped negative checks.
- [x] Build a fresh wheel locally; run installed full suite, original legacy suite and doctor. Exercise isolated staging with unchanged limits. Resolve every actual defect, retaining failed evidence.
- [x] Back up four actual SQLite stores plus Workspace; retain v0.4.14 wheel/runtime. Promote only accepted code, restart HTTP only, keep tunnel/address/no-auth. Run restricted real HTTPS canary in separate QA projects; inspect historical EXP02 without mutation and reject old binding replay.
- [x] Verify SQLite integrity, original rows/files/journal prefixes/hash chains, installed source manifest and all 102 schemas. Build machine gate matrix G0–G10 and required directional/model/proof/semantic provenance artifacts from actual receipts.
- [x] Final publication gate completed: repair documentation audit CURRENT; v0.4.15 GitHub release/tag published,1955 source blobs and ZIP SHA anonymously verified; exact binary patch reproduced; root source checkout fast-forwarded with all87 user changes/AGENTS preserved. [PUBLICATION_CERTIFICATE.json](PUBLICATION_CERTIFICATE.json) closes the source-snapshot pending publication. Actions remains DISABLED_BY_USER_REQUEST_NOT_EXECUTED, never CI PASS.
