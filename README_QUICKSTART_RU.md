# LivingMath × SUTI v0.4.11 — developer preview

Однопользовательский CLI для конечных проверок и проверок исходных документов. Он использует **неизменённые** verifier ASSURANCE-001 и binder ASSURANCE-002 из сохранённой поставки ASSURANCE-003. Модель, API-ключ и подписка для ручного пути и replay не нужны.

## Установка и одна команда проверки

Проверены Python 3.13 и 3.14, Linux x86_64. Из корня поставки:

```bash
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install .
lm-suti doctor --smoke
```

Из wheel, предварительно собранного командой `python -m pip wheel --no-deps . -w dist`:
`python -m pip install dist/lm_suti_assurance-0.4.11.dev0-py3-none-any.whl`.
Установка зависимостей может требовать интернет; сам replay сеть не использует. Офлайн-установка: заранее собрать wheelhouse через `python -m pip download --only-binary=:all: -d wheelhouse ./dist/*.whl`, затем `pip install --no-index --find-links wheelhouse lm-suti-assurance`. Бинарные зависимости должны соответствовать Python и платформе получателя.

## Полный ручной путь

```bash
lm-suti examples --output demo --project pilot
lm-suti project new --project pilot --request-key project-new
lm-suti source add --project pilot --snapshot demo/C1-source-0.json --policy demo/policy.json --request-key source-C1
lm-suti task import --project pilot --file demo/C1-task.json --request-key task-C1
```

Сохраните `task_ref` из последнего ответа. Прочитайте `demo/C1-task.json`: область `[0,15]`, предпосылки и SHA источника должны соответствовать вашему утверждению. Подтвердите именно эту задачу:

```bash
lm-suti task review --project pilot --task-ref TASK_REF --actor owner --reason 'Подтверждаю точный источник, область 0..15 и предпосылки' --request-key review-C1
```

Создайте `candidate.json`, подставив настоящий `TASK_REF`:

```json
{"schema":"lm-suti.assurance.candidate/0.1","project":"pilot","task_ref":"TASK_REF","format":"delta","raw":"{\"schema\":\"symseq.assurance.proposal-delta.v1\",\"intent\":\"PROPOSE\",\"kind\":\"BOUNDED_PROPERTY\",\"property\":\"PRESERVES_POPCOUNT\"}"}
```

```bash
lm-suti candidate import --project pilot --file candidate.json --request-key candidate-C1
lm-suti check --project pilot --candidate-ref CANDIDATE_REF --request-key check-C1
lm-suti report --project pilot
lm-suti export --project pilot --audience reviewers --output pilot.zip
lm-suti replay pilot.zip --offline
lm-suti replay pilot.zip --offline --engine compiled
```

Это **7 команд** от source add до export для одного источника; чтение точной задачи и создание файла кандидата — отдельные ручные действия; генерация каталога примеров и project new идут до них. Машинный smoke отдельно считает только вызовы API и не является замером времени внешнего пользователя.

## Проверяемые примеры и границы

`lm-suti smoke --output smoke-output` сохраняет воспроизводимый `pilot.zip`: ложное ENTAILED (23/24) → REJECTED и две контрмодели; bounded popcount → CHECKED_FINITE; потеря SUTI-поля → SOURCE_ATTESTED; эмпирическая гипотеза → UNKNOWN; смена scope → REJECTED.

CHECKED_FINITE относится только к полному объявленному конечному классу/домену. SOURCE_ATTESTED относится к байтам/полям источника, не к физической истине и не к юридическому разрешению на действия. UNKNOWN/HOLD не означает опровержение. `execution_permission` всегда false. Native SUTI: NOT_EXECUTED; formal adapter: UNAVAILABLE_NOT_REGISTERED.

Правила экспорта: `rights.can_embed=true`, `rights.status=DECLARED_USER_AUTHORIZED` **и** разрешение публикационной политики для выбранной аудитории. Иначе байты отсутствуют, а replay выдаёт MISSING_SOURCE_DEPENDENCY. Все отрицательные кандидаты и supersession сохраняются. Новая версия задачи требует отдельного review. Исходные файлы журнала не редактировать.

## Внешний пилот

Два внешних технических участника должны независимо установить пакет и воспроизвести `pilot.zip`, не имея исходной модели. Заполните `docs/release-v01/EXTERNAL_PILOT_FORM.md`. Автоматические smoke/MCP-проверки не заменяют этот gate. До появления реальных отчётов R3 остаётся PENDING, финальная готовность не объявляется.

## Текст и версии интерпретаций

[Semantic Bridge: полный путь](docs/semantic-bridge/QUICKSTART_RU.md) добавляет `semantic source/draft/revise/compare/report/withdraw`. В production опубликованы девять `semantic_*` инструментов; прежние 55 input schemas сохранены. Для генерации нужен уже авторизованный Codex CLI с ChatGPT-login; ручной импорт и replay этого не требуют. При недоступности backend возвращается `MODEL_UNAVAILABLE`.

Пакет Python имеет версию `0.4.11.dev0`, основной MCP endpoint — `v0.4.11-developer-preview`, 94 инструмента. `doctor.release`, `assurance_contract.release` и префикс `lm-suti --version` сохраняют базовую версию assurance v0.1 для совместимости; `semantic_contract.release` показывает сохранённый контракт v0.2, `white_star_status.release` — v0.3. Frozen verifier/binder не менялись. Версия всего сервера читается через `bridge_system_status` или MCP initialize.

## Белая звезда

Для этого дополнительного режима нужны Linux с Landlock ABI≥3, Python 3.13+, C++17, NumPy 2.3.5 и pandas 2.2.3. Проверенный путь: `pip install '.[white-star,mcp,test]'`, затем `lm-suti white-star prepare`. Сборка выполняется явно до запросов. [Полный цикл, произвольный текст, экспорт и сравнение](docs/white-star/QUICKSTART_RU.md). Обычный assurance CLI не требует NumPy/C++ или модели. Legacy development endpoint публикует 44 инструмента; production release entry объединяет 94. [Архитектура](ARCHITECTURE.md), [MCP-справочник](docs/MCP_INTERFACE.md), [различия запуска](docs/INSTALL.md).
