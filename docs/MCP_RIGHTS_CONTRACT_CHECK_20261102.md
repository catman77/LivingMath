# Проверка входного контракта и экспорта MCP — 2026-11-02

## Результат

Точный [запрос с фрагментом «Эха»](examples/research_autonomy_ingest.observer012-public-domain.json)
принят через действующий подключённый MCP-клиент. Сервер:
`1.2.0rc3-observer012`, deployment `20261101T044526Z-observer012`.

- Project: `BRIDGE_QA_RIGHTS_CONTRACT_20261102`.
- Input: `4574`; case: `4575`; source snapshot: `4573`, version `1`.
- Source SHA-256: `b6329395d8b469ff33a5710faf8d28f27b591cd1ca3d41cede550dee19e0c24b`.
- Итог: `COMPLETED / PARTIAL_MODEL`, stop reason `MODEL_BUDGET_EXHAUSTED`.
- Проверены четыре конечных варианта: result IDs `4592, 4599, 4606, 4613`.
- `full_formalization=false`, `source_verified=false`, execution grant отсутствует.

## RCA и изменение

Схема Rights в репозитории структурно совпадает со схемой установленного
кода. Допустимы только `basis` (`USER_SESSION` или `PUBLIC_DOMAIN`), обязательный
строковый `origin` и необязательный строковый `attribution`.
PUBLIC_DOMAIN принят действующим endpoint без изменения проверок.

Обнаружено рассогласование документации и установки: основной пример
`docs/USAGE.md` предлагал `meaning014`, тогда как установленный ArtifactInput
принимает только `general011` и `observer012`. Также готовый старый пример
PUBLIC_DOMAIN находился на диске, но исключался из Git и не был связан с инструкцией.
Добавлен точный реально выполненный observer012-запрос, указан полный контракт
Rights и разобраны частые причины общей клиентской ошибки `source is not valid
under any of the given schemas`. Пример Meaning014 явно отделён от работающей версии.

Исходный JSON прежнего отказа не представлен, поэтому конкретное неверное поле
того запроса не установлено. Принятие исправного запроса не доказывает, что прежний
отказ был вызван исключительно rights. Новые права, SDT-операторы или DSL не добавлены.

## Проверки

| Проверка | Результат |
|---|---|
| Точный пример через реальный MCP | PASS: ACCEPTED_FOR_AUTOMATIC_PROCESSING |
| Повтор request key | PASS: те же input/case/snapshot IDs |
| Опубликованная Rights schema против установленного кода | PASS: точное структурное совпадение |
| Неверный регистр basis | PASS: отказ с полем rights.basis |
| Отсутствующий origin | PASS: отказ с полем rights.origin |
| Лишнее поле license | PASS: отказ с полем rights.license |
| Отсутствующий edition для raw_text | PASS: RAW_SOURCE_METADATA_AND_RIGHTS_REQUIRED |
| Meaning014 на установленном observer012 | PASS: установленный валидатор отклоняет неподдерживаемый режим |
| Полный export через MCP | PASS: 12 страниц, 43 записи, more=false |
| Хеши экспортированных записей | PASS: 43/43; непрерывный сегмент previous_hash сохранён |
| service_health | PASS: sqlite_integrity=ok; audit.ok=true |

Отрицательные проверки выполнены установленным Pydantic-контрактом локально;
положительный приём, повтор и весь экспорт — через реальный MCP.
Код не менялся, поэтому новый unit-suite не запускался.

## Что реально экспортировано

Observation checkpoint `4583`: 1 reading, 4 states,
3 relations и 6 unknowns.
Сохранены исходные source refs, координаты, proposer/critic, alignment и потери.
Конечные модели содержат reaction_network, guards, initial_states, assumptions,
premises, source_context, binding и check.analysis. Тип observer здесь SIGNED_RESPONSE;
наличие универсального поля source_graph у каждой модели не предполагается.

Покрыты строки 1–5 фрагмента. Строка 6 («И ты, поэт!») сохранена как
unsupported/unparsed, а 4 из 7 запланированных ветвей проверены. Исходный смысл
целиком не объявлен формализованным. В документации описана сборка fragments и
различие исходных отношений и переходов конечной модели.

Артефакты локальной проверки:
`/home/catman/.local/state/livingmath/rights-contract/20261102T025730Z/`:
`source_export.json`, `mcp-transcript.json`, `integrity.json`, `final-checks.json`.
Хеш source_export.json:
`3716ca9425f1736dd185357c07f80d655f6dd17d4da70e1abf04c5fc4344ced2`.

При первой сборке клиент округлил created_ns через JavaScript Number.
Эта повреждённая клиентская копия сохранена отдельно; итоговый экспорт заново
собран из исходных json_ascii с точными Python integer и прошёл Store.decode.
Это исправление сборки артефакта, исходные серверные записи не менялись.

## Развёртывание

Изменены только документация и опубликованный пример. Перезапуск сервера и
переподключение ChatGPT для этого запроса не требуются. Миграций, изменения
онтологии, ослабления контрактов или изменений RH/Soft FTL не было.
Фоновый Roblox-прогон продолжает использовать прежний неизменный слой.
