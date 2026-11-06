# Опубликованная поставка PATCH005

[GitHub release](https://github.com/catman77/LivingMath/releases/tag/v0.4.7-developer-preview) · [единый ZIP](https://github.com/catman77/LivingMath/releases/download/v0.4.7-developer-preview/LIVINGMATH_PATCH005_DELIVERY_20261106.zip).

- ZIP:249056073 bytes,244 files; SHA256 `6b9b9da999e8a12492c14802d2d646755b9500b0eb24faaae5ce3efbf9f6cbce`.
- Полный source/tag commit `4c849e0864deef79e91e19fd966fc2c89e8b1ae3`, diff от `9ce8fc2bc9101a70e0204363fe05c04aade0054b`.
- Все244 файловых хеша и1443 Git blobs распакованного исходника совпали;
 110 Python файлов совпали с runtime. После распаковки19 новых тестов PASS,
 mixed30 proof повторён без сети: REPLAY_MATCH, journal PASS.
- Код/wheels/исходный архив ТЗ, frozen fixtures/external scorer, полный baseline/
 staged/public MCP request/response/wire, оригинальные snapshots, failures и RCA.
- Ни OAuth credentials/паролей, ни production SQLite/workspaces/approvals.
 Проверка100 известных секретных значений, PAT/private-key patterns и nested ZIP PASS.
- [Ресурсные издержки](RESOURCE_SUMMARY.json):CPU/RSS всех34 конечных inference runs;
 wall latency отдельно не измерялась и не выдается за метрику качества.

[Проверка упаковки](DELIVERY_VALIDATION.json), [проверка CI](GITHUB_CI.json).
GitHub Actions6 jobs не стартовали: account locked due to a billing issue.
385+385 локальных тестов и реальные MCP PASS не объявляются зелёным GitHub CI.

Хеш всего контейнера публикуется внешним sidecar/текстом release; контейнер
не содержит свою собственную checksum. Полные диагностические модели находятся
в evidence ZIP; их компактные stage summaries — в MODEL_SUMMARIES.json.

Публичный ZIP скачан после публикации:249056073 bytes, полный SHA256 совпал.
[GITHUB_ASSET_READBACK.json](GITHUB_ASSET_READBACK.json).
