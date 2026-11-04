# LivingMath × SUTI v0.1 — отчёт

**Проверенный developer-preview установлен на production. Финальный gate R3 ещё не закрыт.**

Архив запроса сохранён без изменения в docs. В изолированной release-ветке собран один assurance runtime: исходные verifier/binder сохранены побайтно; добавлены CLI, типизированные артефакты, отдельное подтверждение задачи, атомарный append-only журнал, права публикации и автономный replay. Новых математических операций, DSL, модельных прогонов и выдуманных результатов нет.

| Проверка | Результат |
|---|---|
| Новые тесты Python3.13 /3.14 |117/117 PASS на каждом|
| Старые assurance unit-тесты |50 PASS|
| Старый серверный набор |1066 PASS,20 SKIP,0 FAIL|
| Исторические фикстуры / полный003 replay |80 случаев /76 записей, прежние digest|
| Чистая установка и установка из offline wheelhouse |PASS|
| Реальный публичный HTTPS/OAuth MCP: staging /production |39/39 PASS на каждом|
| Прежние44 входные схемы + новые11 инструментов |сохранены /доступны, всего55|
| Экспорт последних6 кандидатов, включая новые HOLD |PASS, оба evaluator совпали|
| Сохранность исходных canonical/typed/DAV строк и inode |PASS|
| Два внешних технических replay |PENDING, получено0 отчётов|

Production: `v0.1.0-developer-preview`; deployment `release-v01-20261104T181130Z`. Manifest `18dc44612d34488cc5a2e40919b54ddd37984bdef1c8d501a1285ff21d9419fc`. Endpoint:

https://fares-september-rebel-board.trycloudflare.com/mcp

В ChatGPT переподключите MCP-приложение к этому URL: прежний quick-tunnel адрес больше не работает. Первый вызов — `assurance_contract`, затем `assurance_doctor`. Owner OAuth и текущий пароль сохранены; секреты в поставку не включены. Доступ реального MCP SDK к55 инструментам проверен; обновление кэша схем именно вашего приложения ChatGPT требует переподключения.

Сохранены2058 основных и2072 typed событий,769 основных обязательств,983 записи основной истории статусов. Основная audit chain:4817 записей, прежний head `c9c0048be5cc2e782cb2f2377da524e5ad04303d86b65792ef1d503b8c1c3d50`. До переключения сделаны4 SQLite BackupAPI копии; дополнительно перед переключениями — согласованные копии при остановленном HTTP. Все резервные копии и предыдущие deployment/drop-in сохранены приватно. Замена баз и переписывание истории не выполнялись.

Ручной путь: `README_QUICKSTART_RU.md`. Одна проверка после установки: `lm-suti doctor --smoke`. Для независимых участников подготовлены `pilots/source-projection.zip`, `pilots/finite-counterexample.zip`, `pilots/bounded-invariant.zip` и форма `docs/release-v01/EXTERNAL_PILOT_FORM.md`. Каждый кейс содержит принятый, отклонённый и HOLD результат с причиной. Автоматические измерения не выданы за время/действия человека.

Состояние: **R0/R1/R2 PASS; R4 technical PASS; R3 и final release admission PENDING.** Это отражено и в metadata production. Чтобы назвать релиз финально принятым по приложенной roadmap, нужны два настоящих внешних replay-отчёта. Исходный сервер заменён по прямому распоряжению владельца, но это не отменяет отсутствующее свидетельство.

Native SUTI: NOT_EXECUTED; formal kernel: UNAVAILABLE_NOT_REGISTERED. CHECKED_FINITE ограничен объявленным полным конечным классом, SOURCE_ATTESTED — исходными полями/проекцией, UNKNOWN/HOLD не означает опровержение. Во всех новых решениях execution_permission=false; модель не присваивает verified.

Полные MCP JSON сообщения, включая отрицательные ответы: `mcp/production/`; фиксация всех6 кандидатов — `final-export-*`. Токены OAuth и HTTP Authorization не записаны. Список файлов: `CHANGED_FILES.json`; проверки SQLite/строк: `INTEGRITY_AFTER.json`; причины и границы: `RCA.md`. GitHub origin подтверждён как пустой публичный R-Commons/LivingMath; в этой задаче публикация туда не выполнялась.
