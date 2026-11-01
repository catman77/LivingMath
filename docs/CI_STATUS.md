# GitHub Actions: запуск пока заблокирован

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
