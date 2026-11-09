# PATCH002 — воспроизведение

Установите wheel из проверенного delivery ZIP в отдельный Python3.13 venv с зависимостями из evidence/runtime-constraints.txt. Подготовьте native и выполните tests, не используя production data как тестовую базу.

```bash
python -m pip install '.[white-star,mcp,test]'
lm-suti white-star prepare
python -m pytest -q tests
lm-suti doctor --smoke
python docs/SEMANTIC_BRIDGE_PATCH002_20261109/fixtures/REFERENCE_VERIFY.py
```

Для установленного wheel, из папки вне checkout:

```bash
python -m pytest /path/to/source/tests -o pythonpath= -q
python /path/to/source/tools/semantic_bridge002_verify.py /path/to/ANALYSIS_BUNDLE.json --output /tmp/sb002-independent.json
python /path/to/source/tools/semantic_bridge001_replay.py /path/to/ANALYSIS_BUNDLE.json --expected-sha256 <SHA256_ПОЛНОГО_ФАЙЛА>
```

Файл, binding и result SHA должны соответствовать точному архивному wheel. Старые результаты не переписывайте, при mismatching binding replay должен отказать. Команды с `/path/to` и угловым SHA — шаблоны, замените своими путями/хешем.

Реальные MCP examples находятся в MCP_EXAMPLES.json; это полные принятые запросы с действительными QA refs. Для своего проекта предварительно assurance_project_new и formal_store(source/model), затем register/analyze/inspect/replay. source_ref не заменяйте одним текстовым хешем. При replay используйте выданные run_ref/result_sha256, inspect выгружайте все страницы с проверкой полного SHA. Все гипотезы/obligations остаются PROPOSED/OPEN.

Фактический runner требует --endpoint, --baseline (сохранённый tools/list), --historical (17 read-only historical bundles из пакета), --output (новая папка), --project (отдельный QA namespace), --tag (новые request keys). Для локального стенда добавьте --loopback. Не запускайте его в рабочем исследовательском проекте. Операторские воспроизводимые скрипты и точные команды находятся в пакете; приватные production backups/config не публикуются.

GitHub Actions отключён. Wheel/test/deployment выполняются локально; push/release только публикует уже проверенные файлы.
