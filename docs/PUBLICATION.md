# Публикация актуального MCP-сервера

Целевой репозиторий: **[catman77/LivingMath](https://github.com/catman77/LivingMath)**.
По GitHub metadata на 2026-11-06 он **public**. Видимость, настройки доступа и
production данные этой публикацией не меняются. Публикуется исходный код
**v0.4.8-developer-preview / 0.4.8.dev0**, уже прошедший production приёмку.

## Состав

- `src/lm_suti_assurance/`: текущий Python-пакет, frozen checker/binder, Semantic
  Bridge, White Star с исходниками поставленного ядра, Symbolic V1, конечные
  SP-комплексы и независимая проверка синтезированных наблюдателей.
- `tools/`: действующий `release_v01_entry.py`, изоляция, реальные MCP QA-runner,
  воспроизводимые эксперименты и offline replay.
- `live_math_mcp_prod/`: полный сохранённый legacy runtime — HTTPS/OAuth,
  SQLite ledger, исследовательские обязательства/lifecycle, DAV, автоматический
  цикл, artifact/source pipeline, Bridge и операторские утилиты.
- `assets/unified/`, схемы и тесты. Полный сервер использует весь checkout;
  package wheel содержит библиотеку/CLI, а не legacy host и deployment tools.
- [Архитектура](../ARCHITECTURE.md), [интерфейс всех 83 методов](MCP_INTERFACE.md),
  [установка](INSTALL.md), [использование](USAGE.md), [тестирование](TESTING.md),
  contributor guide и third-party notices.
- `suti_author_proposals/`: пять предложений автору SUTI, их основания и варианты
  решения. Они остаются предложениями, а не принятыми изменениями SUTI.
- Выбранные неизменённые архивы ТЗ, source fixtures и проверенные acceptance
  артефакты в `docs/`. Исторические fixtures перечислены в
  `assets/test-fixtures.manifest.json`; новые release-отчёты имеют свои source
  bindings и manifests. Рабочие источники редактируются в распакованных модулях.

## Что остаётся приватным

Живые SQLite и backups, OAuth tokens/client secrets, owner login password,
TLS private keys, production config/approvals, model spool, `.codex-attachments/`,
virtualenvs и неопубликованные полные исследовательские трассы остаются локально.
Существующие пользовательские изменения и неотслеживаемые эксперименты не
добавляются автоматически. Наличие данных в локальном каталоге не означает их
включение в Git.

Большой `LIVINGMATH_FIX_B2_DELIVERY_20261106.zip` хранится локально и не входит в
историю Git; опубликованы его checksum/результат проверки, код воспроизведения,
положительный feature, rejected variants, frozen predictions и schemas. Полные
локальные MCP-трассы и резервные копии доступны владельцу отдельно.

## Подтверждённые проверки

Последний runtime release: **409 PASS** source tests, **409 PASS** установленного
wheel, **1066 PASS / 20 SKIPPED** legacy. Полная MCP-приёмка и31 обязательный gate
содержатся в [отчёте DYCK006](symbolic-v1/dyck006/USER_REPORT_RU.md),
[матрице](symbolic-v1/dyck006/acceptance_matrix.json) и
[манифесте runtime](symbolic-v1/dyck006/release_manifest.json).
Это разные проверки с указанной областью, а не суммарное число уникальных тестов.

Перед публикацией проверяются соответствие отслеживаемого кода этому runtime
манифесту, актуальные версии и schemas, примеры JSON, внутренние ссылки и
публикуемые Git-объекты. Результаты этой отдельной проверки сохраняются в
[publication-v045-checks.json](publication-v045-checks.json).
GitHub Actions проверяется отдельно: исторический `startup_failure` с jobs=0
не является PASS или падением pytest; [исходные факты CI](CI_STATUS.md).

Первоначальный checkout smoke на 44 инструмента и исходные 1074 PASS/12 SKIP
сохранены как исторические данные в `publication-checks.json`; они не подменяют
приёмку актуального сервера на 83 инструмента. Архивные записи не переписываются.

## Публикация и эксплуатация

Публикация выполняется обычным fast-forward push в `main` без force-push,
с сохранением существующей Git-истории. После push проверяются удалённый commit
и файлы. Приватные approvals и рабочие источниковые адреса не превращаются в
разрешения у получателя clone.

Поставка PATCH005 включает отдельное обновление production HTTP-сервиса после
backup и staged QA; текущий адрес и tunnel сохраняются. GitHub публикация сама
по себе не перезапускает установленный сервер. Конечные инженерные PASS не означают
универсальную грамматику или подтверждённый semantic transfer. Native SUTI
остаётся `NOT_EXECUTED`, внешний R3 — `PENDING`; отрицательные научные результаты
Meaning014 и литературного контроля сохранены.


DYCK006: текущая поставка и source snapshot опубликованы в
[v0.4.8-developer-preview](https://github.com/catman77/LivingMath/releases/tag/v0.4.8-developer-preview).
[Приёмка, исходные run IDs и данные](symbolic-v1/dyck006/USER_REPORT_RU.md).
ZIP включает новый и historical0.4.7 wheels, исходный патч/full source,
замороженные входы/gold, полные staged/public MCP трассы и failed attempts.
Приватные конфигурации, OAuth credentials, production SQLite/workspaces исключены.
Это developer preview, не R3 approval и не universal invariant.
