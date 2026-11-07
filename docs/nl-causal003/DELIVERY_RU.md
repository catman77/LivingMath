# Поставка NL-CAUSAL-003

[GitHub release v0.4.11-developer-preview](https://github.com/catman77/LivingMath/releases/tag/v0.4.11-developer-preview).
Полный файл поставки: `LIVINGMATH_NL_CAUSAL003_DELIVERY_20261107.zip`.

[Скачать ZIP](https://github.com/catman77/LivingMath/releases/download/v0.4.11-developer-preview/LIVINGMATH_NL_CAUSAL003_DELIVERY_20261107.zip).
Внутри: source.zip, source.patch, wheel, runtime manifest, ТЗ, отчёты,
протокол заморозки, исходные model receipts, полные MCP request/response/wire,
конечные контрмодели, snapshots17 фактических structural runs и offline replay.
`PACKAGE_CONTENTS.json` указывает source commit; `MANIFEST.sha256` покрывает байты
всех payload-файлов. Архив не содержит SQLite, OAuth credentials и private configs.

[Итог](USER_REPORT_RU.md), [машинные результаты](result.json),
[матрица проверок](TEST_MATRIX.json), [RCA](RCA_RU.md),
[точные вызовы и rollback](QUICKSTART_RU.md).

Предварительный результат: инженерная приёмка PASS; смысловое преимущество
White Star UNCONFIRMED, внешняя human adjudication HUMAN_NOT_EVALUATED.

## Подтверждённая публикация

Code/source commit: `e7b92a9ebb00055d9f2d96a44d66fdfc81c25df8`. Размер ZIP:86 390 583 bytes.
SHA-256: `47d2b247475a560e28bceed7b0c97dc9115646ef4f3b5ca37039e495b75d8610`.

Анонимное скачивание ZIP и1766 source blobs проверено: совпадение всех SHA.
[Квитанция](PUBLIC_READBACK.json), [проверка пакета](PACKAGE_VALIDATION.json),
[скан credentials](ASSET_SECRET_SCAN.json). История и БД сохранены.

GitHub Actions создали6 checks с failure до запуска заданий из-за account billing
lock; тесты в GitHub не исполнялись. Статус NOT_RUN_ACCOUNT_BILLING_LOCK,
не PASS. [Ответы checks/annotations](GITHUB_CI.json). Локальная и реальная MCP
приёмка завершены отдельно. Платёжные настройки не изменялись.
