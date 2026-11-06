# Ролевые программы: MCP и воспроизведение

Версия0.4.8,83 tools. Новые inputs только additive: mode=role_branching_ast,
role_max_tokens/role_max_cells/role_max_split_trials и optional query_id в observer_verify.
Старые required fields/output schemas/annotations сохранены. Literal/compositional
маршруты прежние; auto пробует ролевой catalog, если equality-кандидат не найден.

Сначала assurance_project_new, затем dataset_store для train и query-only records.
В synthesize передайте полный обычный request с enabled_builtins=[],derive_relations=true,
своими train/predict refs и следующим фрагментом promotion_policy:

```json
{"mode":"role_branching_ast","candidate_sources":["derivation_trace"],
 "max_ast_nodes":32,"max_ast_depth":8,"max_recursion_steps":8,
 "max_tokens":8,"max_train_witnesses":256,"max_runtime_ms":4000,
 "role_max_tokens":8,"role_max_cells":91,"role_max_split_trials":512,
 "require_independent_checker":true}
```

Полные реальные вызовы — api_examples.json, полная MCP-схема — MCP_TOOL_SCHEMAS.json.
Роли не задаются клиентским готовым AST: generator выводит ограниченные binding
alternatives из train alphabet и выбирает совместимую программу только по train.
Семейство остаётся UNDERDETERMINED; CHECKED_INSTANCE относится к finite execution.

Из inspect(view=model) возьмите used_feature_ids. Default observer_verify проверяет
весь train. Для одного query добавьте query_id из исходного query dataset:

```json
{"project":"my-project","run_id":"<actual run_id>",
 "feature_id":"<actual feature_id>","query_id":"<actual query record id>"}
```

Ответ содержит data.verification и data.certificate. Последний можно повторно
передать в optional certificate: server использует неизменяемый registered AST,
фактический query и независимый checker, не доверяет wrapper SHA или producer bit.
Положительный tree содержит обе children, роли, действительные SPLIT/CONCAT,
реконструкцию полными токенами и UTF8 lineage. Отрицательный certificate содержит
все interval cells и независимо проверяемое покрытие всех разрезов.
Schemas: ROLE_PROGRAM.schema.json, ROLE_CERTIFICATE.schema.json, types.ts.
Это data types, не разрешение на исполнение произвольного AST/кода.

Переименование слов с фиксированными ролями меняет язык. Совместное переименование
слов И role bindings сохраняет программу с точностью до переименования.
LITERAL_ROLE_SENSITIVE, covariance и NF_INVARIANT=false — разные контракты.

Для P1 явно задайте role_max_tokens=12; общий8-token equality scope не меняется.
Horizon6 требует конкатенаций до12 токенов. EPS уже допустим как tokens=[],text=""
с действительными source SHA/rights/edition; это не новый специальный placeholder.
За scope и при нехватке бюджета — UNKNOWN, а не False/CHECKED. Worker caps прежние.

## Команды

```bash
python -m pip install '.[white-star,mcp,test]'
lm-suti white-star prepare
python -m pytest -q tests
python tools/role006_mcp_qa.py --help
```

Три отдельные серии: --phase accept, --phase continuations, --phase edges;
--phase baseline предназначен для исходной0.4.7. Используйте новый tag/output
и новые QA namespaces. Frozen inputs/gold из delivery ZIP, source refs те же,
когда исходные datasets зарегистрированы в вашем проекте. Gold читается только
после inference; N+2 сравнивается с настоящими множествами суффиксов.
HTTP018_RESOURCE_BUSY/429 обрабатывается клиентским ожиданием и повтором тех же
байтов запроса; математические ошибки/другие429 не маскируются. Серверные caps
и авторизация не ослабляются. Credentials/рабочих баз в поставке нет.
