# API и сертификаты: предложение (не установленные в продакшне команды)

Контракты ниже — **целевые**. Реальные актуальные команды v0.4.5 остаются доступными. Изменения не нарушают существующие required properties.

## 1. Аддитивная опция в `white_star_symbolic_observer_synthesize`

Предлагается добавить в `request` **необязательное** поле:

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

Необязательное отсутствие `promotion_policy` сохраняет поведение предыдущей версии (`literal_context_only` или текущий default). `max_train_witnesses` — лимит **новой** ветки; не переписывать нынешний `FINITE_SHORT_WORD_SCOPE_REQUIRED` prototype-mode. Нестандартный candidate route из `source_run_id` разрешён лишь при совпадении project и pinned training input digest.

Все значения bounded; сервер валидирует с реальными worker limits и возвращает `RESOURCE_LIMIT` при превышении. `max_tokens` означает область применимости, а не guarantee of success beyond train.

## 2. Запись наблюдателя

Существующее `observer_provenance` расширить для композиционного правила:

```json
{
  "feature_id": "derived_<deterministic_digest_prefix>",
  "origin": "DERIVED_FROM_OPERATORS",
  "template_origin": "COMPOSITIONAL_AST_PROMOTION",
  "operator_ast": {
    "composition": "iterate_on_inner_fragment",
    "trim_left": 1,
    "trim_right": 1,
    "fragment_operations": ["SPLIT", "SPLIT"],
    "relation": {
      "composition":"aligned_token_equality",
      "base_max_tokens":1,
      "left_operations":["SPLIT"],
      "right_operations":["REVERSE","SPLIT"],
      "offset":0,
      "expected_equal":true
    }
  },
  "operator_ast_digest": "<sha256 canonical AST>",
  "required_observers": [],
  "parent_feature_refs": ["operator:SPLIT", "operator:REVERSE", "primitive:literal_word_equality"],
  "execution_verified": true,
  "derived_claim_allowed": true,
  "known_invariance_scope": {"max_tokens":8,"representation":"literal","universal_invariant":false},
  "claim_status": "CHECKED_FINITE_INSTANCE",
  "train_only_witness_refs": ["<hash refs from actual stored train>"],
  "verifier_result": {"status":"CHECKED_INSTANCE", "verified_witnesses":16}
}
```

Значения placeholders не являются реальными свидетельствами. Все hashes, refs и версии генерирует production server из своих immutable data; запрет client-provided arbitrary verified flag.

## 3. Независимая проверка

Текущий `white_star_symbolic_observer_verify({project,run_id,feature_id,certificate?})` сохраняется. При новом composition feature он выполняет:

- проверку pinned исходников и разрешённых operators;
- статическую типизацию AST, отсутствия unbounded recursion;
- re-execution каждого trace с UTF-8 spans и исходными tokens;
- сверку версии kernel binding и full train-only witness coverage;
- отказ при подмене одного поля, даже если подделывающий пересчитал внешний digest;
- корректный отказ при изменении `origin` или hidden labels.

**Требуемый пример результатов:**

`CHECKED_INSTANCE` для корректного конечного evidence; `REJECTED` для corrupt trace; `UNKNOWN` при out-of-domain; `NOT_PROVED` для неполного набора свидетельств; `UNDERDETERMINED` для отсутствия единственности grammar.

## 4. Diagnostics

В каждом `observer_inspect(view='diagnostics')` показать:

```json
{
  "candidate_generation": {"seen": 4, "train_compatible": 2},
  "composition_promotion": {
    "attempted": 2,
    "promoted": 1,
    "rejected": [{"ast_digest":"...", "failed_obligation":"..."}]
  },
  "context_promotion": {"attempted": 0, "status":"NOT_APPLICABLE"},
  "limits_used": {"ast_depth":4,"steps":8,"train_witnesses":16},
  "claim_boundary":"finite verified execution and train-compatibility; no proof of unique grammar"
}
```

Эти численные значения — форматный пример, не измеренные метрики.

## 5. Попытка использовать уже существующий AST

Действующий `source_run_id` необходимо либо реально использовать как источник immutable candidate AST с проверкой train digest, либо дать явный отказ. Нельзя делать silently ignored `source_run_id` или регистрировать source-supplied AST как AUTO-DISCOVERED.

Если в кодовой базе невозможно безопасно расширить текущий endpoint, вместо ad hoc расширения внедрить отдельную аддитивную команду `white_star_symbolic_composition_promote` с теми же fields и proof boundary. Поддержать его в system status, catalog, inspect и replay.
