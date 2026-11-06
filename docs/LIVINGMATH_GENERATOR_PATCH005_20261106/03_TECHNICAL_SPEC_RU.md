# Техническое задание: PATCH-005 mixed-length compositional candidate discovery

## 1. Изменяемая часть

Вносить изменения только в генерацию и отбор кандидатов `observer_synthesis_v1` / общей grammar composition, опционально в диагностический вывод; повторно использовать существующие `compositional_ast` promotion, независимый checker `bounded-composition-independent-checker/1`, `dataset_store`, replay, content-addressed refs. Не менять численную Белую звезду, SP 2-комплекс, автономные операции, права проектов, режимы загрузки сертификатов.

## 2. P0. Воспроизвести и исправить минимальный сбой

- Генерировать кандидат PAL (не название `palindrome`, а структурно выражаемый AST) независимо от наличия короткого положительного свидетельства.
- Сначала проверять корректность типов и допустимость рекурсии по строго убывающей мере, затем **полную train compatibility по всем длинам**. Разделить generation (какие AST были предложены) и validation (точные контрпримеры) — не выбирать AST заранее по одной длине.
- Сохранять базы ε и singleton; учитывать паритет и recursion-to-empty. Не трактовать пустой внутренний фрагмент как `UNKNOWN` или `false` в разрешённом домене.
- Минимальные кейсы `B`, `B+SS`, `B+PP`, `B+SP`, `B+PS` должны все выдавать хотя бы один train-compatible AST (для B+SS и B+PP — не только endpoint_equal) и проходить независимое исполнение.
- Запретить фильтр вида `all_positive_same_length`, если он без отдельного доказуемого основания отбрасывает совместимый AST. Никаких silent early drops из-за short positive.

## 3. P1. Минимальная генерация, а не тупой полный перебор

Строить типизированные skeleton AST из действующих операторов, затем проверять/дополнять по наблюдаемым различиям. Разумный маршрут: генерация шаблонов бинарных отношений, специализация по `SPLIT`, `REVERSE`, `Eq`, structural recursion; удерживать кандидатов по типам и длинам при инкрементальном добавлении train. Бюджет ограничивать `max_ast_nodes`, `max_ast_depth`, `max_recursion_steps`, `max_proposals`, `max_runtime_ms`.

Не вводить отдельный hardcoded PAL-classifier или DFA, подогнанный под фиксированные длины, и не подменять цель численной частотой S/P. Сохранить существующий COPY (`compare_fragments`, `MIDPOINT_EXACT_EVEN`) и короткие `contains(AB)` наблюдатели, не регрессировать.

## 4. P1. Трассируемость генератора

Отчёт обязан различать:

1. `NOT_GENERATED` — AST отсутствует в рассмотренном bounded-grammar (с версией grammar и budget).
2. `GENERATED_REJECTED_BY_TYPE` / `TERMINATION` — ошибка типов или отсутствие убывающей меры.
3. `GENERATED_REJECTED_BY_TRAIN` — фактический `sample_id`, expected/observed, без подмены false на UNKNOWN.
4. `TRAIN_COMPATIBLE`, `PROMOTED_VERIFIED`, `TRAIN_COMPATIBLE_NOT_PROMOTED` — separate status.

`candidate_generation` содержит количества по `AST.kind`, список `candidate_digest`, counterexample refs, группу train lengths и отказы с конкретной стадией, `pruning_reason`, `candidate_budget_exhausted`; при truncation статус `BOUNDED_SEARCH_INCOMPLETE`, но не доказательство отсутствия грамматики. Использовать bounded pagination / chunked export, не заливать тысячи строк в summary.

## 5. P1. Невырожденный перенос

Тесты: `PAL` train Σ²∪Σ⁴→Σ⁶/Σ⁸; train Σ¹…Σ⁴→Σ⁷; train Σ¹∪Σ³∪Σ⁵→Σ⁷; train Σ²∪Σ⁴∪Σ⁶→Σ⁸. Считать TP,TN,FP,FN по отдельным закрытым query-only наборам. Требовать FP=FN=0 **только для конкретных тестовых случаев**, иначе диагноз и указанный counterexample, не фальшивый PASS. Актуальные server limits `max_tokens=8`; за пределами `UNKNOWN`.

Короткое PAL Σ⁴→Σ⁶/Σ⁸, COPY20/COPY52→Σ⁶/Σ⁸, вставки SS/PP vs SP/PS — обязательные регрессии. Текущий предел контекстной ветки 64 train не расширять без необходимости: у compositional AST другая архитектура и 126 train может оставаться допустимым (если проходят time/resource budgets).

## 6. P1. Независимость проверок

`operator_verify` проверяет типизированный AST, origin, train-only provenance, UTF-8 source spans, независимый re-execution, границы и внутренние хеши. Replay/журнал неизменны. Порча `output_word_hash`, `SPLIT.position`, исключение свидетеля, подмена origin и `universal_invariant=true` должна приводить к REJECTED даже после пересчёта внешнего SHA-256. Кросс-проектные refs отклоняются; holdout labels не доступны генератору; `execution_permission=false`.

## 7. Совместимость и поставка

Никаких breaking changes. Если добавляются новые поля/версия диагностического объекта — дополнить schema и documenting validation. Подготовить CI golden tests, объективную таблицу run_id старой/новой сборки и различия result_digest; *новые request_key обязательны*. Финальный отчёт: какие AST действительно впервые сгенерированы, какие были готовыми, этапы отбора, неснятые ограничения, ресурсные издержки, все failures. Без дефолтной подмены `UNDERDETERMINED` на доказательство универсальности.
