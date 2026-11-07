# LM-NL-CAUSAL-003 implementation plan

The supplied TZ and prompt are the approved design. Add one opt-in tool to
existing FastMCP; retain all93 old tool schemas and old decoder/replay semantics.

1. Capture actual endpoint, code, schemas and integrity before changes. Recover
   old C through owned storage and actual MCP without model inference. Back up
   all4 real SQLite stores and workspace bytes before operational changes.
2. `nl_proposal/causal.py`: immutable four-arm engine; exact frozen base proposals;
   one decoder-only sham; trace-blind bounded primitive BFS and checked paths.
3. `nl_proposal/finite_relations.py`: independent exact finite evaluator,
   five-way relation classification, complete enumeration versus UNKNOWN and
   explicit directional countermodels. Preserve semantic PROPOSED on all branches.
4. `nl_proposal/causal_service.py`: owned immutable source resolution, replay gate,
   hashed data-only bundles, idempotent append-only records and inspector wrapper.
   Register only formal_nl_redecode; old93 schemas remain byte-identical.
5. Test real U21–U25 frozen receipts: one-swap reproduction and176/530 differences;
   preserve/exclude invalid U26. Negative tests cover types, capture, NOT boundary,
   missing/fake/foreign/mutated provenance and resource exhaustion.
6. Precommit new3+quantifier sources and assistant-authored reference limitations.
   Obtain independent real model receipts, freeze, then run4 arms with zero new
   provider calls. Human semantic licensing remains HUMAN_NOT_EVALUATED.
7. Execute actual1024 old control rows and12 old replays, source/wheel tests,
   real HTTPS/OAuth new tool, immutable replay and database/hash-prefix checks.
8. Publish source/patch, raw receipts, TEST_MATRIX with execution-evidence levels,
   RCA, scope/budgets, rollback and one verified downloadable ZIP. Deploy only
   after engineering acceptance; retain failed attempts and all original history.
