# ТЗ LM-OBSERVER-COMPOSITION-004

**Назначение:** точечно расширить текущий LivingMath MCP после `v0.4.5-developer-preview` (`observer_synthesis_v1/2-context-promotion`) проверяемым продвижением **композиционных/рекурсивных AST** в новые наблюдатели. Существующие FIX-B2 коротких образцов, `symbolic_complex_v1`, численная Белая звезда, SUTI, UDAV и старый `symbolic_v1` **не изменяются семантически**.

**Приоритет:** P0 PAL promotion, P1 COPY induction, P2 генерализация на Dyck/корпус; P0 и P1 имеют самостоятельные acceptance-gates. ТЗ основано на `01_RESEARCH_RCA_RU.md`, формальная семантика в `02_FORMAL_MODEL_RU.md`.

## 0. Неприкосновенные ограничения

1. Не переписывать `base_v1`, `cj_v1`, `white_star_symbolic_explore`, `white_star_symbolic_complex_analyze` и их persistence / immutable saved results. Все текущие MCP-команды и прежние запросы продолжают работать.
2. Фиксировать полную символьную историю; никаких 2D numeric projections, scalar aggregators вместо структурных токенов, подмены буквального слова его SP-нормальной формой. Числовая длина допускается лишь как координата `SPLIT` и bounded execution.
3. Не hardcode флаги `PAL`, `COPY`, `Dyck`, `Nostradamus`, словари смыслов или заранее известный «правильный» ответ в production. Новую выразительность получить **из комбинации разрешённых существующих operators** и их грамматики AST, без обобщённого интерпретатора произвольного кода, Python eval, JSON DSL или LLM runtime.
4. Обязательно train-only selection; `queries` не содержат `accepted`. Истинные holdout labels принадлежат отдельному harness. `hypothesis_frozen_before_queries=true` проверять в тесте.
5. Не утверждать `PROVED_EXACT`, `UNIQUE_GRAMMAR`, `universal_invariant=true` на основании одного конечного train/holdout. Гарантируется только проверенное выполнение ограниченной конструкции.
6. На каждое изменение API — идентифицируемые версия, source hash, kernel binding, worker limits, deterministic result digests, JSON schema, backward compatible inspect/export/replay.

## 1. Функциональная проблема, которую исправляем

На PAL `Σ⁴`, 16 размеченных records, новый synthesis engine уже порождает:

```
derivation_trace[{ast.composition='iterate_on_inner_fragment',
                   status='TRAIN_COMPATIBLE', counterexample_train_ids=[]}]
```

но завершает:

```
NO_LABELLED_DISTINGUISHING_CONTEXT → NOT_PROMOTED
```

Требуется **новая ветка продвижения** для валидных typed composition candidates, независимая от локальных «labelled distinguishing contexts». Отсутствие локального свидетеля не должно уничтожать корректно предъявленный глобальный рекурсивный AST; оно может означать лишь, что один из путей синтеза не применим.

## 2. P0 — Typed compositional promotion для PAL

### 2.1. Интерфейс кандидата

Переиспользовать AST из существующего `derivation_trace` и `grammar_hypotheses` (`observed_relation_composition`). Прежде всего поддержать:

- `aligned_token_equality` из типизированной последовательности `SPLIT`, `REVERSE`, `literal_word_equality`;
- `all_observed_relations` как bounded conjunction;
- `iterate_on_inner_fragment` c `trim_left,trim_right∈N`, строго положительным суммарным trim, `fragment_operations=['SPLIT','SPLIT']`, остановкой на конечном base-case;
- существующий короткий literal prototype promotion остаётся отдельной неизменной веткой.

Вычисление AST должно выполняться **на полном первоначальном слове** с исходными source spans, а не на alpha/normal-form representation, если это явно не объявленная локальная область кандидата. Каждая операция вычисляет выходы в типе `Word`, никакой fake flag `coherent=true` без реального исполнения.

### 2.2. Pipeline — отдельно поиск, выбор, продвижение, применение

`(A) DISCOVER`: существующий ограниченный search генерирует typed AST. Каждый кандидат получает AST hash, provenance, supported primitive bindings, train coverage, predicted labels и witness refs. Не маркировать built-in как newly derived.

`(B) SELECT`: на TRAIN проверяется, что AST типизируется, завершается, не читает holdout, предсказание определено в объявленном scope. Отдельный класс `TRAIN_COMPATIBLE` означает нуль ошибок. Если несколько кандидатов совместимы, сохранять альтернативы; selection policy фиксировать. Prefer immutable candidate source / deterministic Pareto by explainable coverage and complexity, not best test accuracy. Несовместимые rejected candidates и контрпримеры сохранять.

`(C) PROMOTE`: для выбранного train-compatible композиционного кандидата строится executable bounded observer, составленный **только из разрешённых operations**, с полным certificate и immutable feature id. Результат `PROMOTED_OPERATOR_COMPOSITION` / `VERIFIABLE_OPERATOR_COMPOSITION_FOUND` только после независимой успешной проверки; иначе `NOT_PROMOTED` + точная failed_obligation.

`(D) PREDICT`: только после freeze взять query-only dataset, применить **ровно этот** наблюдатель с scope checks, записать predictions and evidence digests. Вне области `UNKNOWN`, не false. Не подменять retained hypothesis family одним доказанным законом.

`(E) VERIFY`: новая функция проверки должна работать и с уже существующими `DERIVED_FROM_OPERATORS` v0.4.5, и с рекурсивным AST, пересчитывать реальные примитивы независимо от создателя.

Ключевая метрика P0: PAL-16-to6 и PAL-16-to8 в режиме **`enabled_builtins=[]`**, где `derive_relations=false` служит отрицательным контролем.

### 2.3. Source-run bridge

Опциональное поле `source_run_id` уже существует. Если оно предъявлено, загрузить фактически сохранённый `symbolic_v1` run **того же project**, проверить input digest, exact AST digest, привязку к train и версию операторов; позволить кандидату из этого run пройти проверку/продвижение. Чужой `run_id`, mismatch train, old incompatible AST → `REJECTED` либо `NOT_COMPATIBLE`, а не silent fallback и не право исполнения.

Нельзя **требовать** source_run_id: правило должно продвигаться и непосредственно из текущего derivation_trace. Если обе ветки доступны, provenance содержит источник выбора; не утверждать, что кандидат найден сервером, если он был введён как source supplied.

### 2.4. Сертификат и проверка

Обязательны поля и смысл из `02_FORMAL_MODEL_RU.md`. Минимальный сертификат: exact AST/canonical digest, operator versions/bindings, bounded evaluator scope, frozen train digest, source record refs and UTF-8 spans, trace per train record, node input/output hashes, declaration of proof boundary, immutable `feature_id`, independent verifier digest.

Проверяющий повторяет операции **с нуля**. Верификатор НЕ должен принимать только hash предоставленного trace (злоумышленник может пересчитать его после подмены!). Проверять валидность каждого шага `SPLIT`, `CONCAT`, `REVERSE`, equality, корректность границ и терминацию рекурсии. На fail возвращать `REJECTED` с `field_path` и обязательством, никакой выдачи permission.

Scope: текущий worker `CPU≈5s`, wall≈6s, memory≈512MB; max_tokens и depth явно объявлены. Допустить PAL n≤8 для P0, n=10 только когда проверен bounded scope. Вне scope `UNKNOWN`/`score=null`. Нельзя внезапно требовать долгих многоминутных прогонов.

### 2.5. Никаких скрытых парсеров специальных языков

Если старый `iterate_on_inner_fragment` уже типизирован в shared module, переиспользовать его. Если нет, создать маленький **проверяемый** evaluator для нынешних AST, не «универсальный DSL» и не крупный переписанный движок. Опасные бесконечные циклы отсекаются статическим `strict decrease` `|inner|<|parent|`, ограничением шага/глубины и независимой runtime проверкой.

## 3. P1 — Генерация сравнения удалённых фрагментов (COPY)

Существующая ветка **не находила COPY**, поэтому для P1 недостаточно продвижения. Понадобится один новый общий конструктор выражений, построенный из уже существующих операций:

```
SPLIT(Word, position=MIDPOINT_EXACT_EVEN) -> (Left, Right)
literal_word_equality(Left,Right) -> Bool
```

`MIDPOINT_EXACT_EVEN` — параметризованная позиция разреза, не число, представляющее смысл и не отдельная примитивная операция. Ввести в bounded candidate generator общую схему двухфрагментного сравнения. Не добавлять `if COPY then ...`.

Требование: генератор на `Σ²∪Σ⁴` (20 records) выбирает / сохраняет train-compatible правило `compare_fragments`, публикует его provenance и подтверждает конечный scope; на `Σ⁶` 64/64, на `Σ⁸` 256/256. Если не найден — честный `NO_VERIFIABLE_NEW_OBSERVER`, фаза P1 не пройдена. Значения, длины, метки оригинальных слов не допускается смешивать с SP-zero reduction.

Отрицательный контрпример на «только совпадают первые/последние буквы» и на «совпадают counts» должен разрушать слабые гипотезы.

## 4. P2 — Context-free / перенос на тексты (исследовательская, не блокирует P0)

- Dyck-1: сравнение структуры префиксов/разложение `S u P v`, без включения встроенного `pair_0_max`. Не выдавать 100%, полученные с built-in, за открытие нового закона.
- Nostradamus: frozen centurie holdout, независимые original-vs-swap labels, восстановление `quatrain→line→word`, alpha/line boundaries, отсутствие punctuation leak, честный `NOT_IDENTIFIABLE` при совпадениях.
- Никаких обещаний открыть «смысл» или предсказать события. В P2 исследуем переносимость структурных правил, и её отсутствие — допустимый научный результат.

## 5. Совместимость API

Предпочесть **аддитивное** изменение текущих команд:

- `white_star_symbolic_observer_synthesize`: необязательный `promotion_policy` (`literal_context_only|compositional_ast|auto`) с bounded options, default текущего поведения ради обратной совместимости (для P0 harness mode выбрать `compositional_ast` либо `auto`); существующий `source_run_id` использовать по назначению.
- `white_star_symbolic_observer_inspect`: `observer_provenance`, `model`, `candidate_rules`, `pairwise_eval`, `diagnostics`, `checks` расширить source-bound typed evidence; ничего не удалять.
- `white_star_symbolic_observer_verify`: принимать `feature_id` нового composite feature, независимо сверять его типизированный AST/trace; все варианты контрподделок поддержать через `certificate` replacement.
- `white_star_symbolic_dataset_store`: сохранять старую schema и `source.sha256`/`edition`/`rights`; train/query isolation; не снимать контроль `HELDOUT_LABEL_LEAKAGE`.
- `white_star_symbolic_extension_replay`: пересчёт compositional model и независимого verifier; `REPLAY_MATCH`, `journal_hash_chain=PASS`.

Если внедрение `promotion_policy` невозможно без breaking change, создать отдельную **аддитивную** команду `white_star_symbolic_composition_promote`; указать точные версии в release notes. Не вводить обязательные новые поля в старых запросах.

Контракты подробно в `04_MCP_CONTRACTS_RU.md`.

## 6. Ресурсы, ошибки, уникальность и безопасность

- Train sets до 64 для текущего короткого prototype mode остаются валидными. Для operator-AST branch не использовать старый ресурсный preflight как семантическое препятствие: поддержать bounded batch/stream up to 512 records (если реально проходит worker) либо честно документировать меньшее значение. Ни в коем случае не «снимать лимит 64» глобально на все old modes.
- Ограничения `max_ast_nodes`, `max_ast_depth`, `max_recursion_steps`, `max_tokens`, `max_train_witnesses`, `max_runtime` жёсткие; отмена работы по CPU/WALL лимиту без интерпретации `TIMEOUT` как False.
- Результат не зависит от hash-key повторных запусков; каждый новый acceptance run с новым `request_key`. Repeat same key → unchanged run_id (idempotency). Different fresh keys same data/kernel/seed → same deterministic result_digest.
- Per-user/private project scope and source binding; запрет сети, LLM, ZIP execution и arbitrary paths; query labels не видны обучению.
- Инвариантность переименований проверять только в заявленной области. PAL/COPY с literal equality инвариантны при биекции алфавита (одновременном переименовании всех атомов), но не при независимой случайной замене в каждой половине.

## 7. Acceptance gates

**P0 PASS** iff одновременно:

1. PAL: `Σ⁴` (16 train) → `Σ⁶` (64) TP=8,TN=56, FP=FN=0; `Σ⁸` (256) TP=16,TN=240,FP=FN=0; **without builtins**.
2. В `observer_provenance` один или несколько новых реальных `DERIVED_FROM_OPERATORS`, `operator_ast.composition=iterate_on_inner_fragment` (либо точный семантически эквивалентный операторный AST), `role=USED` или `used_feature_ids`; не просто кандидат в `derivation_trace`.
3. `white_star_symbolic_observer_verify(feature_id)` → `CHECKED_INSTANCE`; min required train witness coverage 16; falsification tests → `REJECTED`; source_run_id regression passes.
4. `derive_relations=false` и denylist promoted feature реально ухудшают результат или дают честное отсутствие классификации; no fake discovery.
5. Frozen hypothesis digest одинаков для query6 и query8 при одинаковом train/config; no holdout labels; claims bounded, `UNDERDETERMINED` вне uniqueness.
6. Replay new export, old numeric/complex/symbolic regression; no perf limit overflow.

**P1 PASS** iff P0 PASS + COPY AST построен **генератором**, а не загружен как ground truth: training 20, `Σ⁶`: TP=8,TN=56,FP=FN=0; `Σ⁸`: TP=16,TN=240,FP=FN=0; verified feature, effective ablation, trace lineage. `source-supplied` AST может подтвердить evaluator, но **не засчитывается как discovery**.

**P2 PASS** requires separate frozen benchmark with report and baseline; no hardcoded success threshold on Nostradamus. Report failure honestly.

## 8. Reporting и сдача

Агент сдаёт один ZIP: diff/patch real repository code, exact commit/deploy ref, version/kernel hashes, tests, run manifest with NEW request_keys, independent verification output, risk + backward compatibility summary. Приложить `RCA_RU.md`, `CHANGELOG_RU.md`, `ACCEPTANCE_RU.md`; никаких фиктивных «выполнено» до живого запуска и independent verifier. Запуск коротких тестов, без часов брутфорса. Не ломать старые immutable runs.
