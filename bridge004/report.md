# LM–SUTI–Bridge004 — пересмотр по межфайловым источникам

**Научный результат для обеих пар:** `NO_APPLICABLE_CONSTRAINT_FOUND_WITHIN_SEARCH_SCOPE`. Обе пары проходят действительно применимые исходные схемы; дополнительные текстовые основания требуют review. Глобальная независимость полей, runtime и новый математический закон не установлены. **Процессный результат: `PASS_SOURCE_LINKED_REVISION`; G0–G6 PASS.** Это не подтверждение найденного межфайлового ограничения.

## G0 — исходники и предрегистрация

До discovery заморожены два точных fingerprint из Bridge003, исходные JSONL bytes/base64, четыре полные записи, archive/source SHA, критерии, ограничения и статусы. Freeze SHA256 `6dd82702206840682ff835b4f690ac72960ccd52a9b98450466261d1b04e9f15`, время `2026-10-29T02:27:33Z`. Полные хеши — в `source-freeze.json`; receipt фиксирует отсутствие discovery-кода. USER_SESSION разрешает локальную работу с авторскими рабочими файлами; новой подписи или релиза не требовалось.

## G1 — измеренный поиск

Потоковый индекс просмотрел 10361 archive entries в обоих архивах; прочитано 3598 UTF-8 файлов / 27241580 байт. Exact symbol references и затем более широкий поиск по замороженным именам/смысловым эквивалентам дали 1185 кандидатов:390 для P1-001 и 795 для P1-002. Это адресованные references, не 1185 доказанных отношений.

Исключения: {'DIRECTORY': 1117, 'EXCLUDED_PATH': 5400, 'SCANNED_UTF8': 3598, 'EXCLUDED_FORMAT': 245, 'OVERSIZED_FILE': 1}. Один oversized-файл и все исключённые пути перечислены в `source-census.json`; metadata каталога не равна просмотру содержимого. Кандидатные и byte caps не достигнуты. Поиск ограничен UTF-8, разрешёнными форматами, каталогами и контекстными окнами; нет заявления об отсутствии связи во всём корпусе.

Два дополнительных коротких фрагмента в `reviewed-contexts.json` выбраны оператором ПОСЛЕ discovery при чтении полного контекста уже просмотренных README. Они отдельно помечены SOURCE_CONTEXT_REVIEW, не передавались worker и не стали исполнимыми правилами. Общий ledger содержит 1187 кандидатов; классификация источника после результата не менялась.

## G2 — применимость и полные записи

Независимый checker не импортирует discovery и вновь читает реальные архивные байты. Проверены source/archive SHA, char/byte spans, quote hash, revision, observer, тип и dialect. Стандартный Draft202012Validator проверил все 4 полные записи. Исполнимыми для пары считаются исходная schema и реально достигаемые исходящие `$ref`; другая schema с теми же именами или обратным `$ref` не накладывает ограничение назад. В реальных двух схемах дополнительных исходящих связей нет.

| Пара | Исходный свидетель | Полные записи | Расширенный источник |
|---|---|---|---|
| P1-001 | `visibility=public`; `transfer_status=HOLD` / `transferred-by-explicit-choice` | обе valid | NO_APPLICABLE_CONSTRAINT_FOUND_WITHIN_SEARCH_SCOPE; documented review |
| P1-002 | `external_transfer=HOLD`; `decision=COMMIT` / `ROLLBACK` | обе valid | NO_APPLICABLE_CONSTRAINT_FOUND_WITHIN_SEARCH_SCOPE; documented review |

Конкретный пример: `SUTI.uni/SUTI.studium/README.md`, UTF-8 bytes `[24899,25100)`, говорит: «Решение о расширении, закупке, интеграции ПО или передаче данных является отдельным от удачной учебной пробы». Это первичный текст, но он не задаёт исполнимое условие между полями нашей версии. Он сохранён как `DOCUMENTED_RELATION_REQUIRES_REVIEW`, без фиктивного refutation.

Полный `applicability-ledger.jsonl` содержит решение для каждого кандидата; шаблон-пример не считается всеобщим инвариантом, чужие namespace не объединяются, код архива не исполнялся. У непроверенных программных контрактов PROGRAM_CLAIM_UNVERIFIED; версия и lifecycle binding неизвестны. Лексическая близость никогда не означает тождество полей.

## G3 — условный пересмотр

`original003-restored.jsonl` восстанавливает выбранные строки побайтно. `revision-history.jsonl` содержит 4 append-only звена с previous_hash: исходная ревизия 0 и расширенная ревизия 1 для каждой пары. Старый локальный вывод остаётся верным в исходной области; новый вывод ограничивает претензию независимости измеренным контекстом. Старые источники/ledger/FAIL не переписаны. Скалярное LOST и выбранное joint PRESERVED сохранены; авторское намерение и runtime остаются UNKNOWN.

## G4 — контроли

13 pytest PASS: зависимые/независимые synthetic engineering schemas, реально разрешаемый `$ref`, недостающий исходник→UNKNOWN, документация/комментарий/конфликтующие тексты/prompt injection, foreign namespace, hash/revision/authority и append-only история. Synthetic cases отмечены тестовыми и не повышают научный статус SUTI. Ещё26 adversarial controls на реальных кандидатах PASS: source/hash/span/version/observer, false grant/verified, documentation-as-executable, rename, foreign schema и восстановление старого LOST. Конфликтующие документы требуют review; удобный запрет из них не выбирается.

## G5 — реальный MCP

Свежая приватная BackupAPI-копия, отдельные BRIDGE_QA_REVISION004 проекты; исходные schema, found/unknown контекст и обе версии формализации записаны операторским ResearchStore. Через настоящий ClientSession выполнено 10 read-only tool calls: context, frontier, normalize, audit и cross-project negative для каждой пары. Local endpoint публикует 20 инструментов, initialize version0.4.2. Полные requests/responses в `mcp-wire.jsonl`, точные object IDs — в `result.json`.

Нормализация обеих пар COMPLETE; аудит UNPROVEN_SEMANTIC_PRESERVATION / REQUIRES_SEMANTIC_REVIEW; foreign refs INSUFFICIENT_CONTEXT. Проверяется именно ожидаемый успешный structured response. MCP не менял QA state, grants=false, proof_status=unverified. Native adapter отсутствует: NOT_RUN_UNSUPPORTED_SOURCE_ADAPTER; это не native-успех.

Отдельно существующим staging-процессом проверены 27-tool factory:5 baseline checks/2 calls воспроизводят gaps,18 patched checks/14 calls PASS, точный rollback PASS. Неизменные 92 теста зависимости и 86 исторических MCP-инвариантов PASS. Это отдельная compatibility-проверка, не математика Bridge004.

## G6 — переносимый пакет

`reproduce.sh` принимает реальные локальные пути обоих архивов, LM и приватных снимков; архивные SHA проверяются. В ZIP нет полных архивов, production DB или credentials. Код и собственные зависимости захвачены с manifest. Фактический запуск из чистого извлечённого trial ZIP прошёл: PASS_REPRODUCED, 14.218s wall. Все source relations, полные проверки, hash-linked revisions и восстановленные003 bytes совпали побайтно. Receipt — `reproducibility-receipt.json`; окончательный ZIP проверяется отдельно, его SHA и receipt находятся рядом в artifacts/. Исходные FAIL не заменены.

## Стоимость и сохранность

Первый полный научный run: 6.108s wall, discovery 2.661s wall / 2.643s CPU, peak RSS 59876KiB. Worker caps CPU90s/wall120s/AS1GiB не превышены. Стоимости поиска, checker, MCP, regressions и упаковки разделены в costs/receipts; ускорение не заявляется. Внешних контролируемых LLM-вызовов/токенов/API spend0, работа самого Codex не входит в этот ноль; LLM_ADVANTAGE=NOT_ESTABLISHED.

Проверка 700 защищённых файлов и архивов: без drift. Production canonical2057 событий/4815 операций, typed2072/4863, прежние inode/bytes/все строки, integrity=ok. QA добавила 10 событий; все исходные строки и префикс hash-chain сохранены, audit=ok. Production service active,PID1270304,NRestarts0. Ни патчей, ни рестартов production не было.

## Следующий адресный опыт

Два объяснения с четырьмя полными состояниями и ровно одним вопросом на случай — `author-review-package.md`; постоянная карточка 004 в suti_author_proposals. Авторский ответ NO_REVIEW, отправка отсутствует. Следующий опыт — получить точный источник связи для одной из этих версий полей и проверить его применимость к этим записям; новый DSL или предполагаемое runtime-правило не добавлять.
