# Конечное покрытие CJ: MCP-COMPLETENESS-001

Opt-in расширение для `cj_v1` и наблюдателя
`pair-sign-and-absolute-dominance/1` конструирует witness каждого качественного
состояния допущенных неколлинеарных пар и обязательно обслуживает их через
существующий `cad.project`. Число целей выводится из атласа.

Это конечная полнота геометрического наблюдателя, не полнота смыслов, native
сигнатур или бесконечного множества witnesses. LLM не вызывается.

## Установка и воспроизведение

Python 3.13+, окружение проекта с extras `mcp,white-star,test`:

```bash
python -m pip install -e '.[mcp,white-star,test]'
python -c 'from lm_suti_assurance.white_star.pool import prepare; print(prepare())'
python -m pytest -q tests/test_completeness.py tests/test_completeness_boundaries.py
python tools/completeness001_server.py --state /tmp/lm-cj-qa/workspaces --port 18765
```

Локальный Streamable HTTP endpoint: `http://127.0.0.1:18765/mcp`; выбирайте
свободный порт. QA-сервер регистрирует 76 существующих инструментов и четыре новых,
он не заменяет production-композицию из 106 инструментов (102 прежних +4). Прежние
вычислительные инструменты на этом стенде публикуются без executors; вычисления
нового режима выполняет настоящий изолированный CAD worker.

Полная приёмка приложенного приватного fixture, включая настоящий restart:

```bash
python tools/completeness001_mcp_qa.py \
  --input /private/extracted-package/INPUT.json \
  --output /private/new-qa-output
```

Рядом с `INPUT.json` нужен исходный `independent_verify.py` из архива. Runner
выбирает свободный loopback-порт. Полная MCP-трасса, source, страницы и журнал
остаются в приватном output; не добавляйте их в Git.

Общий `assurance_export` для проектов с `coverage.*` явно отклоняется кодом
`COVERAGE_EXPORT_REQUIRES_PLAN_REF`: он не имеет правил публикации и replay этого
нового журнала. Используйте `coverage_inspect`; приватный source не включается
автоматически в общий public/reviewers ZIP.

## Контракт инструментов

Сначала `assurance_project_new(project="cj-qa", request_key="init")`.
`source_request` использует **тот же** полный контракт
`levinmas-white-star-request/1`, что `white_star_explore`: source SHA,
точные UTF-8 цитаты, концепты, две оси и protocol. Пример без чужого текста:
`white_star/vendor/fixtures/original_request.json` в установленном пакете.
Его геометрия отличается от приватного fixture.

1. `coverage_plan(project, request_key, source_request, scope)`.
   Обязательный scope:
   `{"mode":"completeness_only","observer":"pair-sign-and-absolute-dominance/1"}`.
   Ответ: `plan_ref`, неизменный `total_count`, `kernel_binding`, независимая
   проверка и исходный объект `cursor`. Планирование не выполняет цели.
2. `coverage_advance(project, plan_ref, request_key, cursor, work_budget)`.
   Передавайте **весь cursor из последнего ответа**, не только индекс.
   Бюджет 0..128 проекций; недостаточный бюджет возвращает PARTIAL.
   При ERROR обязательство остаётся открытым. Повтор ключа/аргументов возвращает
   прежнюю квитанцию; новая попытка после ошибки требует нового ключа.
   Изменение аргументов под прежним ключом отклоняется.
3. `coverage_inspect(project, plan_ref, view="summary", cursor=0, page_size=64)`.
   `view=plan/atlas/omissions/records`: полные страницы до `next_cursor=null`.
   Для крупных записей страница может быть меньше запрошенной; denominator
   не меняется. Полные данные находятся в MCP `structuredContent`, текстовый
   content содержит краткий preview без повторного копирования records.
4. `coverage_replay(project, plan_ref, cursor=0, work_budget=64)`.
   Повторяет сохранённые проекции закреплённым изолированным worker. Следуйте
   `next_cursor` до null, проверяйте сумму `checked_count`. Это не исполнение
   heuristic orbit prefix и не проверка смысла источника.

## Вычисление, экспорт и доставка

`compute_complete` возникает после долговечного сохранения всех проверенных
квитанций; `export_available` означает доступность всех records. Сервер не
заключает, что клиент их получил. После объединения страниц клиент сверяет
`export_sha256` с SHA-256 канонического JSON всего списка (`sort_keys=True`,
`ensure_ascii=False`, separators `(',', ':')`, `allow_nan=False`).

Затем клиент явно вызывает `coverage_inspect` с `view="delivery"`, новым
`request_key` и `acknowledgement={"export_sha256":"<полный SHA>",
"record_count":224,"client_id":"my-mcp-client"}`. Число берётся из ответа,
не фиксируется для других источников. `delivery_acked` фиксирует декларацию
названного клиента, не доказывает чтение или смысловое понимание LLM.

## Ограничения, production и откат

Поддерживается только `cj_v1`; `base_v1` явно отклоняется. Координаты концептов
ограничены 10⁶; сохраняются прежние лимиты charts, входа/выхода и worker
(5 секунд CPU, 6 секунд wall, 512 MiB, 2 active/16 queued). Python integers
точные; floating phase вспомогательна. Квота/ошибка не превращаются в COMPLETE.

Production entry подключает расширение **только** при owner-конфигурации
`"certified_coverage":{"enabled":true}` в новом закреплённом слое. Численный
бюджет разделяется с White Star/UDAV workers. Расширение установлено в production
v0.4.16 на прежнем HTTPS-адресе; [receipt и приёмка](DEPLOYMENT_RU.md). В ChatGPT
переподключите LivingMath, чтобы обновился закешированный список инструментов.

Миграция SQLite отсутствует. Данные используют существующий Workspace и
append-only journal. Для отката отключите opt-in и верните предыдущий слой;
новые журналы сохраняйте. Автоматически архивировать весь проект не требуется.
