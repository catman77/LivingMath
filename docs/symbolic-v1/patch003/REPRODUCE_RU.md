# Воспроизведение PATCH003

Исходный код: commit18919801e44c92402ca386f2733efb785fe394cb; предыдущая база dcb18662582644e33d62533304d010fe6e323a15. Runtime layer состоит из193 SHA-bound файлов;192 соответствуют исходникам репозитория, ещё один — native `.so`, скомпилированный из неизменённых численных исходников. Манифест находится в `release_manifest.json`.

Локальный delivery ZIP: `docs/LIVINGMATH_SYMBOLIC_PATCH003_DELIVERY_20261106.zip`. Он содержит полный wheel, исходный diff/изменённые файлы, замороженные942 катрена, отдельный файл внешних меток, все13 результатов и production MCP-трассы. Приватных баз, конфигурации сервера и OAuth credentials в нём нет. Архив ТЗ сохранён отдельно без изменения.

После распаковки ZIP в новый каталог:

```bash
python3.13 -m venv /tmp/lm-p003-replay
. /tmp/lm-p003-replay/bin/activate
python -m pip install './dist/lm_suti_assurance-0.4.3.dev0-py3-none-any.whl[white-star,mcp,test]'
python -m lm_suti_assurance white-star prepare
python -m pytest -c /dev/null --import-mode=importlib -q code/tests
unshare -Urn python code/tools/symbolic_patch003_replay.py evidence/production-qa/sp-10.zip
unshare -Urn python code/tools/symbolic_patch003_replay.py evidence/production-qa/dyck.zip
unshare -Urn python code/tools/symbolic_patch003_replay.py evidence/production-qa/corpus-global-alpha.zip
python code/tools/symbolic_patch003_research.py run --frozen corpus-freeze --output /tmp/patch003-research
```

Требуются Linux с Landlock ABI≥3, C++17 compiler и Python≥3.13. Тесты из ZIP проверяют30 новых случаев; полные302 и1066 legacy запускаются из репозитория. Ограничения CPU/RAM действуют и во время replay.

Для работы с полным деревом примените `source.patch` к указанной базовой ревизии либо checkout кодового commit. Инструкции установки полного сервера: `README_QUICKSTART_RU.md` и `docs/INSTALL.md` в репозитории. Production private config и базы никогда не восстанавливайте из исследовательского ZIP.

`SHA256SUMS.json` проверяет каждый включённый файл. Перед inference протокол проверяет digest train/query и запечатанных меток; оценщик открывает метки только после завершения всех inference jobs. Для сравнения используйте integer wins/losses/ties/abstentions и `RESULTS.csv`, не трактуйте random tie credit как измеренный успех.

Полные MCP request/response: `evidence/production-qa/transcript.json` и `evidence/production-legacy-qa/transcript.json`; wire — JSON-RPC messages без HTTP/OAuth headers. Ранний неполный staging-прогон и исходные ошибки сохранены в `evidence/development-attempts/`; они не засчитаны в PASS. Любое новое исследование выполняйте в новом QA-проекте; исходные RH/Soft FTL данные не используются как тестовый мусор.
