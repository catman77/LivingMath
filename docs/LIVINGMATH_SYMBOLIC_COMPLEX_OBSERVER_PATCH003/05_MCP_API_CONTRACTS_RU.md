# Предлагаемые новые MCP-контракты (не установлены)

Версия контрактов в этом ТЗ: `livingmath-symbolic-complex-request/1`, `livingmath-symbolic-observer-synthesis-request/1`. Имена endpoints рекомендательные, но совместимость и структура данных обязательны. Схемы ниже — минимальный **смысловой контракт**, который кодовый агент уточнит под реальный валидатор сервера; не регистрировать фальшивый endpoint без реализации.

## 1. `white_star_symbolic_complex_analyze`

**Request:**

```json
{
  "project": "whitestar_dialog_test",
  "request_key": "complex-sp-10-v1",
  "request": {
    "schema": "livingmath-symbolic-complex-request/1",
    "complex_source": {
      "kind": "sp_balanced_fixture",
      "max_length": 10,
      "rewrite_rules": ["SP_TO_EMPTY", "PS_TO_EMPTY"],
      "edge_identity": "source_position_rule"
    },
    "cells": {"policy": "all_local_peaks", "join_depth_limit": 1},
    "analysis": ["graph_cycles", "homology_F2", "path_coherence", "pi1_certificate"],
    "budgets": {"max_vertices": 500, "max_edges": 2500,
                "max_cells": 5000, "max_cpu_ms": 4000}
  }
}
```

Альтернативный источник для P1: `{"kind":"saved_symbolic_history","project":"...","run_id":"<64hex>","only_verified_edges":true}`. Он не должен внезапно расширяться до всех слов языка.

**Response:**

```json
{
  "schema": "livingmath-symbolic-complex-response/1",
  "ok": true,
  "status": "COMPLETED",
  "data": {
    "engine": "symbolic_complex_v1",
    "run_id": "<64hex>",
    "result_digest": "<64hex>",
    "summary": {
      "vertices": 351, "edges": 1614, "components": 1,
      "graph_beta1": 1264, "local_peaks": 3360,
      "verified_cells": 3360,
      "rank_d2_F2": 1264, "dim_H1_F2": 0,
      "pi1_status": "PROVED_TRIVIAL_WITH_CERTIFICATE",
      "pi1_basis": "based_at_empty_word",
      "assumptions": ["all_local_peaks_filled", "terminating_SP_rewriting"]
    },
    "artifacts": {
      "vertices_ref": "<hash>", "edges_ref": "<hash>",
      "cells_ref": "<hash>", "homology_ref": "<hash>",
      "path_coherence_ref": "<hash>", "manifest_ref": "<hash>"
    }
  }
}
```

В P0 `summary.pi1_status` может быть `NOT_PROVED`; при любом `cells.policy=none` и N≥4 не возвращать `PROVED_TRIVIAL_WITH_CERTIFICATE`. `result_digest` вычислен из канонических данных, не из времени выполнения.

## 2. `white_star_symbolic_complex_inspect` и `white_star_symbolic_complex_verify`

`inspect` пагинирует `summary | vertices | edges | peaks | cells | homology | paths | diagnostics | manifest | export | artifact`. Ответ всегда содержит `total,next_offset,requires_artifact,artifact_ref` и bounded page. При больших объектах — private data-only artifact chunks, **не** молчаливое усечение.

`verify` принимает `project`, `run_id` и `certificate_ref` (или строго ограниченный typed certificate), проверяет источник/тип/права/версию и независимо воспроизводит `∂1∂2=0`, rank, локальные края и DAG path-coherence. Результат: `CHECKED_INSTANCE` / `REJECTED` / `NOT_PROVED` с точными failed obligations. Не использовать LLM как trusted verifier.

## 3. `white_star_symbolic_observer_synthesize`

**Request:**

```json
{
  "project": "whitestar_dialog_test",
  "request_key": "observer-grammar-v1",
  "request": {
    "schema": "livingmath-symbolic-observer-synthesis-request/1",
    "source_run_id": "<64hex optional>",
    "task": {
      "mode": "context_relation_induction",
      "train_ref": "<private dataset-ref>",
      "predict_ref": "<sealed queries-only-ref>",
      "holdout_labels_visible": false,
      "structure_levels": ["word", "line", "quatrain", "century"],
      "candidate_transformations": ["SWAP_LINES_2_3"]
    },
    "feature_policy": {
      "enabled_builtins": ["literal", "alpha_pattern", "adjacency"],
      "prohibit_undocumented_builtins": true,
      "synthesis_origin_required": true,
      "renaming_scope": "per_variant",
      "strict_source_boundaries": true
    },
    "search": {"seed": 137, "max_composition_depth": 4,
               "max_proposals": 128, "max_contexts": 256,
               "max_witnesses": 512, "max_cpu_ms": 4000}
  }
}
```

Правило не должно быть рождено лишь как дескриптор `{'name':'new_invariant'}`. Система возвращает исполняемый `rule_ast`, операторные зависимости, provenance, train witnesses / counterexamples, список конкурентов, контроль feature-ablation, seal digest замороженной гипотезы. Для прогнозов — значения `PREFERENCE | TIE | NOT_IDENTIFIABLE | UNDERDETERMINED` плюс `pair_id`, `observed_difference_witness`, без истинных test labels.

**Пример отдельной записи признака:**

```json
{
  "feature_id": "pair_0_max",
  "origin": "BUILTIN",
  "semantic_type": "finite_word_observer",
  "source_code_binding_sha256": "<64hex>",
  "required_observers": ["<actual runtime dependencies>"],
  "construction_trace": null,
  "derived_claim_allowed": false
}
```

Если признак действительно выведен из операций, вместо этого `origin=DERIVED_FROM_OPERATORS`, валидированный `operator_ast`, `proof_or_trace_ref`, `parent_feature_refs`, `execution_verified=true`.

## 4. Совместимость

Обязателен `bridge_system_status` с обоими новыми точными capability flags, versions, limits, worker readiness, proof boundary; если P1 недоступен, его статус `NOT_IMPLEMENTED`, а не `READY`. Старые `symbolic_v1` и численные endpoints/exports остаются доступными. Все ошибки содержат код, field_path, run_id|null; неизвестные или несовместимые модели -> `UNSUPPORTED_MODEL`, а не silent fallback.

## 5. Безопасность

- Источники подаются через registered projects, обычный source hash + explicit rights.
- Внутри worker no network, no credentials, no uncontrolled filesystem writes, no eval/dynamic Python.
- Все new algorithms останавливаются по CPU/wall/memory и пользовательским bounded budgets.
- Проверять циклические ссылки в uploaded graph и source span bounds; не материализовать опасные вложенные data payloads без ограничений.
- Экспорт только data-only; replay перепроверяет exact kernel/ops versions, source digests, proof/checks; чужой private project недоступен.
