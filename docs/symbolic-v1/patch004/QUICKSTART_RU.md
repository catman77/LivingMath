# PATCH004: запуск рекурсивного наблюдателя

Сервер `v0.4.6-developer-preview`, пакет `0.4.6.dev0`, 83 MCP tools.
Сначала `assurance_project_new`, затем `white_star_symbolic_dataset_store`
для train и queries. Dataset refs берите из ответа **своего** проекта.
Полные реальные вызовы — [api_examples.json](api_examples.json), актуальные
input/output schemas — [MCP_TOOL_SCHEMAS.json](MCP_TOOL_SCHEMAS.json).

В `white_star_symbolic_observer_synthesize` передайте обычный request с
`task.mode="context_relation_induction"`, своими train/predict refs,
`holdout_labels_visible=false`, `feature_policy.enabled_builtins=[]`,
`derive_relations=true`, а также:

```json
"promotion_policy": {
  "mode": "compositional_ast",
  "candidate_sources": ["derivation_trace", "source_run_id"],
  "max_ast_nodes": 32,
  "max_ast_depth": 8,
  "max_recursion_steps": 8,
  "max_tokens": 8,
  "max_train_witnesses": 256,
  "require_independent_checker": true
}
```

Это фрагмент request, не самостоятельный валидный вызов; полный request находится
в JSON-примере. Отсутствие `promotion_policy` сохраняет старый literal-context
маршрут. Для нового source-only пути укажите `request.source_run_id` настоящего
совместимого завершённого Symbolic V1 run и
`candidate_sources=["source_run_id"]`. Ссылка из другого проекта недопустима;
несовместимые train labels и kernel отклоняются. Новая source-ссылка без opt-in
получает `SOURCE_CANDIDATE_ROUTE_NOT_ENABLED`. Идентичные исторические ключи
возвращают оригинальную старую запись.

Из `white_star_symbolic_observer_inspect(view="model")` возьмите feature ID из
`used_feature_ids`; проверьте его через `white_star_symbolic_observer_verify`
с project/run_id/feature_id. Большие sections могут вернуть `artifact_ref`:
читайте все `view="artifact"` chunks, соедините декодированные base64 и проверьте
`artifact_sha256` перед JSON parsing. `CHECKED_INSTANCE` относится к конечному
свидетелю, не к универсальной истинности или смыслу текста.

Модель замораживается до queries. За пределом 8 токенов возвращается UNKNOWN с
`score=null`; family остаётся UNDERDETERMINED. Для effective ablation используйте
`derive_relations=false` или реальный ID feature/его parent в denylist.
Новый request key запускает новый build; старый ключ с другим payload отклоняется.

## Воспроизведение поставки

```bash
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install '.[white-star,mcp,test]'
lm-suti white-star prepare
python -m pytest -q tests
python tools/recursive_observer_experiment.py prepare \
  --source docs/LIVINGMATH_RECURSIVE_OBSERVER_PATCH004_20261106/fixtures \
  --fixture /tmp/patch004-fixture
python tools/recursive_observer_experiment.py run \
  --fixture /tmp/patch004-fixture --output /tmp/patch004-results
```

Каталоги результата должны быть новыми. Gold хранится отдельно от worker packet,
внешний scorer читает его после всех inference. Source-supplied AST — отдельный
контроль evaluator/checker, не открытие генератора. Для HTTPS/OAuth QA:
`python tools/recursive_observer_mcp_qa.py --help`; runner создаёт только новые
QA проекты и добавляет новый source-bridge run в исходный проект, старые записи
не изменяет. Credentials и рабочие SQLite в поставку не входят.

Экспорт PAL/COPY/SP можно перепроверить без сети:
`unshare -Urn .venv/bin/python tools/symbolic_patch003_replay.py <bundle.zip>`.
Для исторического bundle нужен утверждённый runtime той версии; новый checker
не переписывает старые hashes. Production setup и приватные owner manifests
описаны в [INSTALL.md](../../INSTALL.md); архив не содержит живой базы/секретов.
