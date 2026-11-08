# Проект интерфейса MCP — не действующий контракт

Кодовому агенту разрешено выбрать меньший обратно совместимый интерфейс, но не изменить смысл этих переключателей. Ниже — **предлагаемые** формы, не рабочие вызовы сервера до внедрения.

## Symbolic V1

Существующий `white_star_symbolic_explore(project,request_key,request)` может получить новое значение только для `request.search.strategy`:

```json
{"request":{"search":{"strategy":"frontier_argument_coverage_v1"}}}
```

Это фрагмент, НЕ полный запрос: обязательные `schema/source/algebra/segmentation/operators/observers/task/search` остаются. Возможный отдельный `search_summary`:

```json
{
  "search_policy": "frontier_argument_coverage_v1",
  "parameter_coverage": {"SPLIT": {"attempted_unique": 44, "applicable_known": 68, "status": "PARTIAL_PARAMETER_COVERAGE"}},
  "frontier_remaining": 24,
  "unexpanded_nontrivial": 7,
  "visited_parent_nodes": 12,
  "candidate_attempts": 72,
  "literal_observation_growth": 48,
  "structural_class_growth": 19,
  "global_exhaustion_proved": false
}
```

Числа только иллюстративные; **не выдумывать их в работающем сервисе**.

## Numerical White Star

Предпочтительнее **отдельный opt-in tool**, например `white_star_explore_v2`, поддерживающий `selection_policy="cat_distinction_tiebreak_v1"`, чтобы не менять существующие схемы 94 инструментов. При отдельном tool обязательны те же исходные request/source SHA, права на workspace, журнал, ресурсы, inspect/replay и отсечение чужих run refs.

```json
{
  "project": "my-research-project",
  "request_key": "opt-in-cat-distinction-001",
  "selection_policy": "cat_distinction_tiebreak_v1",
  "request": {"schema": "levinmas-white-star-request/1", "encoding": "<EXISTING_COMPLETE_ENCODING>", "atlas_profile": "cj_v1"}
}
```

Это **типовой фрагмент** для выбора режима, `encoding` здесь нарочно заменён строкой-заглушкой. Он НЕ пройдёт валидацию и НЕ предназначен для вызова до реализации. Агент должен дать работающий полный JSON для installed tool.

Новые поля лога candidate:

```json
{
  "view_id": 69,
  "arithmetic_signature": [2, 0, 3, 1, 1, 7],
  "source_bound_concept_pairs": [["concept1", "concept7"]],
  "alias_resolution": "UNAMBIGUOUS",
  "primary_topology_novelty": 9,
  "new_distinction": false,
  "selection_reason": "TIE_BREAK_OR_LEGACY",
  "counterfactual_only": false
}
```

Вся информация о понятиях считается **объявленной автором входной разметкой**, а не доказанной семантической истиной.

## MUST NOT

- Не добавлять `generate_theories`, `fit_scientific_hypothesis`, `find_truth`, `semantic_verifier` в tools.
- Не использовать названия `UNIVERSAL_COVERAGE` или `SEMANTICALLY_VERIFIED` для bounded structural outputs.
- Не подменять true dynamic selection простым post-hoc rerank старого `candidate_scores`.
