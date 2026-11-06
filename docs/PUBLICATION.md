# Публикация актуального MCP-сервера

Целевой репозиторий: **[catman77/LivingMath](https://github.com/catman77/LivingMath)**.
По GitHub metadata на 2026-11-06 он **public**. Видимость, настройки доступа и
production данные этой публикацией не меняются. Публикуется исходный код
**v0.4.5-developer-preview / 0.4.5.dev0**, уже прошедший production приёмку.

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

Последний runtime release прошёл **337 PASS** source tests, **337 PASS** wheel
вне checkout, **1066 PASS / 20 SKIPPED** legacy и **656 PASS** настоящего
HTTPS/OAuth MCP. [Матрица](symbolic-v1/v044-reacceptance/acceptance_matrix.json),
[отчёт](symbolic-v1/v044-reacceptance/USER_REPORT_RU.md),
[манифест установленного слоя](symbolic-v1/v044-reacceptance/release_manifest.json).
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

Эта операция обновляет GitHub. Уже установленный production код не меняется и
не перезапускается из-за документации. Конечные инженерные PASS не означают
универсальную грамматику или подтверждённый semantic transfer. Native SUTI
остаётся `NOT_EXECUTED`, внешний R3 — `PENDING`; отрицательные научные результаты
Meaning014 и литературного контроля сохранены.
