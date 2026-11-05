# PATCH001_IMPLEMENTATION_RU

## Результат

Установлено **v0.4.1-developer-preview**, deployment `symbolic-patch001-20261105T070936Z`. Адрес прежний: `https://fares-september-rebel-board.trycloudflare.com/mcp`.75 инструментов;74 прежних schemas полностью совпадают, symbolic_inspect расширен только optional compare_run_id и views comparison/diagnostics. Explore/replay request schemas прежние.

Архив сохранён без изменений в [docs](../../LIVINGMATH_SYMBOLIC_V1_ACCEPTANCE_PATCH001_20261105.zip), SHA256 `64b08e60cae9e5592b75b7a7da2eff88a48ffb406a6a47e8d0b538405dc534f2`. Все7 исходных файлов распакованы рядом. [План](../../superpowers/plans/2026-11-05-symbolic-acceptance-patch001.md).

## Код и механизм

Расширены существующие symbolic/grammar.py, kernel.py, search.py, service.py, mcp.py, executor.py и bundle.py; новых runtime engines/modules нет. SOURCE/word operations/state.py, numerical White Star,75 supplied files и frozen verifier/binder не изменены.

Гипотезы теперь включают bounded композиции наблюдаемых равенств на SPLIT/REVERSE-фрагментах, конкретные train witnesses/контрпримеры и max_rules. Candidate generation использует максимум4 наблюдаемых выравнивания и их композиции; active probes — максимум64 train-derived mutations. Нет перечисления CFG/всех слов, LLM re-ranking или пользовательского DSL. Witness indices ссылаются на frozen train_samples и sample digest, а не ошибочно на исходный несортированный массив.

Объект grammar публикует relational_rule_ast, rule_witnesses, scope, counterexample_candidates, hypothesis_complexity, candidate_status и identifiability_status. Старое дерево сохранено как свидетельство/совместимый baseline. Вероятность — Laplace score выбранного empirical кандидата; family-disagreement помечается INCONCLUSIVE. Последовательность train→freeze→predict проверена разными predict-масками.

NO_NOVEL_CANDIDATES имеет finite certificate текущего word/node, tested variants, причин отказа, clock-cycle/window и unproposed operators. Новые provenance-paths не сворачиваются в режиме provenance. Префикс реального старого trace до остановки совпадает побайтно: policy Удава не подменялась ради теста.

Новая comparison-view сопоставляет actual initial words, α-pattern с declared scope, SP normal forms, history DAG, op_trace и finite observer signatures. Предъявляет source byte spans первой разницы, реальные declared components/CONCAT refs и полные SP reduction routes. Она не выводит равенство из совпадения summary. Ненулевой q при SP_INV меняет знак; равенство нулю — отдельное свойство. Cross-project run IDs отклоняются.

Исторические bundles с binding404d... автоматически передаются **уже установленному immutable v0.4.0 worker**, чей полный manifest проверяется до старта. Код не копировался/переписывался и из ZIP не исполняется. Неизвестный binding даёт явный отказ, не fallback. Текущий и historical profiles разделяют исходную квоту2 active/16 queued; CPU5с, wall6с,512MiB/job и остальные quotas прежние.

## Фактическая приёмка

| Gate | Итог |
|---|---|
|Обязательный baseline до code edits |252 PASS|
|Полный pytest после исправлений |261 PASS|
|Установленный wheel, вне checkout |261 PASS|
|Legacy suite |1066 PASS,20 SKIP|
|Staging v0.4.1, реальный OAuth/MCP |129 PASS|
|Действующий HTTPS/OAuth MCP |129 PASS|
|Fixed unique holdout |selected9/9, family5 consensus/4 inconclusive|
|Дополнительный OOD holdout |1200/1200 selected-candidate correct|
|New + historical offline replay в unshare -Urn |REPLAY_MATCH|
|Actual historical v0.4.0 digest |f17aa98dd5695692c9efd31b46256d4ef1ec44025f12cad2b742db47b15cb62f|
|17 supplied historical summaries |точно совпадают с baseline copy|

[Полная AC01–AC16 матрица](ACCEPTANCE_MATRIX.json). AC14 — PASS_WITH_UNDERDETERMINED_FAMILY, AC11 — STRUCTURAL_ONLY, AC16 — scoped bounded/security gates, **не** полный независимый pentest или длительная нагрузочная сертификация. Hosted CI: NOT_RUN. Все команды, запросы и исходные неуспешные попытки включены в delivery; никаких FAIL не скрыто заменой исходного лога.

[Исследовательские результаты и границы](BENCHMARK_REPORT_RU.md). Выражаемость рекурсивной гипотезы и выбранный finite classifier подтверждены; уникальность языка и литературное понимание — нет. `verified` не присваивается; R3 внешних участников остаётся PENDING.

## Проверенные операции через MCP

Проект `qa-patch001-prod`. Базовый run `2b3b790e7cf523296d01af4c7128df8d4af89520ba2f2227c2a8a75ee8463afd`, structural digest `4f4a4e48e7f1adcca240934bbbb5d9b8e4efc423e6504452f10ac0487f5bf6d6`, kernel binding `ea8df7eaa0f9e32e78cc86e7907606d7d9b7b5f857a8ca5fa73733062fd716fa`.

```json
{"project":"qa-patch001-prod","run_id":"d4ce400041b05bb28b44a3633aa8aa0536df041d4dbc8163f7c882fd066fb1f8","view":"comparison","compare_run_id":"38a474a46482414423423aade0adec34e1729c5211ee7819dd0e26c962002a15"}
```

Передать в white_star_symbolic_inspect. Для диагностики: run_id=`b8ef4c89f7197227755b616e4a108b29c6421cba16f0d2ae82b62d36ed721fd9`, view=diagnostics. Grammar/predictions: run_id=`435451dad06e4f653946779b89b9c4c916e8fb1616c433fd7a8acadcca0cad9b`, view=grammar/evaluation. Статусы кандидата и семейства читать раздельно. Если клиент кеширует старую schema инспектора, обновить подключение LivingMath; адрес и OAuth настройки не менялись.

## Сохранность production

Сделаны online и отдельный quiescent backup4 SQLite и файловых workspace до переключения. Все прежние research/typed/DAV строки сохранены, inode/пути4 БД прежние;1604 старых файла неизменны,18 append-only journals/hash-chains валидны. Canonical audit4817 entries/head c9c0048b... без изменений.17 historical snapshots и прежняя White Star history читаются, оба replay profiles пересчитываются; исторические модели не переписываются лучшим новым прогнозом. OAuth меняет только штатные сессии входа владельца.

Перезапущен только HTTP; tunnel PID1801300 и URL сохранены. Активных/незавершённых QA runs нет. Profile-level rollback реально проверен old worker + network namespace с исходным digest; конфигурационный rollback всего сервиса подготовлен возвратом прежнего drop-in и restart HTTP, **без** восстановления БД поверх новых записей. Полный отдельный обратный production cutover не выполнялся.

## Команды и файлы

```bash
python docs/LIVINGMATH_SYMBOLIC_V1_ACCEPTANCE_PATCH001/checks/heldout_palindrome.py
python -m pytest -q tests
(cd live_math_mcp_prod && python -m pytest -q .)
python tools/symbolic_patch001_benchmark.py --output /tmp/patch001-new --old-model replay/old-grammar.json --mallarme replay/mallarme-historical-request.json
```

Live acceptance: tools/symbolic_patch001_mcp_qa.py с --origin/--endpoint/--baseline/--output/--tag, для staging --loopback-port. Он пишет OAuth credentials отдельно и создаёт только QA-проекты.

[REGRESSION_RESULTS.json](REGRESSION_RESULTS.json), [CHANGED_FILES.md](CHANGED_FILES.md), [release_manifest.json](release_manifest.json), [INTEGRITY.json](INTEGRITY.json), [RCA_RU.md](RCA_RU.md). Поставка: `exports/LIVINGMATH_SYMBOLIC_V1_PATCH001_DELIVERY_20261105.zip`, без паролей/токенов/SQLite. Исходный approved v0.4.0 слой и оба owner-private backup сохранены вне Git.
