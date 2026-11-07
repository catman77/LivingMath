# LM–NL–CAUSAL–003: итоговый отчёт

Установлен **v0.4.11-developer-preview**; engineering acceptance PASS.
Deployment `nl003-20261107T201856Z`;94 MCP tools, все93 прежних tools/list записи
сохранены целиком. Архив ТЗ сохранён без изменений в docs.

**Смысловая польза White Star не подтверждена.** Исправлен экспериментальный
контракт: все4 arm теперь декодируют один реальный frozen provider receipt.
Внутри redecode/replay —0 model calls и0 network calls; source bytes, reverse-map,
signature, binders/token links, provider request/raw output и base AST одинаковы.
Вся семантика остаётся PROPOSED/HUMAN_NOT_EVALUATED, execution_permission=false.

## Что показал эксперимент

| Выборка | Результат | Граница вывода |
|---|---|---|
| U21–U25, открытый контроль |5/5 wide SHA совпали с реальным историческим B; каждый выведен одним primitive swap |176 различий на530 моделях; усиление формулы не удостоверяет чтение текста |
| U26 |EXCLUDED_INVALID_ORACLE |Ошибочный исходный эталон сохранён и исключён из score |
| Новые12 источников |9 без incremental structural expressivity,2 NO_BASE_PROPOSALS,1 вне closure depth2 |ASSISTANT_AUTHORED_ORACLE; human licensing не проводилось |
| Единственный выход за closure, H05 |Конструктивно воспроизведён3 соседними swap |Это отдельная post-hoc диагностика вне preregistered depth2; не улучшенный результат arm |
| Отрицательные H07/H08 |Перестановка даёт другой AST, SAME_ON_BOUND |Структурное отличие и отличие истинности считаются отдельно |

В H05 минимальная цена3 подтверждена: reversal[2,1,0] имеет3 инверсии; один
соседний swap меняет их число на1, alpha-renaming не переставляет binders.
Новый кандидат INCOMPARABLE_ON_BOUND и имеет два направленных контрпримера.
Это не новое фундаментальное преобразование и не доказательство текстовой допустимости.
Модальные/невыразимые случаи H04/H12 сохранили NO_BASE_PROPOSALS; подписи без
модальности не превращались в её поддельную реализацию. H03 достиг relation-cell
bound: UNKNOWN_BOUND, а не универсальная эквивалентность.

## Заморозка и модель

Старые A/B/C прочитаны через реальный HTTPS/OAuth MCP. C `076ccc229e6c661dae47459449ffc28f5e499f90c68ffe03bb10cc77a7f2ef46`
существовал в production и COMPLETED; его SHA/replay проверены без нового LLM.
Исторический matched_ablation менял prompt и decoder; он сохранён только как история.

Новые12 оригинальных текстов и рубрика зафиксированы до генерации:
corpus SHA `7ef25b599ec08cf6c295b3492dbcd0d57de306f4d0ea909b3fb89bfa498191c3`,
oracle SHA `a5172682f52bb10684dd75f041bee236396a50874480de2caeaffd5b41494695`.
Рубрика не содержит независимых человеческих gold readings. Выполнено **2 свежих
вызова gpt-6.1-sol** через owner-authenticated ChatGPT-login CLI и реальный staging MCP,
по6 текстов; generator видел только source/signature, не rubric/gold/White Star.
Provider revision/seed/temperature не контролируются CLI. Receipt содержит реальные
model_id, request, raw output, prompt, schema, events и usage; это SHA-bound receipt,
а не криптографическая подпись провайдера. API-ключи не использовались.
Эти2 сохранённых receipts перенесены в отдельном QA-проекте и прочитаны новым
production MCP; новые model calls на production для их redecode не выполнялись.

Общие границы:8 candidates/source,32 AST nodes,4000 ms CPU на весь decoder,
8 слотов попыток/arm, primitive depth2, seed2211. Измерено реальное CPU каждого arm
по thread_time; слоты без операции явно NOOP. По умолчанию uniform nonempty
sort domains1,2; для открытого контроля1,2,3. Полные помодельные счётчики,
контрмодели и расходы находятся в JSON, не интерпретируются как human semantics.

## Приёмка и сохранность

- 464/464 source tests и464/464 tests установленного wheel;17 focused tests.
- Реальный production HTTPS/OAuth MCP:60/60 новых проверок;93 старых схемы точны.
- Полная формальная регрессия:869 проверок,667 реальных MCP-вызовов; отдельно
  перепроверены1024/1024 строк Dyck2, palindrome, parity DFA, anbn.
- 12/12 старых owned runs заново replay через production, REPLAY_MATCH.
- C и новые frozen bundles: REPLAY_MATCH без LLM/сети; подмена ключа/AST/source,
  чужой проект, fake node/snapshot и ввод raw_output отклонены.
- Четыре реальные SQLite сохранены, inode/path не сменились, integrity_check=ok;
  исходные non-OAuth rows сохранены. OAuth expiry отмечен отдельно.
- Все прежние workspace bytes и append-only journal prefixes сохранены;
  все journal hash chains проверены. Старые COMPLETED/результаты не переписывались.
- Численные/символьные/Formal Bridge kernels и8 старых NL modules byte-identical.
  Все17 использованных structural runs дополнительно пересчитаны оригинальным
  kernel offline: полное совпадение result SHA.

Исходные ошибки и повторные проверки находятся в delivery ZIP. Смысловые внешние
ворота остаются NOT_EXECUTED; наличие инженерного PASS не делает их зелёными.

## Production и воспроизведение

Действующий endpoint: `https://difficulty-nightlife-rca-missions.trycloudflare.com/mcp`. Старый временный Cloudflare origin был удалён
на стороне tunnel и не резолвился ещё до изменения кода. После полного backup
создан новый tunnel; дальнейший release перезапускал только HTTP, новый URL сохранён.
Для ChatGPT необходимо переподключить LivingMath к этому URL и обновить список tools.

- open: `9affcb8dc71e99df09776b57cd748c9806043be5f0248e17685382882e43f40f` (`nl_independent_eval_20261107`)
- hidden: `17e1baa1aae91fac343eefa82acb1644cc58f7f9f7bb41ea705c567b7954242d` (`qa-nl003-holdout`)
- hidden: `f4e31007063f4071a9881a75f7ccb7c4962008a58576df5f1229de1aeab57164` (`qa-nl003-holdout`)

[Точный запрос, inspect, offline replay и rollback](QUICKSTART_RU.md).
[Машинная матрица доказательств](TEST_MATRIX.json), [RCA](RCA_RU.md),
[таблица новых результатов](HIDDEN_RESULTS_TABLE.csv), [контроли](OPEN_TABLE.json).
