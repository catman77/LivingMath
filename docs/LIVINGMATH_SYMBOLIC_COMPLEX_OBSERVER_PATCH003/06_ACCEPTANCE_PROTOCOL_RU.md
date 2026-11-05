# Матрица приёмки и негативные тесты

Статус этого документа: **ожидаемые условия**, не результаты ещё не реализованной версии. На этапе сдачи агент добавляет actual PASS/FAIL, commands, commit, run IDs и неизменяемые source SHA. Значения с пометкой EXPECTED нельзя переносить в «доказано production» без реального вызова.

## A. Regression baseline (сначала)

| ID | Check | Expected |
|---|---|---|
| REG-001 | old White Star numeric profiles `base_v1`, `cj_v1` и frozen kernel hashes | EXACT SAME |
| REG-002 | legacy `white_star_symbolic_explore/inspect/replay`, stable schema | PASS |
| REG-003 | прежние 20 balanced length-6 words; word/provenance disambiguation | PASS; distinct histories retained |
| REG-004 | literal equality vs alpha vs q vs observer-indistinguishability | four distinct relations |
| REG-005 | deterministic source hash, idempotency request_key, invalid-hash reject | PASS |
| REG-006 | old immutable data-only ZIP bundle replay and cross-project denial | PASS |
| REG-007 | no hidden server LLM calls, source hash/version in checks | 0 calls, PASS |

## B. P0 exact SP-complex

| ID | Check | Expected |
|---|---|---|
| SP2C-001 | N=2: V,E,β,faces,rank | 3,2,0,0,0 |
| SP2C-002 | N=4 | 9,14,6,8,6 |
| SP2C-003 | N=6 | 29,74,46,80,46 |
| SP2C-004 | N=8 | 99,354,256,560,256 |
| SP2C-005 | N=10 | 351,1614,1264,3360,1264 |
| SP2C-006 | in all above: H1(F2), ∂1∂2 | 0,0 |
| SP2C-007 | parallel SP cancellation edges position-aware | distinct edge IDs |
| SP2C-008 | source/destination of every 1-edge, strict length decrease | verified |
| SP2C-009 | source/target and attachments for every 2-cell | verified |
| SP2C-010 | every two outgoing edges have a verified local join | 0 unresolved peaks |
| SP2C-011 | full path coherence proof DAG and independent verifier | CHECKED_INSTANCE |
| SP2C-012 | `cells=none` N=10 | H1=1264, π1 proof not returned; graph π1 free rank1264 |
| SP2C-013 | `cells=bigons_only` / `diamonds_only` | π1=NOT_PROVED |
| SP2C-014 | tampered cell endpoints, bad edge position, removed witness | REJECTED or NOT_PROVED |
| SP2C-015 | no accidental identification `SSPP=SPSP` as literal, both q=0 | PASS |
| SP2C-016 | S↔P meta-isomorphism between complexes | exact incidence preserving map, no claims of ID equality |
| SP2C-017 | `N=11` / N beyond fixture limits | clear INVALID_INPUT/BUDGET not unbounded compute |
| SP2C-018 | repeated run and replay | same result digest/proof digest |
| SP2C-019 | graph with same H1=0 but no SP path certificate | NOT_PROVED, no false π1 claim |

**Trusted-checker boundary:** `SP2C-011` должен использовать production-side independent verifier; тесты reference script alone insufficient. Привести один пример *rejected tampered proof*.

## C. P1 observer synthesis / leakage

| ID | Check | Expected |
|---|---|---|
| SYN-001 | `pair_0_max` and similar existing grammar features | `origin=BUILTIN`, exact binding/dependencies |
| SYN-002 | claiming new feature as `DERIVED_FROM_OPERATORS` without AST+trace | REJECTED |
| SYN-003 | disable feature via allowlist/denylist including all dependent features | реально исключён; trace shows no use |
| SYN-004 | true composition of primitive ops with valid trace | `DERIVED_FROM_OPERATORS`, verified |
| SYN-005 | train and heldout label storage separated | PASS, no prediction read of labels |
| SYN-006 | Dyck 28 train, 70 words length8 and 252 length10, exact labels external | publish confusion, no LLM claims |
| SYN-007 | Dyck single literal/alpha/adjacency observer ablations | full per-feature report, no hidden fallback |
| SYN-008 | `SSPP`/`SPSP` source routes, equal q distinct histories | PASS |
| SYN-009 | two train-compatible but globally different grammars | UNDERDETERMINED + competing candidates |
| SYN-010 | out-of-training context request without known labels | UNKNOWN, not false |
| SYN-011 | change test labels while frozen hypothesis fixed | no change in rule hash |
| SYN-012 | adversarial candidate with same α but contradictory labels | CONTRADICTORY_TRAINING |

## D. P2 Nostradamus and controls

| ID | Check | Expected |
|---|---|---|
| NOS-001 | original corpus source IDs and verse edition manifests | 942 main quatrains, explicit anomalies & missing VII |
| NOS-002 | distinct `century/quatrain/line/word` spans and parent IDs | PASS |
| NOS-003 | original vs swap line2/3, independent per-variant rename | PASS |
| NOS-004 | α-equivalent pairs with opposite labels (e.g. II.5, VII.2) | flagged nonidentifiable; NEVER silently relabel |
| NOS-005 | train I–VIII and sealed holdout IX–X | PASS |
| NOS-006 | identical splits for punctuation/length/majority/derived | PASS |
| NOS-007 | pairwise wins/losses/ties and abstention counts | exact integer counts |
| NOS-008 | original label leakage through shared alpha token IDs | FAIL fast |
| NOS-009 | literature interpretation only AFTER frozen rule + heldout | INTERPRETATION, not proof |
| NOS-010 | corpus not solvable within budget | partial + BUDGET_EXCEEDED without invented output |

**Не требовать точности выше 50% без оснований.** Если честный результат соответствует baseline, научная проверка **PASSED** (измерение корректно), но гипотеза о переносе **NOT SUPPORTED**. Релизный критерий — корректное различение этих статусов.

## E. эксплуатационные проверки

- `max_nodes`, `max_total_tokens`, wall/CPU/memory соблюдаются; consistent `MAX_*` with complete diagnostics and not `global_exhaustion_proved=true`.
- Большие result/evaluation arrays уходят в проверяемые artifact chunks, при этом summary inline не требует загрузки десятков MB.
- Cross-project reads denied. SHA-invalid source/cell/proof/manifest denied. ZIP replay data-only, no code execution.
- Same source, seed, version, operator binding ⇒ identical stable results. Different timings can vary.
- Raw source and edition not modified across normalization. Utf8 byte offsets preserved; invalid byte split rejected.
- Два независимых operators не теряют provenance при одинаковом конечном слове.

## F. независимый локальный эталон

```
python3 tests/test_reference.py
python3 reference/sp_complex_reference.py --max-len 10
python3 reference/sp_complex_reference.py --max-len 10 --face-policy none
```

Ожидается 6 unittest PASS и таблица SP2C-001..005. **Это локальный oracle; агенту нужно добавить свои integration tests с настоящими endpoints.**
