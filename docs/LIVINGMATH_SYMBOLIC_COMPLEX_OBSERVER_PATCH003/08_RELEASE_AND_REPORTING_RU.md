# Сдача production-патча и дисциплина свидетельств

## 1. Артефакты, требуемые от кодового агента

В репозитории:

- точный diff/commit с инкрементальными новыми MCP endpoints, явной схемой типизации и JSON-schema;
- независимый implementation-side verifier для SP path coherence и GF2 chain complex;
- migration/no-breaking-change note для существующих `white_star_symbolic_*` и численной Белой звезды;
- интеграционные tests, выделенные negative tests, механизмы private replay/export и detector source hashes;
- `bridge_system_status` с версиями и известными ограничениями;
- отдельный отчет `release-gates.md` с P0/P1/P2 и PASS/FAIL/SKIPPED/NOT_IMPLEMENTED (не заменять реальный статус словом «готово»).

В итоговом evidence bundle:

```
release_manifest.json
source_bindings_and_hashes.json
api_examples.json
sp_complex_exact_counts.json
sp_path_coherence_certificate.json
sp_homology_certificate.json
negative_control_results.json
observer_feature_provenance.json
feature_ablation_report.json
synthetic_grammar_holdout.json
nostradamus_pairwise_holdout.json
privacy_sandbox_report.json
run_ids_and_replay_refs.json
changelog_ru.md
```

Можно структурировать иначе, но **не терять смысловых полей**. `summary` inline, подробности — content-addressed immutable artifacts с hash-проверками.

## 2. Форма проверки утверждений

Каждая строка отчёта:

```
claim_id, statement, status, scope, source_ref, witness_ref,
assumptions, verifier_version, check_result,
independent_baseline, open_obligations
```

Статусы: `DEFINED`, `PROVED_IN_MODEL`, `CHECKED_FINITE_INSTANCE`, `OBSERVED`, `EMPIRICAL`, `CONJECTURE`, `UNDERDETERMINED`, `NOT_PROVED`, `INTERPRETATION`. Больше цифр не означает больше доказанной физики. В частности **π₁ finite SP complex** возможна как доказанное утверждение в явной модели, но **π₁ абстрактного «нуля»** без определения морфизмов и заполнений не имеет смысла.

## 3. Release decisions

- `ACCEPTED_P0`: все P0 guards, exact counts, negative tests, verifier, legacy regression, replay.
- `ACCEPTED_P1`: плюс P1 origin audit, ablation, witness-bounded grammar synthesis.
- `RESEARCH_COMPLETED_P2`: плюс реальный корпус, слепое holdout сравнение и честная оценка против baselines. Эмпирическая точность может быть нулевая или равная baseline без препятствия для инженерного релиза, но исследовательская гипотеза тогда **не поддержана**.
- `BLOCKED`: отсутствует trusted verifier, нарушены хеши численного ядра, нет source-bound replay, получена утечка holdout меток или непроверенные 2-клетки объявлены доказательством.

## 4. Источник истины

За основу брать проверенный deployment и два предыдущих архивных отчёта. `01_RCA_AND_DECISIONS_RU.md` содержит exact known live run IDs. Данные Нострадамуса не лежат в этом ZIP: исходный external mixed archive не следует выдавать за критическую научную редакцию и не нужно заново включать в каждый кодовый патч. Если ресурс недоступен, используй имеющийся зафиксированный corpus snapshot и укажи источник, хеш и отличия. Никогда не подставлять другой перевод под видом того же французского источника.

## 5. Ключевой критерий результата

Мы хотим не «модель, которая знает много признаков», а **модель, которая строит новые проверяемые отношения из преобразований и сообщает, чего не может вывести**. P0 формирует качественный математический эталон; P1 отличает genuinely synthesized relation от built-in; P2 проверяет, переносится ли конструкция на реальные смысловые структуры.
