# GitHub Actions отключён владельцем

## Текущая поставка v0.4.15 — 2026-11-09

По прямому указанию владельца GitHub Actions отключён в настройках catman77/LivingMath: **enabled=false**, подтверждено API GET. Оба определения перенесены из .github/workflows/ в .github/workflows-disabled/*.disabled с сохранением исходных bytes. Активных workflows в checkout нет. Сборка, unit/integration, installed-wheel проверки, staging и deployment выполняются локально; push/tag/release только публикует готовые файлы. Actions для этой поставки не запускался и не используется для обновления MCP. Статус **DISABLED_BY_USER_REQUEST_NOT_EXECUTED**, не PASS и не текущая ошибка pytest.

Фактическая локальная/живая приёмка:545 installed-wheel PASS;1066 legacy PASS/20 прежних SKIP;236 PATCH002 +68 SB-EXP01 checks на staging и на публичном HTTPS MCP. [Настройки Actions](semantic-bridge-patch002/ACTIONS_DISABLED.json), [матрица](semantic-bridge-patch002/TEST_MATRIX.json), [отчёт](semantic-bridge-patch002/IMPLEMENTATION_REPORT_RU.md). Сведения о публикации появятся в отдельном PUBLICATION_CERTIFICATE.json после обратной сетевой сверки. Исторические отказы ниже сохранены.

## Предыдущая проверка v0.4.14 от 2026-11-09

[Релиз v0.4.14](https://github.com/catman77/LivingMath/releases/tag/v0.4.14-developer-preview) опубликован; production обновлён с сохранением URL и `authentication=none`. Код production: `23c4aac0d2793170def4642e0e53bde59e741ac4`; снимок исходников и документации: `e133c0c4b6bc3e3e0d5ffa6eea94d426988b3ada`. Подключённый MCP подтвердил версию и 102 инструмента.

Анонимная обратная сверка: **1891 Git blob**, ZIP **40060274 bytes**, SHA256 `bf6bbe019373abfd004d18c6c5054e6b71a250de36f733f0a3bf712138a1fb15`. Локально **514 PASS**, legacy **1066 PASS / 20 прежних SKIP**; реальный HTTPS MCP **68/68**, staging **68/68**, три дополнительных постраничных представления PASS. Сценарии контекста независимо от типизации формулы исправлены; v0.4.13 сохранён как предыдущая версия.

Все три GitHub jobs не запустились: `The job was not started because your account is locked due to a billing issue.` CI=`NOT_RUN_ACCOUNT_BILLING_LOCK`, не PASS. Workflow, тесты и billing не менялись.
[Фактические annotations](semantic-bridge-patch001/GITHUB_CI.json), [публичная сверка](semantic-bridge-patch001/PUBLIC_READBACK.json), [сертификат поставки](semantic-bridge-patch001/PUBLICATION_CERTIFICATE.json).

## Предыдущая проверка v0.4.12 от2026-11-08

Code commit `210d6a36bbd8275ee26483b4afb10e8140318ae7`; [релиз](https://github.com/catman77/LivingMath/releases/tag/v0.4.12-developer-preview) опубликован. Анонимно скачаны и сверены1836 source blobs и ZIP66 482 822 bytes.
Installed wheel485 PASS, legacy1066 PASS/20 SKIP, reference5 PASS; public MCP490 symbolic/1436 numeric/6 extra checks PASS.

Все3 GitHub jobs не запустились: `The job was not started because your account is locked due to a billing issue.`
CI=`NOT_RUN_ACCOUNT_BILLING_LOCK`, не PASS. Workflow и billing не менялись.
[Фактические annotations](udav-core001/GITHUB_CI.json), [публичная сверка](udav-core001/PUBLIC_READBACK.json), [сертификат поставки](udav-core001/PUBLICATION_CERTIFICATE.json).

## Предыдущая проверка v0.4.11 от2026-11-07

Code commit `e7b92a9ebb00055d9f2d96a44d66fdfc81c25df8` и
[релиз](https://github.com/catman77/LivingMath/releases/tag/v0.4.11-developer-preview)
опубликованы. Анонимно скачаны и сверены1766 source blobs и ZIP86 390 583 bytes.
Локально464/464 source tests и464/464 installed-wheel tests; на production
60 causal checks,869 formal checks/667 MCP calls,1024/1024 legacy rows и12 old replay.

У всех6 GitHub checks conclusion=failure; annotation сообщает:

> The job was not started because your account is locked due to a billing issue.

GitHub-тесты не запускались. CI=`NOT_RUN_ACCOUNT_BILLING_LOCK`, а не PASS.
[Фактические checks/annotations](nl-causal003/GITHUB_CI.json),
[публичная сверка](nl-causal003/PUBLIC_READBACK.json). Условия тестов и workflow
не ослаблялись; billing не менялся.

## Предыдущая проверка v0.4.5 от2026-11-06

Код v0.4.5 опубликован в `main`, commit
`5f7ebe0a5c57be2d48251e09950917f2706f8328`. Обратное сетевое клонирование
подтвердило SHA-256 всех **1312** отслеживаемых файлов. Локально заново прошли
**337** тестов полного пакета на Python 3.13 и **155** assurance/Semantic тестов
на Python 3.14, плюс doctor smoke в обоих окружениях.

| Workflow | Run | Наблюдение |
|---|---|---|
| Current package and assurance compatibility | [42159890742](https://github.com/catman77/LivingMath/actions/runs/42159890742) | Два job созданы, оба `failure`, `steps=[]`, runner не назначен |
| Python checks | [42159891067](https://github.com/catman77/LivingMath/actions/runs/42159891067) | Один job создан, `failure`, `steps=[]`, runner не назначен |

Checks annotations трёх job (`127702799170`, `127702798967`, `127702799958`)
содержат одинаковую конкретную причину:

> The job was not started because your account is locked due to a billing issue.

Это **подтверждённая блокировка запуска на стороне GitHub**, а не падение pytest:
checkout, установка зависимостей и тесты не выполнялись. Загрузка логов для
не начавшегося job вернула `404 BlobNotFound`. Статус CI —
`NOT_RUN_ACCOUNT_BILLING_LOCK`, не PASS.

Владельцу аккаунта нужно устранить блокировку в GitHub billing, после чего
повторить workflow. Платёжные настройки и лимиты этой публикацией не менялись.
Новые CI jobs сохраняют полный обязательный suite на Python 3.13 с численными
зависимостями и отдельно обозначают compatibility scope на 3.14.

## Архивная проверка 2026-11-01

Проверено 2026-11-01 после публикации commit
`ea52cd304a3544eee8a5d511c85c747ada2c0f0d` в `catman77/LivingMath`.
Локальная чистая установка:1074 PASS,12 прежних SKIP; реальный HTTPS/OAuth MCP
и повтор после перезапуска прошли. GitHub CI **не запускал тесты**.

## Наблюдаемые данные

| Проверка | Фактический результат |
|---|---|
| Actions permissions API | `enabled=true`, `allowed_actions=all`, `sha_pinning_required=false` |
| Наш workflow | ID403641107, `.github/workflows/test.yml`, name `Python checks`, state `active` |
| Первый push | [run41319519723](https://github.com/catman77/LivingMath/actions/runs/41319519723), `startup_failure`, jobs0 |
| Регистрация первого failure | ID403641130, path `BuildFailed`, пустое имя, state `deleted` |
| Явный workflow_dispatch | API принял запрос с HTTP204; [run41320090919](https://github.com/catman77/LivingMath/actions/runs/41320090919) относится к настоящему workflow, но также `startup_failure`, jobs0 |
| CI YAML (actionlint1.7.12) | `go run github.com/rhysd/actionlint/cmd/actionlint@latest -color=false .github/workflows/test.yml` — exit0 |
| Логи первого run | Download endpoint — HTTP404, jobs не созданы |
| Checks diagnostics API | HTTP403: `Resource not accessible by personal access token` |

Получение исходников, установка зависимостей и pytest на GitHub runner не
начинались. Этот результат нельзя объявлять падением pytest или успешным CI.
Обратное клонирование с GitHub подтвердило SHA всех621 опубликованных файлов.

## RCA и граница знания

Доказан отказ запуска до построения jobs. Синтаксическая ошибка workflow
локальным actionlint не обнаружена. Одного `startup_failure` недостаточно для
точного диагноза: возможны ограничения аккаунта, биллинга или платформенный
сбой запуска; доступной диагностики недостаточно, чтобы выбрать причину.

На GitHub Community имеются [сообщения владельцев репозиториев с похожим
BuildFailed/zero-jobs](https://github.com/orgs/community/discussions/211590).
Это аналогичный наблюдаемый случай, не подтверждение причины именно здесь.

Workflow сохранён активным, тесты и зависимости не ослаблены, не добавлены
скрытые retries или искусственный PASS. Не менялись видимость репозитория,
платёжные настройки, разрешения Actions или авторские исходники.

## Минимальный следующий шаг владельца

Открыть приведённый run в авторизованном GitHub UI и проверить доступное там
сообщение о старте, ограничения Actions/аккаунта и биллинга. Если UI не даёт
причины, передать GitHub Support repo, оба run ID и таблицу выше; при наличии
доступа приложить Checks annotations. Платёжные или security-настройки требуют
отдельного решения владельца. Обращение в поддержку автоматически не отправлялось.

До устранения внешнего отказа результат CI — `NOT_RUN_STARTUP_FAILURE`.
Локальный полный тестовый прогон воспроизводится по [TESTING.md](TESTING.md).
