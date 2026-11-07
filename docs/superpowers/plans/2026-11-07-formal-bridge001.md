# Formal Bridge001 Implementation Plan

> Execute inline. User-approved supplied architecture/spec is authoritative; no extra design/deployment approval. Preserve all unrelated user changes.

**Goal:** Implement bounded CFG/DFA induction, independently checked forest/trace, contrast and source-bound typed FOL proposals in existing MCP.
**Architecture:** Add formal_bridge namespace over existing Workspace and shared isolated symbolic executor, using existing observer_verify action dispatch. Reuse source-checked datasets and immutable journal; no oracle production import. Separate grammar IR/search/chart, independent proof checker, DFA, typed FOL and service/API.
**Tech Stack:** Python3.13/FastMCP, existing quotas5CPU/6wall/512MiB,2active16queued, original4SQLite.
**Spec:** docs/LivingMath_Formal_Bridge_v1_20261107/livingmath_formal_bridge_v1/docs/TZ_CODE_AGENT_RU.md and PROMPT_CODE_AGENT_RU.md.

## Global constraints

- Preserve original Symbolic V1/role006/numeric75/SUTI/frozen kernels and prior ledger/events; version new formats formal-grammar-ir/1,formal-candidate/1,formal-contrast/1.
- Generate finite catalog of primitive sequence/alternative constructions and data-bound terminal pair relations, base/start choices; canonical complexity ordering, explicit untried/bounds/counterexamples. Never all-CFG/unique/universal claims.
- Parser: least fixed-point chart plus packed alternatives over nonterminal intervals. Independent checker repeats fixed point using separate traversal, exact source UTF8 spans, complete negative cover. Cyclic/incomplete forest yields UNKNOWN_CYCLE/UNKNOWN_BOUND.
- DFA: bounded canonical transition tables, BFS state-renaming canonicalization, exhaustive accepting-set enumeration filtered by train. No parity builtin.
- Fit never sees query labels; seal before query. Contrast returns query/vector without correct label; external annotation requires new dataset/run.
- Human/imported FOL proposals are explicitly PROPOSED; separate type_status and finite-model checks, closed finite models only; no automatic Russian NLP claim.

## Tasks and checks

- [x] Preserve/hash archive/manifest; inspect real0.4.8 API/code and backup4SQLite/workspaces.
- [x] Baseline409source+1066legacy, supplied225reference, five exact originalrun replay; freeze originaldataset shapes before modification.
- [x] Add tests/test_formal_bridge.py negative-first cases: independent start EPS, two branch types, ambiguous aaa, cyclic forest, forged source/rule/span/order, DFA trace, FOL typing and models.
- [x] Create formal_bridge/ir.py (validate_grammar,validate_dfa,source), chart.py (parse with full forest), proof_checker.py (verify independent chart/trace), search.py (finite grammar catalog/train fitting), dfa.py (canonical search), fol.py (typecheck/evaluate/model contrast).
- [x] Add engine.py (dispatch/fit/predict/contrast/interpret), contracts.py (closed bounded API), service.py (same-project owned refs, idempotent append-only runs), mcp.py (register existing server additive tools).
- [x] Modify symbolic_complex/app.py binding/dispatch only; register additive tools in symbolic_complex/mcp.py. Update release loader hash modules to include new folder only when present, preserving all archived binding calculations.
- [x] Fit sealed previous cases and new positive-enriched/hard-negative queries; compare role/auto/formal without seed cherry-picking. Required anbn epsilon, multi-pair, palindrome, DFA, both contrast witnesses; marked reverse/abplus/canary controls.
- [x] Demonstrate3manual proposed FOL readings under one source,2models/truth vectors, allpair countermodels and forged-type rejection. Preserve parser ambiguity2trees.
- [x] Full source/installed/legacy tests and independent adversarial review; build0.4.9 package, native prepare originalSHA, stage actual SDK/OAuth acceptance including prior suites.
- [x] Quiescent backup, production HTTP-only update sameURL/tunnel, repeat actual HTTPS/OAuth acceptance and data/hashes integrity.
- [ ] Publish source/tag/repro ZIP and required report matrices, full failed/success traces, docs and source/asset public readback. Check CI honestly; preserve userWIP.

## Implementation interfaces

`ir.grammar(value)->dict`, `chart.parse(grammar,record,bounds)->certificate`, `proof_checker.verify(grammar_or_dfa,record,bounds,proof)->status+decision`.
`search.fit(records,constraints,budget)->model` and `dfa.fit(records,bounds,budget)->model` keep complete considered/rival ASTs, seal hash before predict.
`engine.dispatch(packet)->dict` accepts fixed action name only and validates payload before compute.
`FormalService.operation(project,request_key,operation,payload)` reserves/finishes immutable journal, resolves only actual same-project issued refs; inspect pages bounded outputs.
`formal_store(kind=source|model)`, `formal_synthesize`, `formal_inspect`, `formal_verify`, `formal_contrast`, `formal_interpret`, `formal_model_check`, `formal_replay` are additive MCP tools.

## Spec discrepancy

Protocol calls SAPB and ASBP positives for typed pairs S/P,A/B; its own reference grammar rejects both crossing sequences. Preserve them as explicit discrepancy controls and use actual grammar-bound oracle, not silently mutate labels. Correct mixed nested examples SABP and ASPB included alongside both contradictory examples.
