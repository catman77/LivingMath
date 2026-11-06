# Воспроизведение FIX-B2

Архив задания: `docs/LIVINGMATH_V044_REACCEPTANCE_20261106.zip`, SHA256 `0666b1f28defd727a003455888c24241d5143710558ca7dec6ec50f83676d318`. Проверены 4 внутренних checksums; входные документы сохранены без изменения.

Кодовый commit `8ef1293`; база `67b18d8562c75708983bd727215f8dd11129c5c6`. Delivery: `docs/LIVINGMATH_FIX_B2_DELIVERY_20261106.zip`; внутри wheel, patch, original16 source snapshots, frozen14/48 fixture, внешний label-holder, full MCP request/response, позитивный feature и REJECTED variants. Приватных SQLite, server config или OAuth credentials нет.

После распаковки (Linux/Landlock ABI≥3, Python≥3.13, C++17):

```bash
python3.13 -m venv /tmp/lm-b2
. /tmp/lm-b2/bin/activate
python -m pip install './dist/lm_suti_assurance-0.4.5.dev0-py3-none-any.whl[white-star,mcp,test]'
python -m lm_suti_assurance white-star prepare
python -m pytest -p no:cacheprovider -c /dev/null --import-mode=importlib -q code/tests/test_context_promotion.py
python code/tools/context_promotion_experiment.py --fixture fixed-fixture --output /tmp/fixb2-rerun
unshare -Urn python code/tools/symbolic_patch003_replay.py evidence/production-b2-qa/promoted-observer.zip
unshare -Urn python code/tools/symbolic_patch003_replay.py evidence/production-sp-qa/sp-10.zip
```

17 новых regression tests проверяются автономно; полные 337 source/wheel и 1066 legacy tests запускались из полного checkout. Для legacy используйте `cd live_math_mcp_prod` и `PYTHONPATH=.:../src python -m pytest -q .`, чтобы дочерние процессы видели legacy modules.

Для полной MCP-приёмки из репозитория используйте `tools/context_promotion_mcp_qa.py --help`. Публичный endpoint и loopback-staging проверяются настоящим SDK/OAuth. Если client-registration quota уже заполнена, `LIVINGMATH_QA_CLIENT_FILE` указывает на **существующий owner-only mode600** JSON от прежнего QA-входа. Выполняется новый обычный PKCE login/token flow с существующим client_id; серверные ограничения не меняются. Не включайте этот файл в exports или Git.

Все baselines используют одинаковые train/query/seed/search caps. `builtin_only` запрещает pair_0*, `builtin_all` является дополнительным unrestricted control. Majority и no-derivation здесь намеренно совпадают. Оценщик читает внешний файл меток после всех inference jobs; worker его не видит.

Старые run_id сохраняют прежние результаты. Для проверки исправления нужен **новый request_key**. В api_examples.json есть готовый запрос к исходным dataset refs проекта whitestar_dialog_test и реальный verifier request к новому принятому run в qa-fixb2-prod.

`SHA256SUMS.json` проверяет каждый файл delivery. Старый v0.4.4 observer экспортируется и воспроизводится через approved immutable profile того же сервера; для автономного replay используйте включённый wheel0.4.4 в отдельном venv. Код из data-only ZIP никогда не исполняется.
