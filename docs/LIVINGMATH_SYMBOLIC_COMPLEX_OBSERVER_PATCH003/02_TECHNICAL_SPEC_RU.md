# Техническое задание LM-SYM-COMPLEX-003

## 0. Паспорт

**Цель:** продолжить разработку LivingMath после `v0.4.2-developer-preview` (`symbolic_v1/1-patch002`) следующими **двумя проверяемыми возможностями**:

1. `symbolic_complex_v1` — явные отношения **между маршрутами переписывания**: позиционно определённые 1-клетки, локальные 2-клетки, цепные комплексы, сертификаты когерентности и корректно ограниченные утверждения о `π₁`.
2. `observer_synthesis_v1` — прослеживаемый синтез **контекстных структурных правил из операций** с проверкой происхождения каждого используемого признака, строгим train/test и ответом `UNDERDETERMINED`, когда данных/механизма недостаточно.

Третий небольшой слой — `pairwise_context_v1` — применяет найденные отношения к текстам: сравнивает оригинальные и нарушенные порядки на уровнях `word→line→quatrain→century` без утечки исходных меток.

**Статус:** спецификация для реализации в живом репозитории, **не** сообщение о выполненной интеграции. **Приоритет:** P0 (обязательный исполнимый S/P-2комплекс) → P1 (грамматический provenance + контекстные проверки) → P2 (текстовый корпус и выпуск). Ничего не надо делать асинхронно.

## 1. Неприкосновенное

- Численная Белая звезда (`base_v1`, `cj_v1`), исходные файлы/хеши её kernel, SUTI и существующий алгоритм Удава **не менять**.
- Сохранить уже работающие `white_star_symbolic_explore`, `white_star_symbolic_inspect`, `white_star_symbolic_replay`, их schema, прежние immutable runs, idempotency, SHA проверки, sandbox и приватные проекты.
- Новые интерфейсы **аддитивны**. Нельзя незаметно менять семантику `history_identity=word/provenance`, отношение `same_sp_normal_form`, уровень `proved_exact`, предсказания или source spans.
- Нет удалённых LLM-вызовов в ядре, произвольного исполнения ZIP/кода, доступа к внешним файлам из payload, неограниченного синтеза правил, вычислительной «магии», runtime-DSL или графового полного перебора по умолчанию.

## 2. P0: структурный 2-комплекс

### 2.1. Базовые типы

Типы первой версии:

```
SymbolicVertex(id, tokens, source_spans, object_scope)
RewriteEdge(id, src_id, dst_id, rule_id, match_span,
            orientation='forward', provenance, verified)
LocalPeak(id, src_id, edge_left_id, edge_right_id,
          branch_kind, join_state, completion)
CoherenceCell(id, left_path, right_path,
              src_id, dst_id, source_peak_id, role, provenance)
OrientedPath(steps=[(edge_id, sign=+1|-1), ...])
ChainComplexRef(vertex_ids, edge_ids, cell_ids, boundary_policy)
HomologyCertificate(field='F2', rank_d1, rank_d2, H1_dim,
                    generator_or_basis_witnesses, verifier_digest)
PathCoherenceCertificate(assumptions, algorithm, obligations,
                         child_dependencies, verifier_digest)
ComplexRun(immutable, versioned, source_or_generator, bounds, diagnostics)
```

Любая 2-клетка — **отношение двух реальных путей с общими концами**. Не допускается произвольный «плоский» реляционный флаг `coherent=true` без проверяемых путей. Раздельно хранить syntactic identity, semantic quotient, alpha equivalence, equality modulo supplied rewrite theory и observer indistinguishability. Один end-state не равен одному path.

### 2.2. Два источника графа

**Режим SP finite fixture (P0):** сервер сам строит `X_N` по параметру `N` (чётные N=2..10) без необходимости загрузки всех слов в одном payload. Вершины — все сбалансированные слова длины ≤N, включая ε. 1-ребро — удаление каждой конкретной соседней пары `SP`/`PS`, с сохранением позиции, исходного слова, целевого слова и distinct edge ID при одинаковых endpoints. Никакие слова других денотационных классов в `X_N` не добавлять. Порядок генерации и IDs детерминированы при фиксированном schema version.

**Режим saved_history (P1):** взять конкретную immutable историю `symbolic_v1` по project/run_id, построить разрешённую 1-skeleton из **фактически сохранённых** операций (не дорисовывать отсутствующих рёбер), автоматически предложить потенциальные локальные peaks, но **не объявлять** пропущенные маршруты существующими. Если операция не является обратимой — нельзя превращать её в алгебраический inverse move; обратное ребро для топологии разрешено лишь как формальная обратная ориентация того же 1-ребра, не физическое действие.

### 2.3. 2-клетки

Локальный peak: из `u` идут два distinct 1-ребра `e:u→v` и `f:u→w`. Проверяющий конструктор ищет **bounded** завершение `v⇒*z` и `w⇒*z` по явно разрешённым правилам и сохраняет оба пути `e·p` и `f·q`; при совпадении `v=w` — bigon. Для SP fixture P0 достаточно one-step join и bigons: все пики проверяются исчерпывающе внутри ограниченного N, без перебора произвольных маршрутов/программ. Для общего DAG — только реально предъявленные и проверенные локальные свидетели, при нехватке `UNRESOLVED_PEAK`.

Поля сертификата: `peak_src`, `edge_ids`, `left_path`, `right_path`, `joined_at`, `source_spans`, `rule_version`, `verified`, `assumption_tags`, `completion_search_budget`. Непроверенные предложения хранятся отдельно со статусом `PROPOSED`/`REJECTED`. Запрещено молча добавлять 2-клетку только потому, что две ветки имеют равное числовое значение `q`.

### 2.4. Гомологии

Строить настоящие boundary maps `∂1:C1→C0`, `∂2:C2→C1` **с согласованной ориентацией**. Для P0 обязательно точный `rank_F2(∂2)` и `dim H1(F2)=dim ker ∂1−rank ∂2`; проверить `∂1∂2=0`, корректность всех attaching paths, отсутствие расхождения источников/концов. Не путать количество топологических циклов с `graph_beta1` у мультиграфа или числом наблюдений Удава.

Формула `graph_beta1 = E−V+c` допустима только для 1-skeleton с `c` компонентами, после проверки связности. `H1(F2)=0` **не равно** автоматическому `π1=0`.

### 2.5. π₁, строгое ограничение статуса

Для **SP fixture** реализовать проверяемый `PathCoherenceCertificate`: каждая редукция уменьшает длину на 2; для всякой пары одношаговых сокращений предъявляется 2-клетка локального join; индукцией по длине каждый направленный маршрут из слова в ε эквивалентен каноническому. Затем любой loop представим зигзагами исходных рёбер и стягивается. Проверяющий должен пересчитать и проверить ключевые обязательства, а не доверять строке `PROVED_TRIVIAL`. Ссылки в certificate должны вести к конкретным 1- и 2-клеткам и более коротким зависимым шагам.

Для **произвольного входного 2-комплекса** P0 **не** обещает вычисление π₁. Ответ: `NOT_PROVED` или `UNKNOWN`, когда нет достаточного сертификата. Опционально в P2 можно возвращать проверенную конечную презентацию `π1` по spanning tree и relators, с явной границей, что неизвестна разрешимость общих word problems.

### 2.6. Отрицательные случаи

- Граф без 2-клеток: β₁>0 при N≥4, `π₁` свободна ранга β₁; нельзя присваивать `π1_trivial=true`.
- Частичный набор bigons или diamonds не позволяет SP induction certificate, даже если случайно `H1(F2)=0`.
- Подмена позиции сокращения, несуществующего edge, несходящихся путей, циклического dependency DAG, чужого `run_id` или source hash → reject с конкретным field_path.
- `SP_INV` S↔P сохраняет semantic zero, но provenance/literal могут отличаться; отображение должно сохранять **изоморфность предъявленного комплекса**, а не raw IDs.

## 3. P1: происхождение и синтез наблюдателей

### 3.1. Реестр наблюдателей с доказуемым provenance

Каждый признак/правило, участвующий в грамматическом ответе, должен иметь immutable record:

```
feature_id, feature_version, semantic_type, required_observers,
operator_expression_or_builtin_function_ref,
origin: BUILTIN | DERIVED_FROM_OPERATORS | SOURCE_SUPPLIED |
        CLIENT_LLM | UNKNOWN,
source_spans_or_parent_feature_ids, construction_trace,
verified_obligations, known_invariance_scope, cost_budget,
train_only_evidence, leakage_audit, digest
```

**Правило происхождения:** `DERIVED_FROM_OPERATORS` разрешено только при наличии явной композиции реальных разрешённых операций, работающей функции-проверяющего и трассы выполнения на образцах. Любой `pair_0_max`, `pair_3_final`, `lag_4_mismatches`, `adjacent_equal`, `endpoint_equal`, и др. из существующего предвычисленного списка по умолчанию `BUILTIN`, даже если выглядит «интересно». Не переименовывать built-in в discovery.

`feature_allowlist`/`denylist` должны реально исключать признак **из обучения и применения**, включая каскадные derived features с запрещёнными зависимостями. Если полное отключение невозможно архитектурно — заявить ограничение, не подменять честный контроль.

### 3.2. Открытый, но bounded синтез отношений

Постановка: дан `ObservedContext=(left_context, fragment, right_context, structural_scope)` и `verification/membership` на train. Кандидат нового отношения строится **из существующих typed operators** (`SPLIT`, `CONCAT`, `REVERSE`, `RENAME`, `SUBSTITUTE`, проверенных путевых преобразований, известных boundary relations), а не из списка жёстко именных family.

`R(u,v|C)` — конечная *контекстная* гипотеза «подстановка u↔v сохраняет наблюдаемый класс/допустимость в предъявленных контекстах C». Не объявлять универсальной congruence или true Myhill–Nerode relation по конечным примерам. Генерация: только bounded compositional expansions, инициированные реальными разногласиями/контрпримерами, предпочтительно Pareto по множеству объяснённых примеров, без общего scalar reward и без полного перебора по всем словам. `max_composition_depth`, `max_proposals`, `max_witnesses`, `max_contexts`, `max_runtime` обязательны. Доказательства, неизвестные и гипотезы отделены.

Сохранять **конкурирующие совместимые правила**, а не только победителя. По возможности возвращать запросы о метках (`active_disambiguation_queries`) от внешнего держателя истинных ответов. Ни один probe не вправе читать sealed test labels. Вывод `UNDETERMINED` при нескольких допустимых грамматиках — нормальный результат.

### 3.3. Парный evaluator со статусом воздержания

Для каждого pair `(original, perturbed)` вычислять `difference_witness` и `rank_explanation`: идентичны при данном наблюдателе → `NOT_IDENTIFIABLE`; все выбранные кандидаты дают одинаковую оценку → `TIE`/`INCONCLUSIVE`; достаточное отношение проверено на train и новый pair разрешим → `PREFERENCE`, **с уровнем empirical, не theorem**. Запрещено автоматически превращать одинаковые оценки в уверенное «правильный порядок».

Различить:
- `invariance_of_representation`: rename-invariant encoding с независимой канонизацией **каждого** варианта;
- `hierarchy`: не терять реальные границы `word→line→quatrain→century`;
- `source_form`: пунктуация/орфография сохранены, но их использование явно именовано;
- `synthetic_alteration`: операции перестановки с source span и real-world отрицательной меткой только от независимого держателя.

### 3.4. Цель не точность любой ценой

Прогноз на скрытых данных обязателен, но **научная приёмка не требует** превзойти случайность: если выход честно `UNKNOWN` и остаётся на baseline, это исследовательский результат. Инженерная приёмка требует корректной проверки, не нарисованных 80%.

## 4. P2: реальный корпус и обратные связи

- Использовать реальный архив Нострадамуса **с фиксацией редакции и аномалий**; оригинальные тексты не смешивать с переводами и apocryphal, не менять последовательность на уровне учётной записи.
- Учитывать известные I.51, II.32, II.38, VII≈42 и неполные/смешанные варианты, хранить `edition_confidence` и опциональную «неоднозначную редакцию» вместо silent fixes.
- `source_segments` с parent_id: центурия, катрен, строка; байтовые UTF-8 offsets, codepoint positions отдельно, если нужно.
- Train I–VIII, holdout IX–X фиксируется до вычислений; синтетические negative variants требуют *independent per-variant encoding*. Если α-collapse приводит к конфликту, не скрывать случай: сохранить `CONTRADICTORY_TRAINING`, `NON_IDENTIFIABLE` и отчёт по потерянной информации; допустим дополнительный conditional gate с исключением конфликтов, но **не заменять** им исходный полный результат.
- Контроли: original vs swap lines2/3, global/local α, dictionary renaming, punctuation-only, lengths-only, naive majority, shuffled-stanza boundaries, random seed, `word`/`provenance` identity. На тех же splits и бюджете. Метрики accuracy, balanced accuracy, MCC если определён, pairwise wins/losses/ties, abstention coverage, error slices by century, confidence intervals if claimed.
- Доказанный маршрут для S/P не переносить на поэзию лишь по аналогии. `observer_synthesis` только предлагает проверяемые структурные гипотезы; семантическая трактовка LLM допускается **после** заморозки предсказаний, как `INTERPRETATION`.

## 5. Форматы ошибок и статусы

`INVALID_INPUT`, `SOURCE_MISMATCH`, `WORD_TOKEN_LIMIT`, `MAX_*`, `BUDGET_EXCEEDED`, `UNSUPPORTED_RULE`, `UNVERIFIED_EDGE`, `UNVERIFIED_CELL`, `UNRESOLVED_PEAK`, `NON_CONFLUENT`, `NOT_PROVED`, `CONTRADICTORY_TRAINING`, `NOT_IDENTIFIABLE`, `UNDERDETERMINED`, `NO_VERIFIABLE_NEW_OBSERVER`, `HELDOUT_LABEL_LEAKAGE`, `REPLAY_MISMATCH`. Имена можно адаптировать к фактическим code conventions; семантическая разница сохраняется. В выдаче `PROVED_EXACT` не должно быть ни статистических оценок, ни красиво декодированных смыслов.

## 6. Производительность и безопасность

- По умолчанию P0 `N≤10` для точного SP-complex; N=12 только если проходит проверенный лимит памяти/времени, не включать автоматически.
- Сервер может строить полный **заранее конечный** SP_fixture для эталонного теста. Это **не** разрешение использовать полный перебор как общий алгоритм поиска грамматики, зафиксировать два разных режима в коде.
- В Worker: существующий CPU/wall/memory sandbox, no file writes/network inside job, fixed source allowlist; idempotency, immutable runs, source hash, compiler version, operations bindings, manifest. Для массивных boundary matrices использовать sparse GF2, bounded limits; не отправлять огромные JSON inline.
- Артефакты: `vertices`, `edges`, `local_peaks`, `2cells`, `homology`, `path_coherence`, `observer_provenance`, `candidate_rules`, `pairwise_eval`, `diagnostics`, `checks`, `manifest`, data-only private export. `inspect` pagination и artifact chunks.
- Хеши строго детерминированы при равных input, rules/kernel binding, seed, features, engine version; timing/RSS отдельно и не обязаны совпадать.

## 7. Разработка по фазам и выпуск

**P0 Gate:** новые exact finite types+API, edge+cell verifier, exact H₁(F₂), SP path coherence certificate, negative controls, independent reference difftests N=2..10, old MCP regression, export/replay.

**P1 Gate:** feature provenance, actual derivation traces, effective feature ablation, bounded context relation synthesis, counterexample queries, pairwise evaluator with no hidden labels, synthetic Dyck/adversarial grammar benchmarks.

**P2 Gate:** frozen real-corpus experiment, multi-centurial holdout, surface baselines, ambiguous-text reporting, privacy/security audit, release changelog.

В каждый фазовый релиз включать git commit, exact version, build hashes, tests, full failures. При падении P1 не блокировать установку P0, но **не считать новую исследовательскую способность полностью принятой**.

## 8. Что категорически не делать

- Не переписывать `ReversibleUDAV`, White Star numeric kernel, NOBS, SUTI, legacy workspace.
- Не подменять 2-клетку simple graph cycle, а `π₁` — `β₁` или `H₁(F₂)`.
- Не принимать все совпадения SP zero в один vertex, не стирать историю сокращений.
- Не вшивать «палиндром», «Dyck» или «Нострадамус» как специальные флаги production grammar.
- Не создавать новый язык программирования, не добавлять произвольный Turing-complete scripting в MCP, не выполнять пользовательские ZIP.
- Не объявлять `source/heldout` открытым для внешних LLM; не выводить новое сознание/физику/«реальную магию» из структурных тестов.
- Не обещать высокую accuracy или универсальное обнаружение смысла: честный отрицательный результат тоже принимается.
