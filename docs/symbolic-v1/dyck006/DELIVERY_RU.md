# DYCK006: опубликованная поставка

[Релиз v0.4.8-developer-preview](https://github.com/catman77/LivingMath/releases/tag/v0.4.8-developer-preview) ·
[Полный воспроизводимый ZIP](https://github.com/catman77/LivingMath/releases/download/v0.4.8-developer-preview/LIVINGMATH_DYCK006_DELIVERY_20261107.zip).

ZIP: 339467166 bytes, SHA256
`7bf66bfbe68d062fc57e71d3d6b5234d7c667977acab75fce2a5a150d4b13f3a`.
Source/tag: `62cc7b6f520bf7699ccb1ba3d31bffd007df007e`, base
`9d3062a8fb81687a67eb0ad8acf1b10425e76277`.
Проверены408 payload files,1522 Git blobs и113 runtime Python files;
из source ZIP восстановлен тот же код, что работает в production.
GitHub fresh clone совпадает с каждым опубликованным blob.

Внутри: полный source/patch, current/historical wheels, исходный архив ТЗ,
запечатанные входы и отдельный gold, все модели и8191 observations,
полные baseline/staged/public MCP request/response/wire пяти suites,
исходные RED/failed attempts, test logs/review, schemas и integrity receipts.
SHA каждого файла — SHA256SUMS.json. Приватные базы, configs, OAuth excluded;
recursive secret scan PASS (130 known values + credential patterns).

[Приёмка](USER_REPORT_RU.md), [команды и схемы](QUICKSTART_RU.md).
Production0.4.8, прежний URL, SQLite/старые runs/журналы сохранены.

GitHub Actions: все6 jobs остановлены до исполнения из-за billing lock аккаунта
(полный receipt GITHUB_CI.json). Это FAIL инфраструктуры CI; не успешный CI.
Локальные409/409 tests,1066 legacy/20SKIP,24 reference и настоящая HTTPS/OAuth
приёмка10780 checks на каждом endpoint задокументированы отдельно.

UNIVERSAL_INVARIANT=false; family UNDERDETERMINED; R3 PENDING.

Публичный ZIP заново скачан без credentials: размер и SHA256 точно совпадают
(GITHUB_ASSET_READBACK.json). Из распакованного source повторены24 targeted tests:
24 PASS после документированного native prepare с прежним бинарным SHA.
Первый запуск до prepare дал23PASS/1ENGINE_UNAVAILABLE; оба лога сохранены,
ошибка окружения не удалена и не объявлена успешным запуском.
