# Поставка PATCH004

[GitHub release v0.4.6-developer-preview](https://github.com/catman77/LivingMath/releases/tag/v0.4.6-developer-preview)
содержит единый [воспроизводимый ZIP](https://github.com/catman77/LivingMath/releases/download/v0.4.6-developer-preview/LIVINGMATH_PATCH004_DELIVERY_20261106.zip).

- SHA256: `9fcb0334f6ea8f72a8e43d37fab9e3cb1325886f3947100350000488e45062e5`; 154364857 bytes;248 файлов с отдельными хешами.
- Полный source snapshot/tag: `54071e5e6114187fcdf643f3c340b8e6d12c0957`; базовый commit `095e4f1071447e4333c0a416d66bc1c3a66cf062`.
- Source diff,0.4.6 wheel и отдельный исторический0.4.5 wheel, неизменённый архив ТЗ,
  frozen inputs/внешний scorer, полные MCP request/response и wire:по360 tools/call в каждом
  финальном staged/public прогоне, первый partial harness-attempt и исходные RED logs.
- Все248 hashes и1378 Git blobs распакованного snapshot совпали.110 Python файлов
  совпали с установленным runtime. После распаковки29 новых регрессий PASS;
  PAL и исторический0.4.5 replay без сети — REPLAY_MATCH, hash-chain PASS.
- Токены/пароли/рабочие базы исключены; проверены84 известных секретных значения,
  PAT/private-key patterns и вложенные ZIP. Сам runtime/исследовательские данные
  из production не заменяются при распаковке архива.

Внешний SHA контейнера и окончательная проверка распаковки находятся рядом с
архивом в репозитории; контейнер не содержит свою собственную контрольную сумму.
Смотрите [DELIVERY_VALIDATION.json](DELIVERY_VALIDATION.json),
[GITHUB_READBACK.json](GITHUB_READBACK.json), [GITHUB_CI.json](GITHUB_CI.json).

GitHub Actions на этом commit:6 jobs получили failure **до запуска тестов**:
“The job was not started because your account is locked due to a billing issue.”
Локальные тесты/реальная MCP-приёмка прошли; это не объявляется зелёным GitHub CI.
Для использования нового optional promotion_policy при старой закешированной
схеме ChatGPT обновите существующее подключение MCP по тому же URL.

Публичный asset скачан после публикации:154364857 bytes, точное совпадение SHA256.
[GITHUB_ASSET_READBACK.json](GITHUB_ASSET_READBACK.json).
