# Symbolic V1 — запуск и проверка

Production: `v0.4.1-developer-preview`, 75 инструментов. Прежний HTTPS/OAuth адрес сохранён. Новый режим использует полные токены и их происхождение; численный `white_star_explore` с 2D-координатами остаётся отдельным инструментом.

## Первый MCP-запрос

1. Вызовите `bridge_system_status({})`. В `symbolic_v1` опубликованы версия, READY, полные request/response schemas, kernel binding и реальные лимиты.
2. Зарегистрируйте отдельный проект существующим `assurance_project_new`:

```json
{"project":"symbolic_validation","request_key":"project-init-v1"}
```

3. Передайте в `white_star_symbolic_explore` **весь** [валидный пример](../LIVINGMATH_SYMBOLIC_V1/fixtures/mcp_request_example.json). Source SHA уже соответствует исходным UTF-8 байтам. Объект request этого инструмента отличается от numerical White Star: координаты, axes и ручной semantic encoding не нужны.
4. Сохраните возвращённый `data.run_id`. Читайте результаты через `white_star_symbolic_inspect`:

```json
{"project":"symbolic_validation","run_id":"RUN_ID","view":"claims","offset":0,"limit":32}
```

Вместо RUN_ID подставьте фактический digest из ответа; это единственный placeholder в примере inspect. Views: summary, input, source, operations, observations, claims, history, states, grammar, evaluation, manifest, checks, report, export, artifact.

## Области и статусы

- `SP` применим только к атомам S/P; `FREE` — к произвольным токенам. Для FREE уберите sp_reduce и S/P-операторы и задайте allow_reduce=false. Пустое слово поддержано.
- Сегментация: codepoint, whitespace, line или literal_token с точными byte_start/byte_end/token. Сохраняются исходник, пропущенные разделители, границы и источник каждого атома. NFC задаётся явно и сохраняет карту в исходные байты; токену нельзя разрезать нормализуемый кластер.
- `local` переименование/α-pattern отличается от `global`. Исходное слово, α-класс, S/P-нормальная форма и неразличимость выбранным конечным observer-index — разные отношения.
- `proved_exact` относится к конкретным проверяемым токенным/алгебраическим сертификатам. Грамматические модели остаются empirical/conjecture; недостаточные данные дают UNDERDETERMINED. Ни один такой статус не означает `verified` или разрешение внешнего исполнения.

## Полный результат и replay

Следуйте `next_offset` до null. `limit` — максимум записей, а не гарантия размера страницы. При `requires_artifact=true` читайте view=artifact с указанным artifact_ref, собирайте **все** страницы base64 chunks, затем декодируйте полный JSON. Тихого обрезания нет.

`view=export` возвращает упорядоченные части private data-only ZIP и bundle_ref. Склейте их и проверьте SHA256. Затем `white_star_symbolic_replay(project,bundle_ref)` пересчитает тот же input/seed/operations binding в изолированном процессе. Bundle содержит только JSON/journal; код из него никогда не загружается. Replay посторонних legacy-действий не заявляется.

Повтор project/request_key/request возвращает прежний run; изменение payload под тем же ключом даёт REQUEST_CONFLICT. PROJECT_NOT_FOUND требует явной регистрации, после которой можно повторить исходный ключ. Отмена ожидания клиента не отменяет принятый run. Аварийный restart отмечает незавершённый run как INTERRUPTED, сохраняя историю.

Пределы: 48,000 source bytes; 262,144 request bytes; 2,048 tokens/word; 8,192 nodes/observations; 131,072 суммарных сохранённых токенов; 4,096 steps, 16 candidates/step. Два активных job +16 queued, 5 CPU/6 wall секунд, 512 MiB/job, 32 MiB result. Алгоритмический бюджет возвращает halt_reason; жёсткий CPU/wall/memory предел возвращает WORKER_LIMIT с сохранённым failed run. Более длинные тексты требуют явной сегментации/меньшего конечного среза.

## CLI и тесты

Python3.13, Linux с Landlock ABI≥3, C++17; зависимости прежние:

```bash
python -m pip install '.[white-star,mcp,test]'
python -m lm_suti_assurance white-star prepare
python -m lm_suti_assurance --state-dir /tmp/lm-symbolic project new --project symbolic_validation --request-key init
python -m lm_suti_assurance --state-dir /tmp/lm-symbolic symbolic explore --project symbolic_validation --request-key first --file docs/LIVINGMATH_SYMBOLIC_V1/fixtures/mcp_request_example.json
python -m lm_suti_assurance --state-dir /tmp/lm-symbolic symbolic export --project symbolic_validation --run-id RUN_ID --output /tmp/symbolic-run.zip
python -m lm_suti_assurance symbolic replay /tmp/symbolic-run.zip
python -m pytest -q tests
python tools/symbolic_v1_experiments.py --output /tmp/symbolic-experiments-new
```

Для symbolic-проектов общий assurance_export сообщает SYMBOLIC_EXPORT_REQUIRES_RUN_ID: используйте новый explicit run export. Прежние проекты и numerical bundles сохраняют старый контракт. После публикации новых инструментов обновите список инструментов MCP-клиента; если ChatGPT продолжает видеть72, переподключите LivingMath по прежнему адресу.

[Измерения и приёмка](IMPLEMENTATION_REPORT_RU.md) · [RCA и ограничения](RCA_RU.md) · [машинные результаты](RESULTS.json).

## PATCH001

`white_star_symbolic_inspect` теперь поддерживает `view="comparison"` с optional `compare_run_id` того же проекта. Ответ различает same_literal, same_alpha, same_sp_normal_form, same_history, same_op_trace, same_observer_signature и содержит точные source-span/reduction witnesses. `view="diagnostics"` читает local saturation certificate; у старых профилей явно NOT_RECORDED_IN_HISTORICAL_PROFILE.

Grammar: candidate_status=EMPIRICAL не означает identifiability_status=UNDERDETERMINED. При расхождении retained candidates прогноз имеет family_verdict=INCONCLUSIVE. counterexample_candidates — membership queries к внешнему держателю меток, не полученные истины. Верхний grammar.status теперь отражает UNDERDETERMINED семейства; выбранный кандидат оценивается отдельно. max_rules ограничивает AST, проб не больше64.

NO_NOVEL_CANDIDATES означает отсутствие новых путей в фактически обследованном local proposal cycle/window; не глобальную замкнутость операций. Provenance-paths не сворачиваются в word quotient. Текущие и старые replay profiles делят2 active/16 queued; все прежние CPU/RAM quotas сохранены. Старый bundle выбирает operator-approved immutable profile по binding, без кода из ZIP. При неизвестном binding — явный отказ.

Кеширующему клиенту нужно обновить schema инспектора, переподключив LivingMath по прежнему адресу. Число инструментов остаётся75. [Точные примеры и отчёт](patch001/PATCH001_IMPLEMENTATION_RU.md).
