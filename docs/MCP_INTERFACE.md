# MCP-интерфейс LivingMath v0.4.5

Актуальная production-композиция: **83 инструмента**, версия сервера
`v0.4.5-developer-preview`, пакет `0.4.5.dev0`. [Архитектура](../ARCHITECTURE.md),
[установка и различия 44/83](INSTALL.md), [исходный текст и rights](USAGE.md).

## Транспорт и обнаружение

Endpoint — `https://<origin>/mcp`, протокол **MCP Streamable HTTP**, OAuth/PKCE.
Работающий экземпляр использует origin
`https://fares-september-rebel-board.trycloudflare.com`; адрес не зашит в ядро.
Точный HTTPS origin задаётся оператором. Он должен совпасть с issuer/resource и
публичным адресом клиента, включая порт, без дополнительного path.

Сначала клиент проходит OAuth discovery/registration/owner login/token exchange,
MCP `initialize`, `notifications/initialized`, затем `tools/list` и `tools/call`.
В последней реальной приёмке согласован `protocolVersion=2025-11-25`.
Позвольте SDK согласовать версию; не отправляйте запросы как отдельный REST API.
`tools/list` при наличии `nextCursor` нужно дочитать до конца.

Первый вызов через уже инициализированный MCP-клиент:

```json
{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
```

```json
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"bridge_system_status","arguments":{}}}
```

Ответ `bridge_system_status` содержит установленную версию, deployment ID,
количество методов, readiness, kernel bindings и реальные ограничения.
`service_health` проверяет состояние хранилищ. `READY` не регистрирует проект и
не доказывает эффективность исследования.

Полные input/output schemas, описания и annotations всех методов:
[MCP_TOOL_SCHEMAS.json](symbolic-v1/v044-reacceptance/MCP_TOOL_SCHEMAS.json).
Это неизменённый ответ настоящего production `tools/list` из последней приёмки,
не схема, восстановленная из описания. Для конкретного подключения приоритет
имеет его текущий `tools/list`. При закешированном старом наборе обновите
подключение по тому же URL; публикация GitHub сама по себе не требует restart.

## Слои регистрации

| Группа | Количество | Где реализована |
|---|---:|---|
| Legacy research/ledger/cycles | 27 | `live_math_mcp_prod/mcp_server.py`, `production020.py`, engine/native/typed модули |
| DAV | 8 | `live_math_mcp_prod/davcore/mcp.py` |
| Автоматический цикл | 4 | `live_math_mcp_prod/research_automation/server.py` |
| Bridge и источниковые схемы | 5 | `live_math_mcp_prod/unified_system/server.py` |
| Finite assurance | 11 | `src/lm_suti_assurance/mcp.py` |
| Semantic Bridge | 9 | `src/lm_suti_assurance/semantic_bridge/mcp.py` |
| Численная White Star и сравнение | 8 | `src/lm_suti_assurance/white_star/mcp.py` |
| Symbolic V1 | 3 | `src/lm_suti_assurance/symbolic/mcp.py` |
| SP-комплексы, dataset/observer, replay | 8 | `src/lm_suti_assurance/symbolic_complex/mcp.py` |
| **Всего** | **83** | `tools/release_v01_entry.py` объединяет регистрации |

## Проекты, запросы и разрешения

- Для assurance/Semantic/White Star/Symbolic сначала создайте проект через
  `assurance_project_new`. Project slug: `^[a-z][a-z0-9_-]{0,63}$`. Legacy
  проекты имеют собственную схему; одинаковое имя не объединяет namespaces.
- Обязательность `request_key` определяется точной схемой метода. Большинство
  новых мутаций требует его; `white_star_validate_model` использует внутренний
  структурный digest вместо публичного ключа. Для операций с request key
  одинаковый повтор возвращает сохранённый результат; другое содержимое под
  старым ключом отклоняется.
  Повтор старого run после обновления не является новым вычислением.
- `run_id`, `source_ref`, dataset refs и `bundle_ref` берутся из реального ответа
  того же проекта. SHA не является разрешением читать объекты другого проекта.
- Legacy HTTP018 запрещает клиентские `transition_research_move` с действиями
  `activate_experiment` и `complete`: `018_OPERATOR_AUTHORITY_REQUIRED`.
  Эти действия доступны отдельному операторскому пути, хотя аргументы видны в
  общей схеме. Audit/proposal не выдаёт execution grant.
- `COMPLETED` относится к lifecycle/workflow, `CHECKED_INSTANCE` — к конечному
  сертификату, `SOURCE_ATTESTED` — к байтам/полям источника. Ни один из них не
  удостоверяет смысл текста или физическую применимость. Native SUTI не запущен.

## Минимальный новый конечный запуск

Ниже точные `params` для двух отдельных `tools/call`. Это новый QA-проект:

```json
{"name":"assurance_project_new","arguments":{"project":"my-symbolic-qa","request_key":"project-init-1"}}
```

```json
{
  "name":"white_star_symbolic_complex_analyze",
  "arguments":{
    "project":"my-symbolic-qa",
    "request_key":"sp2-first-1",
    "request":{
      "schema":"livingmath-symbolic-complex-request/1",
      "complex_source":{"kind":"sp_balanced_fixture","max_length":2,"rewrite_rules":["SP_TO_EMPTY","PS_TO_EMPTY"],"edge_identity":"source_position_rule"},
      "cells":{"policy":"all_local_peaks","join_depth_limit":1},
      "analysis":["graph_cycles","homology_F2","path_coherence","pi1_certificate"],
      "budgets":{"max_vertices":16,"max_edges":32,"max_cells":32,"max_cpu_ms":4000}
    }
  }
}
```

Сохраните возвращённый `run_id` и передайте его в
`white_star_symbolic_complex_inspect`/`white_star_symbolic_complex_verify` с тем же
project. Это проверка заданного конечного SP-комплекса, не произвольного текста.

Для синтеза наблюдателя сначала сохраните отдельные train и queries datasets
через `white_star_symbolic_dataset_store`, затем передайте их issued refs в
`white_star_symbolic_observer_synthesize`. Queries не содержат меток. Гипотеза
замораживается после train; provenance, AST и реальные зависимости читаются через
`white_star_symbolic_observer_inspect`. Проверка конкретного feature —
`white_star_symbolic_observer_verify`.
[Полные принятые запросы FIX-B2](symbolic-v1/v044-reacceptance/api_examples.json),
[валидный feature](symbolic-v1/v044-reacceptance/VALID_DERIVED_FEATURE.json),
[ответ независимого verifier](symbolic-v1/v044-reacceptance/CHECKED_INSTANCE.json).

## Входы с текстом и точные rights

| Инструмент/контракт | Где брать валидный вход |
|---|---|
| `research_autonomy_ingest`, `livingmath-artifact/1`, `typed008/1` | [Готовый observer012 запрос](examples/research_autonomy_ingest.observer012-public-domain.json); rights содержит `basis`, `origin`, optional `attribution` |
| `assurance_source_add` | `assurance_contract.source_snapshot_schema`; snapshot и publication policy передаются JSON-строками |
| `semantic_source` | `semantic_contract`: edition metadata, source_ref и отдельное scope review |
| `white_star_explore` | `white_star_status` и [численный пример](LEVINMAS_WHITESTAR_MCP_001/fixtures/original_request.json): явные encoding и source byte spans |
| `white_star_symbolic_explore` | [Точный symbolic request](LIVINGMATH_SYMBOLIC_V1/fixtures/mcp_request_example.json): буквальные токены и source carrier |

Rights разных контрактов не взаимозаменяемы. Объект raw-text rights:

```json
{"basis":"PUBLIC_DOMAIN","origin":"Автор, произведение, источник и основание public domain","attribution":"Автор"}
```

Это декларация вызывающего, не юридическая сертификация. Не заменяйте её
`license`, `public_domain`, `holder` или rights-строкой другого API.
[Полная схема и ошибки валидации](examples/rights.schema.json).

## Ответы, большие результаты и ошибки

В MCP читайте `isError` и `structuredContent`; текстовые content blocks могут
содержать тот же JSON. Legacy/assurance и White Star используют разные payload
контракты — единой универсальной business-envelope схемы нет. Например, extensions
используют `livingmath-symbolic-extension-response/1` с `ok`, `status`, `data`
либо `error`, `execution_permission=false`.

Inspect возвращает страницы с `next_offset`. При `requires_artifact=true`
прочитайте все artifact chunks и проверьте SHA. Data-only export/replay использует
`bundle_ref` того же проекта. В автономной legacy истории поля пагинации иные:
`after_record_id`, `byte_offset`; [порядок сборки](USAGE.md).

| Ошибка/статус | Действие клиента |
|---|---|
| `PROJECT_NOT_FOUND` или project-level `NOT_FOUND` | Создать assurance-проект перед новым White Star/Symbolic запуском; проверить namespace |
| `REQUEST_CONFLICT` / `REQUEST_KEY_CONFLICT` | Восстановить прежний payload либо использовать новый ключ |
| `INVALID_REQUEST` / schema field path | Сверить JSON со схемой именно этого инструмента |
| `WORKER_LIMIT` | Сохранить отрицательный run; уменьшить конечный срез/бюджет, не объявлять отсутствующий результат |
| `NO_VERIFIABLE_NEW_OBSERVER` | Прочитать failed obligations: это отсутствие принятого feature |
| `UNKNOWN` / `UNDERDETERMINED` | Сохранить неизвестность; дополнительные данные не заменять предположением о доказанности |
| `KERNEL_BINDING_UNAVAILABLE` | Нужен установленный оператором immutable профиль, а не код из ZIP |
| `MODEL_UNAVAILABLE` | Hosted proposer недоступен; deterministic/manual/replay пути отделены |

## Полный перечень методов

Ниже имя и обязательные поля верхнего уровня из реального schema snapshot.
Optional поля, defaults, enum, limits и вложенные типы находятся в полном JSON
Schema выше; список обязательных полей не заменяет валидацию. Назначение каждой
операции опубликовано в её `description` в том же snapshot.

### Legacy research, ledger и cycles

| Метод | Обязательные arguments |
|---|---|
| `research_context` | `project` |
| `research_focus_candidates` | `project` |
| `audit_research_shift` | `project` |
| `research_frontier` | `project` |
| `research_obligation_history` | `project`, `obligation_id` |
| `research_move_history` | `project`, `move_id` |
| `propose_research_policy` | `code`, `content` |
| `service_health` | Нет |
| `research_normalize_preview` | `project`, `focus`, `source_event_ids`, `query_scope` |
| `research_native_preview` | `project`, `active_frontier_id`, `active_frontier_version`, `source_event_ids`, `source_adapter_id`, `source_bindings`, `observer`, `question` |
| `record_result` | `project`, `kind`, `focus`, `result` |
| `record_research_move` | `project`, `move`, `request_key` |
| `transition_research_move` | `project`, `move_id`, `action`, `request_key` |
| `audit_research_move` | `project`, `move_id`, `request_key` |
| `research_obligation_create` | `project`, `statement`, `scope`, `source_event_ids` |
| `research_obligation_update` | `project`, `obligation_id`, `expected_version`, `changes` |
| `record_transformation_contract` | `project`, `source`, `operation`, `result`, `preservation`, `source_event_ids` |
| `attend` | `project`, `focus`, `reason` |
| `interpret` | `project`, `focus`, `claim` |
| `research_cycle_preview` | `request` |
| `research_cycle_precommit` | `request`, `request_key` |
| `research_cycle_validate` | `project`, `move_id`, `event_id` |
| `research_novelty_snapshot` | `request` |
| `research_cycle_next` | `query` |
| `research_cycle_history` | `project` |
| `research_source_contract` | `project` |
| `research_contract` | Нет |

### DAV

| Метод | Обязательные arguments |
|---|---|
| `dav_register_adapter` | `project`, `spec`, `request_key` |
| `dav_observe` | `project`, `registration_id`, `adapter_binding`, `states` |
| `dav_check_law` | `project`, `registration_id`, `adapter_binding`, `formula` |
| `dav_generate_candidates` | `project`, `registration_id`, `adapter_binding` |
| `dav_reduce_library` | `project`, `registration_id`, `adapter_binding` |
| `dav_find_counterexample` | `project`, `registration_id`, `adapter_binding`, `formula` |
| `dav_audit_adapter` | `project`, `registration_id`, `adapter_binding` |
| `dav_export_evidence` | `project`, `evidence_id` |

### Автоматический цикл

| Метод | Обязательные arguments |
|---|---|
| `research_autonomy_ingest` | `project`, `source`, `request_key` |
| `research_autonomy_status` | `project` |
| `research_autonomy_control` | `project`, `case_id`, `action`, `request_key` |
| `research_autonomy_history` | `project`, `case_id` |

### Bridge

| Метод | Обязательные arguments |
|---|---|
| `bridge_system_status` | Нет |
| `bridge_catalog` | Нет |
| `bridge_inspect` | `source_id` |
| `bridge_validate_records` | `source_id` |
| `bridge_run_alchemy` | Нет |

### Finite assurance

| Метод | Обязательные arguments |
|---|---|
| `assurance_contract` | Нет |
| `assurance_project_new` | `project`, `request_key` |
| `assurance_source_add` | `project`, `snapshot_json`, `publication_policy_json`, `request_key` |
| `assurance_task_import` | `project`, `artifact_json`, `request_key` |
| `assurance_task_review` | `project`, `task_ref`, `actor`, `reason`, `request_key` |
| `assurance_candidate_import` | `project`, `artifact_json`, `request_key` |
| `assurance_check` | `project`, `candidate_ref`, `request_key` |
| `assurance_report` | `project` |
| `assurance_export` | `project`, `audience` |
| `assurance_replay` | `bundle_base64` |
| `assurance_doctor` | Нет |

### Semantic Bridge

| Метод | Обязательные arguments |
|---|---|
| `semantic_contract` | Нет |
| `semantic_source` | `project`, `source_ref`, `metadata_json`, `actor`, `reason`, `request_key` |
| `semantic_draft` | `project`, `edition_ref`, `request_key` |
| `semantic_revise` | `project`, `frame_ref`, `challenge`, `request_key` |
| `semantic_compare` | `project`, `left_ref`, `right_ref`, `projection_json`, `request_key` |
| `semantic_report` | `project` |
| `semantic_withdraw` | `project`, `frame_ref`, `reason`, `request_key` |
| `semantic_export` | `project` |
| `semantic_replay` | `project`, `bundle_ref` |

### Численная White Star и сравнение

| Метод | Обязательные arguments |
|---|---|
| `white_star_status` | Нет |
| `white_star_explore` | `project`, `request_key`, `request` |
| `white_star_inspect` | `project`, `run_id` |
| `white_star_record_interpretation` | `project`, `run_id`, `request_key`, `readings` |
| `white_star_validate_model` | `project`, `run_id`, `proposal` |
| `semantic_compare_runs` | `project`, `left`, `right`, `protocol` |
| `semantic_run_frozen` | `project`, `request_key`, `common_snapshot_ref` |
| `white_star_replay` | `project`, `bundle_ref` |

### Symbolic V1

| Метод | Обязательные arguments |
|---|---|
| `white_star_symbolic_explore` | `project`, `request_key`, `request` |
| `white_star_symbolic_inspect` | `project`, `run_id` |
| `white_star_symbolic_replay` | `project`, `bundle_ref` |

### SP-комплексы и observer synthesis

| Метод | Обязательные arguments |
|---|---|
| `white_star_symbolic_complex_analyze` | `project`, `request_key`, `request` |
| `white_star_symbolic_complex_inspect` | `project`, `run_id` |
| `white_star_symbolic_complex_verify` | `project`, `run_id` |
| `white_star_symbolic_dataset_store` | `project`, `request_key`, `dataset` |
| `white_star_symbolic_observer_synthesize` | `project`, `request_key`, `request` |
| `white_star_symbolic_observer_inspect` | `project`, `run_id` |
| `white_star_symbolic_observer_verify` | `project`, `run_id`, `feature_id` |
| `white_star_symbolic_extension_replay` | `project`, `bundle_ref` |
