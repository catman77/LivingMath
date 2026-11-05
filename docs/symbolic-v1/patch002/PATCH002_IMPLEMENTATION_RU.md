# PATCH002_IMPLEMENTATION_RU

## Результат

Установлен **v0.4.2-developer-preview**, symbolic_v1/1-patch002, deployment `symbolic-patch002-20261105T075501Z`.
Адрес сохранён: https://fares-september-rebel-board.trycloudflare.com/mcp. Все75 MCP input/output schemas и annotations совпадают с production PATCH001; переподключение для новых аргументов не требуется. Если ChatGPT удерживает закрытую HTTP-сессию после restart, переподключить LivingMath по тому же адресу.

Архив сохранён без изменений: [docs/LIVINGMATH_SYMBOLIC_PATCH002_ACCEPTANCE_REAL_TESTS_20261105.zip](../../LIVINGMATH_SYMBOLIC_PATCH002_ACCEPTANCE_REAL_TESTS_20261105.zip), SHA256 `549dfd97c61023b42bb26021d79b43eca6f4087faeaa909902e1450ec06c7834`. Все7 исходных файлов распакованы в docs/LIVINGMATH_SYMBOLIC_PATCH002; reproduction содержит реально выгруженные requests и golden fixtures. [План](../../superpowers/plans/2026-11-05-symbolic-patch002.md).

## Реальный механизм

Изменён существующий symbolic/search.py. До локальной стагнации используется прежний seeded set-inclusion выбор Удава; первые5 шагов проблемного Nostradamus совпадают с прежним trace. Обнаружив повтор локального clock-state или bounded no-growth окно, контроллер выбирает untried сохранённую пару (node_id, operator) по digest([seed, operator, node_id]). Пара выполняется в первом **обычном** слоте следующего шага; clock и аргументы прежние. Никаких дополнительных шагов, apply вне бюджетного цикла, новых слов при планировании, LLM или фоновых jobs.

Очередь ограничена max_nodes × числом разрешённых операторов. Одна пара получает не более одного forced proposal; local proposals могут её повторять. Покрытие пары означает одну clock-sampled вариацию аргументов, не все возможные позиции SPLIT/пары CONCAT/отображения. ACTUAL_LOCAL_EXHAUSTION относится только к такому конечному фронтиру; global_exhaustion_proved всегда false. Новые параметры/DSL/математические операции не вводились.

Diagnostics сохраняет LOCAL_STAGNATION, FRONTIER_FALLBACK, ACTUAL_LOCAL_EXHAUSTION либо фактический MAX_STEPS/MAX_NODES/MAX_TOTAL_TOKENS/MAX_OBSERVATIONS, candidate_attempts, frontier_size (число untried node/operator pairs), untried_allowed_operators, fallback_count/reason и ссылки на реальный DAG. WORKER_LIMIT по-прежнему выдаёт изолированный supervisor при CPU/RAM/wall/queue limit; частичный поиск при уничтоженном worker не выдаётся за сохранённое свидетельство. Пустой max_steps=0 возвращает терминальную диагностику с нулём попыток и без saturation certificate.

Счётчики proposed/accepted/duplicate/forbidden/resource_limited проверены по настоящему ops_trace. Ранее последняя budget-blocked попытка не попадала в trace; теперь она включается с точной причиной. Before coverage честно отмечает unrecorded_candidate_attempts, не приписывает их неизвестному оператору. Word/provenance остаётся явно выбранной семантикой.

## Контролируемые результаты

| Корпус, один и тот же request | v0.4.1: узлы / шаги | v0.4.2: узлы / шаги | Fallback | Завершение v0.4.2 |
|---|---:|---:|---:|---|
| nostradamus_original_local_word | 18 / 5 | 383 / 99 | 1 | MAX_NODES |
| mallarme_original | 640 / 141 | 640 / 141 | 0 | MAX_NODES |
| mallarme_reverse | 60 / 12 | 466 / 160 | 2 | MAX_STEPS |

Каждая строка сравнивает совершенно одинаковый request, включая source/segmentation/operators/seed/budgets/task; исходный v0.4.1 worker реально пересчитал прежний digest. Настройки разных строк/вариантов не смешиваются для причинного вывода. [Полные данные и охват операторов](BEFORE_AFTER.json).

На исходном Nostradamus в момент локального тупика оставались64 untried пары. Fallback выбрал сохранённый SOURCE_RECORD `84ce7fac89c1a91a682e033e0a10822c837cdc2b22f72830a5c6fa5caab99ee9` и RENAME, создал новый узел `19e01abedffe61b2b339db04e5be43296a9318af081a7d237ba4d54d97123393`. Исходные имена/spans и mapping остались в DAG.383 узла при max_nodes=384 — корректный консервативный предел: следующий SPLIT выдаёт2 результата, прежняя admission-проверка не добавляет их в единственный оставшийся слот.

Грамматический исходник и весь golden grammar/heldout output совпадают с v0.4.1. Выбранное правило9/9, family UNDERDETERMINED. Больше состояний не означает найденный литературный смысл; Малларме проверен только как15 линейных фрагментов и структурный контроль обращения порядка.

## Приёмка

| Gate | Фактический результат |
|---|---|
| Baseline до runtime edits |261 PASS|
| Полный source pytest |272 PASS|
| Установленный0.4.2 wheel вне checkout |272 PASS|
| Legacy suite |1066 PASS /20 SKIP|
| Controlled before/after реальные workers |38 PASS|
| OAuth/MCP на копии production |247 PASS|
| Действующий HTTPS/OAuth MCP |248 PASS|
| Три offline replay в unshare -Urn |REPLAY_MATCH|

Число MCP checks динамическое: включает каждую страницу/вызов; в production исторический экспорт потребовал дополнительный вызов после роста рабочего журнала. Это не пропуск staging-инварианта.

[Матрица T01–T08](ACCEPTANCE_MATRIX.json), [машинные результаты](REGRESSION_RESULTS.json), [RCA](RCA_RU.md), [изменённые файлы](CHANGED_FILES.md). Предыдущие AC01–AC16 сохранены с прежними исследовательскими оговорками: AC11 structural-only, AC14 family underdetermined, AC16 bounded gates, не полный pentest. Hosted CI/долгая нагрузка NOT_RUN; R3 PENDING, native SUTI NOT_EXECUTED, execution_permission=false.

## Production и сохранность

Перед переключением сделаны online и quiescent backups4 реальных SQLite и файловых workspace. В initial snapshot2272 файла; к cutover3391: в рабочем whitestar_dialog_test появились новые записи и append-only продолжение журнала. **Оба** snapshot сохранены: исходные объекты побайтны, старый журнал остаётся точным префиксом. Все исходные research/typed/DAV rows сохранены; canonical audit4817/head c9c0048be5cc2e782cb2f2377da524e5ad04303d86b65792ef1d503b8c1c3d50 без изменений. Все19 текущих журналов валидны;24 заданных historical summaries совпадают со staging snapshot. [Проверка целостности](INTEGRITY.json).

Перезапущен только livingmath-http.service. livingmath-https.service/PID1801300 и URL прежние. Базы не создавались/заменялись; inode прежние. Активных/незавершённых QA runs и execution grants нет. Сохранены реальные immutable v0.4.0 и v0.4.1 replay workers с прежними manifest; все3 symbolic профиля разделяют2 active/16 queued. Numerical base_v1/cj_v1,75 source hashes и frozen ядро не менялись. Из178 runtime файлов изменились ровно5: search/kernel/mcp, package version и entry version allowlist.

## Запросы и воспроизведение

Проект `qa-patch002-prod`; новый Nostradamus run `3daf7ecc87ac6c7bb63ac7de5d330e851bdf817965a1cca664d3a13055ae6109`,
result_digest `bf12e54911e4103011efc4f0d811d1d4405371b53bbda38cdbe4f5f59266cdd8`.

```json
{"project":"qa-patch002-prod","run_id":"3daf7ecc87ac6c7bb63ac7de5d330e851bdf817965a1cca664d3a13055ae6109","view":"diagnostics"}
```

Передать в white_star_symbolic_inspect. Исторический run `61c5af7aa611ed03e914ec72848a0ec84c608a785b44cab4c286696ec6001475` не изменён и по-прежнему описывает прежние18 узлов/5 шагов.

```bash
python -m pytest -q tests
(cd live_math_mcp_prod && python -m pytest -q .)
PYTHONPATH=src python tools/symbolic_patch002_acceptance.py --baseline-dir replay/baseline-runs --historical-worker /PATH/TO/INSTALLED_V041/src/lm_suti_assurance/symbolic/worker.py --output /tmp/patch002-controlled-new
python tools/symbolic_patch001_mcp_qa.py --patch002 --expected-version v0.4.2-developer-preview --origin https://fares-september-rebel-board.trycloudflare.com --endpoint https://fares-september-rebel-board.trycloudflare.com/mcp --baseline evidence/tools-before.json --output /tmp/patch002-mcp-new --tag repeat
unshare -Urn python -m lm_suti_assurance symbolic replay replay/nostradamus-patch002.zip
```

Live runner требует owner credentials вне пакета, пишет их отдельно и создаёт только QA-проект. Для CLI replay требуется установленный wheel соответствующего binding; historical replay на сервере выбирается по owner-approved manifest, код из ZIP не загружается.

Поставка: exports/LIVINGMATH_SYMBOLIC_PATCH002_DELIVERY_20261105.zip; patch к `587b4fcdd99d9675f80b6377ea70cdfd66b0530f`, изменённые файлы, установленный wheel, data-only replay bundles, полные JSON-RPC request/response и все логи, включая начальные red tests. Пароли/SQLite/конфигурации владельца исключены. Rollback профиля реально пересчитан offline и через MCP; полный обратный production cutover не проводился. Прежний drop-in и backups сохранены для конфигурационного отката без восстановления БД поверх новых записей.
