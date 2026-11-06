# PATCH005: исправление mixed-length generator

Установлен **v0.4.7-developer-preview**, deployment `generator005-20261106T113245Z`.
Адрес сохранён: https://fares-september-rebel-board.trycloudflare.com/mcp. Через публичный HTTPS/OAuth MCP:
**916 PATCH005 + 943 регрессионных проверок PASS**;
все прежние31 A/B gate PASS. Новый suite содержит **600 настоящих tools/call**,
34 свежих inference runs с seed137/42. Staged/public models, scores и result_digest
совпадают. Полные трассы и frozen inputs входят в delivery ZIP.

## Доказанный root cause и минимальное исправление

`symbolic/grammar.py:relational_candidates` вычислял `min(available)` по половинам
длин положительных слов. При добавлении положительного SS/PP это давало1,
удаляло offset1; `len(guards)>=2` затем не предлагал рекурсию вовсе. При SP/PS
с false короткая запись не входила в positives, и AST оставался доступен.
Исходный native evaluator/checker корректно обрабатывал epsilon/singleton:
ошибка была в generation, не в базовой семантике.

Новый **opt-in** `compositional.py:typed_skeletons` независимо предлагает typed
comparison и его строго убывающую closure для наблюдаемых координат, затем
ограниченные AND refinements и прежние whole-fragment comparisons. Type/termination,
scope, весь train всех длин и promotion — отдельные стадии. Это конечный catalog,
не полный перебор программ. Численный kernel, SP, общий исторический Symbolic V1
и evaluator/checker побайтно сохранены. Старый literal route не меняется.

На старом сервере воспроизведены B:14/2, B+SS:7/0, B+PP:7/0, B+SP:10/2.
Десять существующих предоставленных runs пересчитаны0.4.6 с точным result_digest.
Указанный в архиве B+PS ID сервер вернул NOT_FOUND; manifest не изменялся.
Новый B+PS причинный контроль на0.4.6 дал10/2. Свежая baseline серия:61 checks
PASS,40 MCP calls. [Точная таблица старых/новых runs](OLD_NEW_COMPARISON.json).

После исправления рекурсивный AST с прежним digest
`b5c20366e2902983352e88b017f458f7244c16145cde7d502ace9757b5c4170f`
появляется и проходит independent checking на B+SS/PP и смешанных train.
Он уже был готовым constructor на B; это исправление полноты ограниченного
поиска, не новая фундаментальная операция/DSL или доказательство уникальности.
Дополнительные equality/inequality closures сохраняются как candidates с
реальными контрпримерами. Feature identity прежняя: AST+scope+operator bindings.

## Конечные результаты

| Train | Queries | TP | TN | FP | FN | BA |
|---|---:|---:|---:|---:|---:|---:|
| B_SS-s137-n6 | 64 | 8 | 56 | 0 | 0 | 100% |
| B_PP-s137-n8 | 256 | 16 | 240 | 0 | 0 | 100% |
| even24-s137-n6 | 64 | 8 | 56 | 0 | 0 | 100% |
| even24-s137-n8 | 256 | 16 | 240 | 0 | 0 | 100% |
| mix1234-s137-n7 | 128 | 16 | 112 | 0 | 0 | 100% |
| odd135-s137-n7 | 128 | 16 | 112 | 0 | 0 | 100% |
| even246-s137-n8 | 256 | 16 | 240 | 0 | 0 | 100% |
| mix126-s137-n8 | 256 | 16 | 240 | 0 | 0 | 100% |
| copy20-s137-n8 | 256 | 16 | 240 | 0 | 0 | 100% |
| copy52-s137-n8 | 256 | 16 | 240 | 0 | 0 | 100% |
| odd13-s137-n7 | 128 | 16 | 64 | 48 | 0 | 79% |

Для всех обязательных положительных случаев FP=FN=UNKNOWN=0, coverage100%.
Полный B/B+SS/PP/SP/PS, COPY20/52, все lengths и оба seed — [SCORES.json](SCORES.json).
Always-negative на n8:240/256=93.75% accuracy, balanced accuracy50%.

Odd1/3 train не идентифицирует продолжение: минимальная endpoint-only модель
сохраняет48FP на n7, а рекурсивный rival теперь **также удерживается**. Этот
контроль не объявляется успешным переносом. На более информативных30/42 train
выбран рекурсивный AST и FP=FN=0. COPY52 n6 содержит32 уже обученных слова:
его64 оценки не выдаются за64 новых holdout. Полностью новый n8 —256/256.

Проверенный mixed30 run `35438fbe59b77f8c9f5e0516b59a495ca3a74d1e4d77d43f37a15e09dd12d27d`,
feature `derived_ee42a6c799ce3ba3a777`, проект `qa-generator005-prod`.
Подключённый LivingMath plugin подтвердил CHECKED_INSTANCE/30 witnesses.
Сырой source-bound proof — [VALID_FEATURES.json](VALID_FEATURES.json).

## Стадии, защита и воспроизводимость

`candidate_generation` содержит grammar_version, histogram, counts by AST kind,
digests, sample_id/expected/observed и отдельные статусы. NOT_GENERATED,
type/termination/train rejection, compatible/not-promoted и PROMOTED_VERIFIED
различаются. Последнее означает finite checker admission, не mathematical verified.
На max_proposals1: BOUNDED_SEARCH_INCOMPLETE, а не no grammar; runtime1ms:
прежний BUDGET_EXCEEDED/FAILED, без prediction. Вне8 tokens — UNKNOWN/score=null.
Full model/details читаются existing pages/artifact chunks; summary не раздувается.

Независимый checker отклоняет rehashed hash/SPLIT/span/missing-witness/operator/
origin/universal/hidden-label/type подмены. Чужие refs, mismatch источника и
holdout labels отвергаются. Повторный ключ возвращает прежний run, свежий
одинаковый payload — новый run с тем же result_digest. Реальные source binding,
исторический Symbolic/observer replay, numeric base/cj и SP4/SP10/partial negatives
прошли регрессию. Без сети mixed30/COPY52: REPLAY_MATCH, journal PASS.

**385 source PASS,385 installed-wheel PASS**,1066 legacy PASS/20 прежних SKIP,
17 independent reference PASS; независимый review:48 targeted PASS/NO FINDINGS.
Исходные RED/первые failed harness logs сохранены; защиты не ослаблялись.

## Сохранность и границы

Два backup:4 SQLite+все workspaces до правок и при quiescent cutover.
Сохранены 38297 initial/38451 cutover files,
все исходные исследовательские строки/объекты/hash-chain prefixes;4/4 SQLite ok,
45 journals PASS, canonical audit неизменён,29 исходных run records совпадают.
Базы/пути/inodes и tunnel PID прежние; перезапущен только HTTP. Квоты/операторские
границы не менялись; все72 QA runs завершились, grants не создавались.

Family UNDERDETERMINED; никакого universal grammar, semantic transfer, physical
interpretation или mathematical verified. Native SUTI NOT_EXECUTED, R3 PENDING.
Dyck/корпус не входят в PATCH005; [отдельный следующий план](../../superpowers/plans/2026-11-06-generator005-next-research.md) приложен.

Runtime source commit `9f0ef23cd4e1ea1415faf8be69b390f021a28db2`; QA commit `c5ca1c8ae0a2cff0015872c46758485311a33087`.
Wheel SHA256 `e017c5bdd572683502d3ae03382c0cd22571d7852186c84143c47e88bb4681ab`.
Binding `5b5ec1450f1fdd4c03da4fa126252f2ed3b5ce046f1e54f568ff67ffa91d8cca`.
GitHub CI оценивается отдельно: account billing lock может не допустить запуск
jobs; локальные PASS не обозначаются зелёным GitHub Actions.
