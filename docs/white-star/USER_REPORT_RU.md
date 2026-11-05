# LevinMAS × White Star — выполненная интеграция

**Production обновлён до `v0.3.0-developer-preview`, deployment `whitestar001-20261105T032516Z`.** Адрес сохранён: https://fares-september-rebel-board.trycloudflare.com/mcp. Опубликованы72 инструмента;64 прежних input schemas не менялись. Проверенный manifest: `a495e5265bca6885fbd7e01891516cb26c3ce75e0ed120f810fdf4ebd8be403d`.

## Реализовано

Перенесены75 файлов предоставленной поставки побайтно, включая6 kernel-файлов. Работает прежний Белая звезда→CAD→Удав без изменения orbit/scheduler/score/tie-breaking/signatures. Профили base_v1 иcj_v1, неортогональные карты и все aliases сохранены; exact reachability остаётся вне горячего пути. Native строится до запросов;2 тёплых supervisor запускают независимые ограниченные процессы с новым native state. Main HTTP не импортирует bare vendor modules и не выполняет численный поиск в event loop.

Добавлены6 запрошенных команд и2 необходимые фасадные: semantic_run_frozen для фактического Bridge ingress иwhite_star_replay. Используются прежние Workspace/immutable objects, append-only hash-chain, строгие schemas, typed errors, whole-record pages и chunks для больших объектов. RUNNING→COMPLETED/FAILED/INTERRUPTED отделён от статуса смысла. Повтор request_key не запускает второй поиск; изменённый payload конфликтует. Отмена клиентского ожидания не бросает принятый run. Реальный staging SIGKILL проверил INTERRUPTED, а completed пережили restart.

## Два режима и два источника

| Источник | Режим | Собственные шаги | CAD projections | Прочтения / пустые слоты | Client LLM sec | Run prefix |
|---|---|---:|---|---|---|---|
| blok | white_star | 64 | 192 | 6 / 0 | 78.04 | `9b8da61005b6…` |
| blok | suti | 14 | — | 6 / 0 | 46.09 | `7bb03ed1d88b…` |
| original | white_star | 32 | 96 | 6 / 0 | 60.45 | `e54da0c0121a…` |
| original | suti | 4 | — | 4 / 2 | 28.48 | `196c272c72ce…` |

192 CAD-проекции не равны14 source-assurance checks. Белая звезда на Блоке совпала с003:64 шага,192 проекции,354 карты,360 подписей,52 качественных режима; base_v1 совпал с001. Новый короткий текст имеет32 шага/96 проекций и только свои4 concept IDs.

Общий levinmas-semantic-input snapshot сохранён до обеих ветвей: точные source bytes/rights, concepts без координат, relations и uncertainties. Обе ветви реально получают одинаковый digest. Отдельная negative разметка с прежним source SHA и изменённым label дала UNMATCHED_INPUT через MCP. Координаты/оси/объяснения — отдельная White Star проекция, не скрытые свойства текста.

Ветка `suti` — фактический **SemanticBridge001/source-assurance-frozen-ingress/1** через существующие SourceSnapshot,Service.source/task/review/candidate/check и исходное assurance-ядро. Она проверяет сохранённые label bytes и предъявляет first-K declared concept frames с полным общим контекстом. Это не native SUTI и не весь legacy DAV/observer pipeline. Интерпретации label/relations и художественная адекватность не становятся SOURCE_ATTESTED; source verdict касается только адресных байтов разметки. Такая граница явно сохранена в receipts/projection, не подменена симуляцией второго движка.

Encoder в этом опыте — предоставленные frozen fixtures (оригинальный короткий текст размечен вручную в архиве); нового extraction не было. Выполнены4 реальных клиентских декодирования одной `gpt-6.1-sol` через существующий Codex ChatGPT login, с одной инструкцией, K6, полным источником и first valid outputs. Сохранены22 прочтения;2 отсутствующих слота Bridge не выдуманы. Сервер White Star модель не вызывает. Requested alias известен, точный provider revision не раскрыт; стоимостьUSD=null. Raw prompts/answers и usage сохранены; только auxiliary CLI warnings с owner path вынесены в приватный оригинал с SHA-ссылкой, без правки модельного текста.

Отдельный пятый вызов — **субъективная LLM-оценка**, не human gate. Метки A/B менялись по фиксированной очередности двух fixtures. Оценщик предпочёл White Star на Блоке и Bridge на коротком тексте; отмечены неподдержанные добавления и потерянные различения у обеих ветвей. Количество кадров/режимов не принято за качество. **Общего превосходства, литературной accuracy, универсальности координат и native SUTI этот опыт не устанавливает.** Полные чтения — READINGS_RU.md, отзыв — model/EVALUATION_LLM.json.

## Проверки и эксплуатация

| Gate | Факт |
|---|---|
| Предоставленные001/002/003 иadapter suites |21+8 PASS; исходные hashes без изменений|
| Текущий код / чисто установленный wheel |196 PASS /196 PASS на Python3.13|
| Прежний сервер |1066 PASS,20 SKIP,0 FAIL|
| Матрица A01–A29 |29/29 PASS, доказательства указаны отдельно|
| Реальный HTTPS/OAuth staging /production |43/43 PASS /45/45 PASS|
| Production live computation |2 новые численные smoke-траектории; ранее сохранённые чтения/refs сохранены|
| Source/spans/strict integer/atlas limits |адресные отказы; native не подменяет вход|
| Три матричных семейства |3CHECKED_INSTANCE,3REJECTED; неизвестнаяphysics→UNSUPPORTED_MODEL|
| Offline replay с kernel network namespace |Blok3,original4,negative1 завершённых вычислений; одинаковые сохранённые logical digests|
| Исходные research SQLite строки /истории/inodes |все сохранены;4integrity_check=ok|
| Прежние файлы /audit chain |404/404 сохранены;4817 и прежнийc9c0048be5cc2e782cb2f2377da524e5ad04303d86b65792ef1d503b8c1c3d50|
| Runtime/frozen core/root AGENTS |kernel75 иassurance verifier/binder прежние;AGENTS не менялся|
| R3 внешних human reports |PENDING,0; не заменён автоматическим QA|

Сначала сделаны online backups4 SQLite и403 файлов, затем quiescent copies при остановленном HTTP —404 файла (добавился прежний semantic export cache, без изменения исходных403). Заменён только HTTP release entry; исходные2058 canonical и2072 typed событий сохранены. Новый SQLite не создавался. Добавлены только3 новых QA Workspace. Tunnel PID1801300 и прежний URL сохранены. Тест rollback v0.3/72→v0.2/64→v0.3/72 проведён на этом хосте с копиями данных; production обратным переключением не прерывался. Команды — ROLLBACK.md.

Численные timings измерены отдельно: median raw adapter 0.007658s, wrapped facade 0.053642s при фиксированном Блоке,3+3 образцах без выбора лучшего. TIMING.json содержит все samples, native kernel, serialization иjournal-write measurements; реальные transport round trips — MCP transcript, LLM latencies/tokens — COMPARISON_RESULTS.json. Это не обещание такой же удалённой задержки и не метрика художественного преимущества.

Формальные матрицы для приёмки вручную переиспользуют явные экземпляры предоставленного пакета; их происхождение не приписано новому поиску/LLM-открытию. Проверяется конкретное равенство при явно добавленных предпосылках и привязка к зарегистрированному claim/frame. Translation fidelity и physical validity не сертифицированы; verified/PROVED_FORMAL/execution grants не выдаются. Исторические F05/F03/F06 исходного003 остаются историческими материалами.

## Как проверить

В ChatGPT обновите подключение приложения для перечитывания72 tools; адрес тот же. Начните сwhite_star_status, затем создайте свой project и передайте полный [валидный request](../LEVINMAS_WHITESTAR_MCP_001/fixtures/original_request.json). [Quickstart](QUICKSTART_RU.md) описывает encode→explore→inspect→decode→record иfrozen ingress→compare.

Приватная поставка включает standalone wheel/source, C++17 source, wheelhouse, схемы, exact archive, все tests, модельные receipts и полные MCP JSON-RPC без HTTP Authorization. Установите offline wheel, выполните white-star prepare до запроса иreplay_offline.sh. Пакеты содержат разрешённые private source bytes; не публикуйте их автоматически. Live пароли/токены/SQLite/config backups остаются только в owner-private state. Финальные машинные проверки — ACCEPTANCE_RESULTS.json,INTEGRITY_AND_REPLAY.json,SOURCE_COPY_CHECK.json иSHA256_MANIFEST.json.
