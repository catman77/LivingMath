# GitHub Actions: запуск пока заблокирован

## Подтверждённая причина на 2026-11-06

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
