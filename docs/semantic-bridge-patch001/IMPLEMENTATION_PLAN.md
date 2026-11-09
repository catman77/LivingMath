# Semantic Bridge PATCH001 Implementation Plan

**Goal:** Add the four specified contextual FOL tools without changing the98 existing contracts or mathematical kernels.
**Architecture:** Use `semantic_bridge/contextual/` because the parent package already implements the nine legacy Semantic Bridge tools. Reuse FormalService ownership, Workspace/CAS, shared symbolic admission and the existing isolated bounded supervisor. Keep every original hypothesis, source, assumption and obligation distinct.
**Spec:** `docs/SEMANTIC_BRIDGE_PATCH001_20261109/TZ_RU.md` and its immutable reference package.
**Tech:** Python3.13, current MCP SDK, existing FOL evaluator and JSON Schema. No new dependencies or provider calls.

## Global constraints

- Existing98 tools and all original semantic/FOL/NL/UDAV/numeric files remain byte-identical.
- Add only4 methods; optional bootstrap hook and version bump to0.4.13.dev0.
-5 CPU sec/6 wall sec/512MiB; shared2 active/16 queued; bounded pairs, atoms, models and total steps.
- Formal proof, finite evaluation, contextual applicability and source meaning have separate statuses.
- Preserve unsupported future, open obligations, immutable receipts and all existing data.

## Tasks

- [x] Capture actual public98 schemas/status, immutable kernel SHA and full backup/rollback. Establish485-test baseline.
- [x] Implement contracts/alpha/checker/relations in the isolated additive package. Check alpha via lexical binders; prove only identical forall-prefix boolean tautologies with <=10 positional atoms and an independent certificate verifier. Return UNKNOWN for unsupported classes.
- [x] Implement directional countermodel search through unchanged fol.countermodels, validate both formulas and all assumptions through fol.evaluate; retain both directions. Keep explicit model scenarios and OPEN obligations separate.
- [x] Implement immutable register/analyze, strict project issuance checks, exact source spans/AST paths, key conflicts, paged inspect and actual recomputation replay. Source/key attacks must not append history.
- [x] Add separate worker/executor using unchanged supervisor and shared symbolic quota; register exactly4 new tools and opt-in capability. Preserve legacy semantic package files.
- [x] Run source/installed-wheel and negative tests, unchanged supplied independent verifier, frozen SB-EXP01 vectors, certificate tampering and bounds. Preserve failed attempts.
- [x] Run actual MCP staging canary then backup/cutover preserving URL/noauth. Run same public HTTPS acceptance and data/hash-prefix integrity.
- [ ] Publish full reproducible ZIP with schemas, traces, tests, hashes, reports/rollback and real release commit. Push code and release to GitHub, anonymously verify download and preserve87 user changes on root sync.

## Финальное уточнение0.4.14

- [x] Три реально неуспешные регрессии воспроизвели зависимость applicability от типа формулы.
- [x] Разделить formula/assumption evaluations;29 targeted/514 installed tests и68 actual MCP checks.
- [ ] Опубликовать исправленную0.4.14 поставку, сохранить0.4.13 архив и подтвердить публичный download.
