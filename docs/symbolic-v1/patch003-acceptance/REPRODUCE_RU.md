# Воспроизведение приёмочного исправления

Кодовый commit `cb0dcb0`; база `974bc0a463b61b2480d8e71a00e69e12a3520936`. Исходный архив сохранён в `docs/LIVINGMATH_PATCH003_ACCEPTANCE_20261106.zip` без изменения (SHA256 `a455c6113284945b4ecfd23a41e00402eb8663747f4a62c613710d3b8c32fea9`). Три внутренних checksum проверены.

Delivery ZIP: `docs/LIVINGMATH_PATCH003_ACCEPTANCE_DELIVERY_20261106.zip`. Включает wheel, изменения исходников, полные production MCP request/response, data-only exports,942 замороженных катрена, полный source tree и исходные ошибки запуска. В нём нет приватной конфигурации production, SQLite или OAuth credentials.

После распаковки в новый каталог (Linux с Landlock ABI≥3, Python≥3.13, C++17):

```bash
python3.13 -m venv /tmp/lm-p003-accept
. /tmp/lm-p003-accept/bin/activate
python -m pip install './dist/lm_suti_assurance-0.4.4.dev0-py3-none-any.whl[white-star,mcp,test]'
python -m lm_suti_assurance white-star prepare
python -m pytest -p no:cacheprovider -c /dev/null --import-mode=importlib -q code/tests/test_patch003_acceptance.py
unshare -Urn python code/tools/symbolic_patch003_replay.py evidence/production-followup-qa/FIX-B-positive.zip
unshare -Urn python code/tools/symbolic_patch003_replay.py evidence/production-qa/sp-10.zip
python code/tools/symbolic_patch003_corpus_audit.py --frozen corpus-freeze --sources corpus-sources --output /tmp/corpus-tree.json
python code/tools/symbolic_patch003_research.py run --frozen corpus-freeze --output /tmp/acceptance-corpus-rerun
```

18 новых tests проверяются отдельно; полные320 source/wheel tests и1066 legacy tests запускались из полного checkout. Для legacy нужен рабочий каталог `live_math_mcp_prod` и `PYTHONPATH=.:../src`; дочерние процессы должны видеть legacy modules. В полном репозитории изменения восстанавливаются `source.patch` поверх указанной базы. Полный сервер устанавливается по README_QUICKSTART_RU.md и docs/INSTALL.md, без подмены данных из исследовательского ZIP.

Полные MCP-трассы — `evidence/production-followup-qa/transcript.json`, `evidence/production-qa/transcript.json`, `evidence/production-legacy-qa/transcript.json`; JSON-RPC wire не содержит HTTP Authorization headers. Манифест `SHA256SUMS.json` проверяет каждый включённый файл. Метки queries не входят в worker payload; отдельный label-holder используется только внешним оценщиком.

Старые PATCH003 exports в evidence проверены через реальный MCP с owner-approved immutable профилем. Для их автономного replay нужен отдельный venv с включённым wheel0.4.3: не подменяйте binding в ZIP и не смешивайте версии в одном окружении. Новый runtime не выполняет код из пакета.

Исторические19 run records из входного отчёта сохранены в исходном виде. Новые исправленные partial-complex summary получаются при новом request_key. `api_examples.json` содержит реальные принятые вызовы и отрицательные certificates; для своего проекта сначала зарегистрируйте datasets и используйте возвращённые refs.

В ChatGPT переподключите LivingMath по прежнему URL для обновления tools/list до83 инструментов. Для проверки выведенного признака вызовите white_star_symbolic_observer_verify с project/run_id/feature_id из result.json. Внешний release sign-off и universal-invariant claim не заявляются.
