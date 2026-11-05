# Symbolic Acceptance PATCH-001 Implementation Plan

**Goal:** close the narrow live acceptance findings with compositional hypotheses, honest active queries, local search diagnostics and exact historical replay.

**Spec:** `docs/LIVINGMATH_SYMBOLIC_V1_ACCEPTANCE_PATCH001/{02_TZ_PATCH001_RU,04_TEST_PROTOCOL_RU}.md`.

**Architecture:** extend the existing symbolic grammar/search/service; keep numerical White Star and S/P operations byte-identical. Add one inspect comparison view with an optional second run ID. Historical symbolic replay runs the already-installed immutable v0.4.0 worker selected by its approved binding, rather than copying/reimplementing the old kernel. Inline execution under the user's supplied implementation/deployment authorization.

## Constraints

No new grammar engine/DSL, no exhaustive enumeration, no LLM/network in workers, no hidden labels/predict words inside fit; 5CPU/6wall seconds/512MiB and all current quotas remain. No overwriting old runs, journals, claims or databases. No UNIQUE or theorem-level generalization from train accuracy.

## Tasks

- [x] Save source ZIP unchanged, read the full handoff and run the existing252-test baseline before modifying implementation. Back up four actual SQLite stores, private configuration and1604 existing workspace files; capture real75-tool endpoint and historical bindings.
- [x] Extend `symbolic/grammar.py` with bounded candidate derivation from observed equality on SPLIT/REVERSE-aligned fragments. Infer recurrence only from repeated train witnesses, test every retained candidate against train, and keep finite-depth/endpoint alternatives. Preserve legacy tree/probability fields, add AST/witnesses/scope/complexity and candidate/family statuses. Generate at most64 train-derived local substitution/composition probes; freeze before reading queries.
- [x] Extend kernel predictions with per-candidate decisions, INCONCLUSIVE on family disagreement and unchanged frozen hypothesis digest. Independent harness owns all palindrome labels, deduplicates the9 supplied holdouts and tests additional6/8/10-token cases and A/B renaming.
- [x] Add a local no-growth diagnostic in `symbolic/search.py` without modifying proposal generation/selection. Certify actual sampled variants, rejection reasons, allowed/unproposed operations, current word/clock, explicit bounded scope and no global no-go. Keep new provenance paths.
- [x] Add `white_star_symbolic_inspect(view="comparison",compare_run_id=...)` in existing service/metadata. Return all six explicit equality flags, applicable scopes, original source/span witnesses, exact SP reductions and retained operation paths. Reject cross-project run IDs and incomparable observer indices explicitly.
- [x] Add trusted historical replay profiles to the existing executor/release entry. Validate the immutable old layer manifest before starting its already-supplied worker. Never use caller-controlled executable paths or code from ZIP. Existing numerical application files and75 frozen sources remain unchanged.
- [x] Run exact/unit/metamorphic, package install, worker quota/offline checks, old/new replay and live OAuth/MCP acceptance. Read all supplied historical IDs without altering them. Run Mallarme controls using the exact existing fa7e... source snapshot.
- [x] Produce PATCH001_IMPLEMENTATION_RU.md, REGRESSION_RESULTS.json, BENCHMARK_REPORT_RU.md, CHANGED_FILES.md and a small delivery with all acceptance rows PASS/FAIL/BLOCKED. Preserve initial failures. Bump package/release to0.4.1 only after acceptance; build a pinned manifest, back up quiescent stores, restart HTTP only, verify same address and every original row/object/journal prefix.
