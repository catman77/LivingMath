# ТЗ LM-NL-CAUSAL-003: frozen counterfactual decoder

**База:** `catman77/LivingMath`, продакшн 0.4.10, namespace `src/lm_suti_assurance/nl_proposal/`. Реальный `NLProposalBridge/1` сохранён, перезапуск вычислительных ядер не требуется. **Назначение:** изолировать содержательный вклад operator trace от LLM и от тривиальных формальных преобразований.

## P0 — строгая заморозка и четыре режима

Добавить opt-in MCP-инструмент `formal_nl_redecode` (или эквивалентную явную команду, не ломая 93 старых инструмента), вход:

```json
{
  "project": "OWNED_PROJECT",
  "request_key": "unique-key",
  "source_nl_run_ref": "ACTUAL_FINISHED_NL_RUN_REF",
  "source_item_indices": [0],
  "structural_run_refs": [{"engine":"symbolic_v1","run_id":"ACTUAL_OWNED_RUN_ID"}],
  "arms": ["NO_MOVE","REAL_TRACE","SHAM_ORDER","PRIMITIVE_CLOSURE"],
  "policy": {"max_candidates_per_source":8,"max_ast_nodes":32,"max_cpu_ms":4000,"sham_seed":2211,"max_primitive_depth":2}
}
```

`source_nl_run_ref` должен указывать на **завершённый и owned run** с фактически сохранённым provider `receipt`; запрещено передавать произвольный `raw_output` как будто он модельный. Выполнять `replay_bundle` по frozen fields перед новым контрфактическим анализом. Все arm используют **одну и ту же**:

- `source_sha256`, `source_ref`, bytes, unicode/normalization reverse-map, signature,
- `provider_request_sha256` и `provider_receipt_digest`,
- `raw_output_sha256` и исходные source-bound base proposals,
- `candidate_base_ast_sha256`, binders/token links,
- одинаковые candidate/CPU/AST budgets.

Система должна **доказуемо** зафиксировать `model_calls_delta=0`, `network_calls=0`, `provider_request_equal=true`, `raw_output_equal=true`, `base_ast_equal=true`. Реальный trace должен принадлежать тому же проекту и иметь тот же source+snapshot guards. Любой mismatch запрещает сравнение (`UNBACKED_ORIGIN`, `SOURCE_BINDING_MISMATCH`, `REJECTED_PROVENANCE`). Исходные run и кандидаты не мутировать; результат append-only.

Семантика arm:

- `NO_MOVE`: replay исходного base AST, без добавления структурных кандидатов.
- `REAL_TRACE`: тот же base AST, один действительный source-aligned оператор; извлечённый trace проверен `provenance.traces` и hashed.
- `SHAM_ORDER`: тот же **frozen provider response**, но `source_order` трансформируется ровно одним детерминированным shuffle/reversal на уровне **декодера**, а не provider input; `origin_status=SHAM_NOT_EVIDENCE`. Изменить только эту причинную переменную, сохранить `before_ast` и число попыток.
- `PRIMITIVE_CLOSURE`: без White Star, в том же бюджете перечислить допустимые типизированные транспозиции внешних кванторов, простое alpha-renaming, явно поддержанные локальные последовательности. Сохранять minimal operator derivation/cost; не вводить оракула семантики/строковых эвристик под gold.

**Запрещено:** текущий двойной placebo из `build_request` плюс `build_move`, добавочные LLM-запросы внутри `redecode`, кормление gold в generator/prompt/closure. Если замороженный receipt отсутствует: `FROZEN_RECEIPT_UNAVAILABLE`, а не реконструкция по SHA.

## P1 — таксономия отличия и минимальное объяснение

Добавить independent finite-model checker для каждой пары base/candidate по объявленной сигнатуре и классам моделей. Отдельно считать:

- `SAME_ON_BOUND`: оба truth vectors совпадают.
- `STRONGER_ON_BOUND`: набор истинных моделей нового AST — строгое подмножество base.
- `WEAKER_ON_BOUND`: строгое надмножество.
- `INCOMPARABLE_ON_BOUND`: есть два направления контрпримеров.
- `UNKNOWN_BOUND`: ресурсная граница, неполный перебор, неподдерживаемое представление.

Возвращать две конкретные `finite_countermodel` (если необходимо), scopes/domains и метки `UNIVERSAL_EQUIVALENCE_NOT_CLAIMED`. Не менять статус `PROPOSED` на `SEMANTICALLY_LICENSED` из совпадения вектора или trace. Присваивать `PRIMITIVE_CLOSURE_REPRODUCED` только если кандидат конструктивно достигнут из frozen base primitive registry и проверена именно цепочка AST, а не «похожий текст».

На U21–U25 ожидаемый результат: исходное `∀x∃y` и `∃y∀x`; TRUE vs FALSE на диагональной модели размера 2. Широкая формула должна быть выведена из исходной **одним primitive swap** и хеши должны совпасть с опубликованными B-derived SHA (см. эталонный скрипт в архиве). Это контроль минимальной достаточности, не gold для продукционного генератора.

## P2 — опыт «что добавляет Белая звезда сверх тривиальных правил»

Считать для каждого source:

`new_structural = valid_candidates(REAL_TRACE) \ valid_candidates(NO_MOVE)`;

`nontrivial_structural = new_structural \ valid_candidates(PRIMITIVE_CLOSURE)`.

При отсутствии новых нетривиальных кандидатов возвращать `NO_INCREMENTAL_STRUCTURAL_EXPRESSIVITY_ON_BOUND`. Текстовая допустимость — независимая научная метка, не выводимая из статусов происхождения. Шаблон U21–U25 — **не использовать** как новую скрытую выборку: он уже раскрыт и должен оставаться *positive open control*.

Запланировать новую скрытую выборку **других** структур: 3+ квантора, отрицание внутри scope, кореференция, модальность, «один и тот же», относительные придаточные; смешать с однозначными отрицательными контролями. На любом новом эксперименте обозначить precommit SHA корпуса, независимый LLM model receipt, source/tokens rights, конкретный budget. Предпочтительны источники с лингвистически проверенными допустимыми чтениями; иначе только `ASSISTANT_AUTHORED_ORACLE` и `HUMAN_NOT_EVALUATED`.

## P3 — инженерная безопасность, идемпотентность и повторяемость

- Прежние 93 MCP tools не нарушать; добавить только opt-in.
- Отсутствие execution grant на всех ветвях, adversarial source SHA/foreign ref/fake frame/changed AST должны давать fail-closed.
- `run_ref + request_key` идемпотентен, иной payload с тем же ключом — `REQUEST_KEY_CONFLICT`.
- CPU budget ≤4000 ms, `max_candidates ≤8`, bounded responses, data-only export и replay без provider и сети.
- Замерить реальную стоимость каждого arm; одинаковые candidate ceilings и количества шагов. `SHAM` должен честно помечать trace как недоказательный.
- **Проверить** 1024/1024 старых контрольных строк (Dyck2, palindrome, parity DFA, anbn) и 12 старых replay, не использовать старые отчёты как замену фактического прогона.
- Желательно восстановить старый C `run_ref=076ccc229e6c661dae47459449ffc28f5e499f90c68ffe03bb10cc77a7f2ef46` через inspect *без нового provider*. Если это невозможно — маркировать техническую невозможность, сохранить journal, не редактировать историю.

## P4 — прозрачный научный вердикт

Отдельно сообщать 1) техническую валидность origin, 2) формально-типовую корректность, 3) finite-model логическое отличие, 4) примитивную воспроизводимость и minimal cost, 5) внешнюю semantic admissibility. Не объявлять пользу White Star при одном лишь увеличении числа типизированных формул или при проверенной trace. Нужна независимая human adjudication, защищённая от подсказок модели и ярлыков источника.

## P5 — поставка

Вернуть ZIP с `RCA_RU.md`, изменениями кода, `TEST_MATRIX.json`, raw receipts, чистым replay, ресурсами, source commit SHA, документацией, prompts и инструкцией rollback. В `TEST_MATRIX` явно отделить `REAL_SERVER_EXECUTED`, `LOCAL_CHECKED`, `NOT_EXECUTED` и `CONJECTURE`. Если материализация исходного C невозможна — выделить blocker, не ставить зелёный PASS.
