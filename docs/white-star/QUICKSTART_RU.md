# White Star — проверка через MCP и CLI

Текущий production: **v0.4.10-developer-preview**, 93 инструмента. Версию всего
сервера проверяйте через `bridge_system_status`; `white_star_status.release`
сохраняет версию численного контракта v0.3. Адрес установленного сервера:
`https://fares-september-rebel-board.trycloudflare.com/mcp`. Если список методов
закеширован, обновите подключение по тому же адресу.
[Архитектура](../../ARCHITECTURE.md) · [Полный MCP-интерфейс](../MCP_INTERFACE.md).

## Проверка действующего сервера

Первый read-only вызов — `white_star_status({})`: он публикует полные input/output schemas, реальные readiness/limits и SHA75 исходных файлов. `SUTI_native_runtime=NOT_EXECUTED` остаётся видимым.

Сохранённый пример: `white_star_inspect(project="qa-whitestar-blok", run_id=RUN_ID, view="summary")`. RUN_ID находится в отчёте/COMPARISON_RESULTS.json приватной поставки. Для нового опыта сначала создайте свой проект через `assurance_project_new(project, request_key)`.

[Отчёт об исправлении регистрации и реальный запуск 64 шагов](ONBOARDING_FIX_REPORT_RU.md).

### Обязательная регистрация проекта

Готовность `READY` не регистрирует исследовательский проект. Для первого запуска выполните **два отдельных вызова MCP**. Сначала:

```json
{
  "name": "assurance_project_new",
  "arguments": {
    "project": "my-white-star-project",
    "request_key": "project-init-v1"
  }
}
```

Затем вызовите `white_star_explore` с тем же `project`, отдельным `request_key` (например, `experiment-1`) и полным объектом `request` из [валидного примера](../LEVINMAS_WHITESTAR_MCP_001/fixtures/original_request.json). Это поля MCP `tools/call`, а не поля самого `request`. Регистрация использует тот же namespace, что White Star; регистрация одноимённого legacy research-проекта не заменяет этот шаг.

Если получен `PROJECT_NOT_FOUND`, поле `/project` и сообщение содержат точный вызов регистрации для указанного проекта. Зарегистрируйте его и повторите исходный explore **без изменения request_key и request**: отказ не создаёт run и не занимает ключ. Повтор принятого explore с тем же содержимым возвращает прежний run_id без повторного вычисления. Обычный `NOT_FOUND` для отсутствующего run_id — другая ошибка. В `white_star_status.data.workflow` опубликованы порядок действий и шаблон регистрации.

1. LLM-клиент формирует `request` по [полному валидному примеру](../LEVINMAS_WHITESTAR_MCP_001/fixtures/original_request.json). Готовый JSON-RPC пример — [mcp_blok_call.json](../LEVINMAS_WHITESTAR_MCP_001/fixtures/mcp_blok_call.json). Замените только project/request_key и свой явный encoding; не подставляйте имена Блока в другой текст.
2. Вызовите `white_star_explore(project, request_key, request)` с объектом request. Укажите точный текст, SHA256 его UTF-8 байтов и полуинтервальные byte spans. Line начинается с1. Никакой нормализации ё/тире/переводов строк. Каждое понятие имеет label, evidence, ненулевые отличные целые coordinates и encoding_rationale. Protocol задаётся явно; рекомендуемый пример — seed42,steps64,k3,frame_size3,decode_first_frames6. Оси/координаты — дополнительные предпосылки, не свойства текста.
3. Читайте `white_star_inspect(..., view="decoder")`, затем сформулируйте до K прочтений в порядке доступных frames. Source anchors, новые связи, добавленные предпосылки, альтернативы и ограничения разделяйте явно. Сервер White Star не вызывает LLM.
4. Сохраните их через `white_star_record_interpretation(project,run_id,request_key,readings)`. Точная схема readings опубликована в status; поля: frame_id,text,evidence,added_assumptions,uncertainties,alternatives,claim_atoms. Claim kind — INTERPRETATION. Необязательная provenance сохраняет модель, instruction/receipt SHA, usage/latency и decoder_protocol_id как декларацию клиента.
5. Для сравнения вызовите `semantic_run_frozen(project, request_key, common_snapshot_ref, decoder_slots=6)` с ref из explore. Реальный существующий assurance facade получает те же сохранённые понятия/цитаты/связи без нового extraction. Это Bridge source assurance, не native SUTI. Декодируйте его packet той же моделью и инструкцией.
6. Вызовите `semantic_compare_runs(project,left,right,protocol)`; left/right содержат engine (`white_star`/`suti`) и run_id, protocol — mode="MATCHED_INPUT" и decoder_protocol_id. Совпадения source SHA недостаточно: изменённая общая разметка даёт UNMATCHED_INPUT. Команда не вызывает модель и не назначает победителя.

Численные weights не вероятности;52 качественных режима не52 независимых литературных смысла. Недоступные слоты остаются пустыми. На коротком примере Bridge имеет4 слота из6: это сохранено явно.

## Формальные модели

`white_star_validate_model(project,run_id,proposal)` требует claim_ref из сохранённого reading и frame_refs того же run. Поддержаны observation_invariant,control_invariant,cyclic_order. Матрицы прямоугольны, размер1..8, элементы — integers или строки вида `-3/2`, максимум256 бит; bool/float/нулевой знаменатель запрещены. Cyclic_order пока2x2. Укажите mapping_assumptions и проверяемые obligations. Countermodel — явные matrix overrides, проверяемые отдельно.

CHECKED_INSTANCE означает только конкретное рациональное равенство/неравенство. Контрпример возвращает REJECTED с witness как нормальный результат, а неподдержанная chemistry/physics — UNSUPPORTED_MODEL. Перенос смысла и физическая состоятельность не становятся доказанными.

## Журнал, страницы и replay

Повтор project+request_key с тем же полным payload возвращает прежний run; другое содержимое — REQUEST_CONFLICT. Принятый run завершается независимо от отмены клиентского ожидания. После аварийного restart незаконченный RUNNING получает INTERRUPTED, без фиктивного продолжения из snapshot-счётчиков.

Inspect: default limit64,max128, целые записи и next_offset. Большая одиночная запись возвращает requires_artifact и artifact_ref: читайте view="artifact", склеивайте base64 chunks по index и выбирайте нужное JSON-поле. Тихого обрезания нет. View="input" содержит protocol и происхождение encoding; summary — фактический расход. Лимиты2 concurrent+16 queued,5CPU/6wall секунд,512MiB,32MiB result относятся к numerical job, не к LLM.

`white_star_inspect(...,view="export",offset=0,limit=1)` возвращает части приватного ZIP и bundle_ref; соберите все страницы, проверьте SHA. `white_star_replay(project,bundle_ref)` пересчитывает сохранённые завершённые вычисления без модели/сети. Публикация White Star ограничена private. Rights PUBLIC_DOMAIN,ORIGINAL_TEST_FIXTURE,USER_AUTHORIZED_PRIVATE,DECLARED_USER_AUTHORIZED — декларации вызывающего владельца, не юридическая сертификация. При иных правах или исключении bytes экспорт содержит missing dependencies, replay не подменяет их пустым текстом. Дополнительно работает прежний export_guard.

## Установка и CLI

Проверены Python3.13,Linux x86_64,Landlock ABI≥3,C++17. Из корня checkout:

```bash
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install '.[white-star,mcp,test]'
lm-suti white-star prepare
lm-suti --state-dir ./private-state project new --project demo --request-key new
lm-suti --state-dir ./private-state white-star explore --project demo --request-key run-1 --file docs/LEVINMAS_WHITESTAR_MCP_001/fixtures/original_request.json
lm-suti --state-dir ./private-state white-star inspect --project demo --run-id RUN_ID --view decoder
lm-suti --state-dir ./private-state white-star frozen --project demo --request-key bridge-1 --common-ref COMMON_REF --slots 6
lm-suti --state-dir ./private-state export --project demo --audience private --output demo.zip
lm-suti replay demo.zip --offline
```

Замените RUN_ID/COMMON_REF адресами из реального explore. Build только через prepare, затем библиотека проверяется до ready; отсутствие .so даёт ENGINE_UNAVAILABLE. Исходники всех 75 vendor-файлов сохраняются побайтно. Пакет standalone CLI не требует production OAuth. QA-runner запускается из полного репозитория с существующими legacy client helpers; полный 83-tool HTTP endpoint использует установленный release entry и owner-private config. [Запуск/обновление/откат текущего хоста](ROLLBACK.md).

В приватной поставке предусмотрены wheelhouse и `replay_offline.sh`. Сначала установите wheel без сети, выполните prepare с локальным C++17, затем скрипт. Реальная проверка этой поставки проведена также в kernel network namespace (`unshare -Urn`), без OAuth/LLM. R3 двух внешних людей остаётся PENDING.
