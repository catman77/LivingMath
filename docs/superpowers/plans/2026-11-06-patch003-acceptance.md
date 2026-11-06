# PATCH003 acceptance follow-up implementation plan

Goal: implement FIX-A/B and independently validate FIX-C, then deploy the exact accepted layer to the existing HTTPS endpoint. The supplied FOLLOWUP_FIXES_RU.md is the approved scope; no additional design approval is required.

## Constraints

Keep numeric White Star, symbolic_v1 and SP checker byte-identical; change only SP summary construction for FIX-A. Preserve every DB/object/journal prefix and the previous extension replay binding. Retain2 active/16 queued, CPU5s/wall6s/RAM512MiB, data-only exports, no network or LLM inside workers. Use existing relation AST and primitive operations; introduce no language flag or DSL.

## Steps

1. Baseline: verify3 supplied checksums, back up4 SQLite stores and workspaces, run12 reference tests,302 source tests and real old-interface server regression. Preserve incoming report/run IDs unchanged.
2. FIX-A: add failing regressions for N6 bigons/diamonds and N10 none. Summary assumptions derive from checked missing_peaks; expose selected_cells_policy, unresolved_peaks, partial_attachment. Leave builder mathematics and checker unchanged.
3. FIX-B: freeze a task protocol before inference: all64 binary words length6 train; all256 length8 queries; target second/penultimate literal equality computed only by the external label holder. Restrict allowlist to derived:* and explicitly deny pair_0_max/min/final. Same seed/budgets and train/query records with derivation disabled as ablation. Use the existing aligned_token_equality AST with train-inferred offset; assert no builtin feature is evaluated.
4. Execute the existing AST through real immutable symbolic.state.apply, retaining input/output word hashes, full content-addressed states and UTF-8 lineage. Independently validate AST, source spans, readout and every operator step without calling the trace producer or symbolic.grammar.relation_value. Reject modified AST, output hashes, source spans and unsupported operators. Add an additive observer_verify MCP tool, preserving all82 previous schemas.
5. Preserve replay by validating owner-installed old extension layer hashes and selecting its existing worker through the same SharedBudget. New engines use a new exact binding; old runs and export bytes stay untouched.
6. FIX-C: verify every original/swap record against source-bound century/quatrain/line/word hierarchy and immutable parent source slices;942 pair IDs, per-variant alpha, all anomalies/editions retained. Rerun13 configurations on the same frozen I–VIII / IX–X split and budgets through local and real MCP clients; preserve negative transfer.
7. Local/installed-wheel tests and staging actual MCP acceptance, then quiescent backup and production HTTP-only replacement. Verify real public HTTPS/OAuth, old83/82 schemas as applicable, all prior82 unchanged, numeric/frozen hashes, old extension replay and every historical summary.
8. Publish reports, exact requests/responses, run IDs, SHA manifests, patch and reproducible data-only exports. Integrate task commits into main while preserving user AGENTS/.gitignore changes; no GitHub push required.
