# Контрактные предложения: без breaking changes

Использовать существующий `white_star_symbolic_observer_synthesize(project,request_key,request)` с `promotion_policy.mode=auto|compositional_ast`, `candidate_sources=[derivation_trace,source_run_id]`. Новая обязательная команда не нужна.

## Диагностика генерации (расширить `diagnostics.candidate_generation`)

Предлагаемые поля, опциональные и назад совместимые:

```json
{
  "grammar_version": "mixed_length_typed_composition/1",
  "search_budget": {"max_ast_nodes": 32, "max_ast_depth": 8, "max_proposals": 128},
  "train_length_histogram": {"2": 1, "4": 16},
  "generated_by_ast_kind": {"aligned_token_equality": 2, "iterate_on_inner_fragment": 1},
  "generated_count": 3,
  "type_checked_count": 3,
  "train_compatible_count": 1,
  "candidate_records": [
    {"ast_digest": "<server-calculated SHA-256>", "kind": "iterate_on_inner_fragment",
     "generation_status": "GENERATED", "type_status": "TYPED",
     "train_status": "TRAIN_COMPATIBLE", "counterexamples": [],
     "promotion_status": "PROMOTED_VERIFIED"}
  ],
  "bounded_search_complete": false,
  "bounded_search_reason": "max_proposals",
  "no_unique_grammar_claim": true
}
```

Placeholder digest не должен попадать в реальные ответы. Модель и типизированный AST уже доступны через `observer_inspect(view=model)` и при необходимости `artifact` chunks. Сохранить старые поля `seen`, `train_compatible`, `composition_promotion` и `promotion.failed_obligations`.

## Инварианты и статусы

- `NO_TRAIN_COMPATIBLE_TYPED_COMPOSITION` допустим только если каждый сгенерированный типизированный кандидат реально провален train или явным образом указано исчерпание bounded catalog. `NOT_GENERATED` нельзя выдавать за отрицательный математический результат.
- `TRAIN_COMPATIBLE` — согласие по конечному train, не уникальность и не теорема.
- `CHECKED_INSTANCE` — finite proof of actual AST execution under declared scope.
- `UNKNOWN` для length > `max_tokens`, `RESOURCE_LIMIT` для превышения времени/узлов; не False.
- Сохранить content addressed `feature_id`, `operator_ast_digest`, `verifier_digest`, source spans и immutability.
- Исторические `request_key` никогда не переписывают прежний run_id; для повторной приёмки всегда выдавать новые.

## Приватность

`task.predict_ref` — только query-only dataset. Любые `accepted`, `label`, `truth`, сведения о holdout в query records — `HELDOUT_LABEL_LEAKAGE`. Cross-project refs — `NOT_FOUND`/reject. Никогда не использовать `source_run_id` другого train как подсказку, если train digest mismatch.
