# Техническое задание LM-NL-PROPOSER-002

**Объект работы:** существующий MCP `SUTI–Bridge–LivingMath`, текущая подтверждённая сборка `v0.4.9-developer-preview` / `formal001-20261107T032742Z` (если к моменту разработки версия иная, снять фактическую и сверить). **Не создавать другой сервер и не переписывать Formal Bridge, белую звезду, numerical75 и старую SUTI-ветку.**

**Цель:** получить живую цепочку `буквальный русский текст → несколько независимых source-bound гипотез → типизированные формулы → строгие следствия/контрмодели/различающие вопросы` с White Star как управляемым, измеримо полезным (или честно бесполезным) поисковым плечом. Ключевой объект результата — не один «правильный смысл», а **множество конкурирующих интерпретаций с доказуемым происхождением, типизацией и границами применимости**.

## I. Фактически установленное основание

Доступны `formal_store`, `formal_interpret`, `formal_model_check`, `formal_contrast`, `formal_inspect`, `formal_verify`, `formal_synthesize`, `formal_replay`; `white_star_explore/inspect`, `white_star_symbolic_explore/inspect` и `assurance_project_new`. `formal_bridge_v1.semantic_proposer=EXPLICIT_HUMAN_OR_IMPORTED_PROPOSALS; no general NL decoder`. `white_star_symbolic_explore` оперирует исходными токенами, α, контекстами и трассами, но не выводит FOL. Численная White Star требует concepts/axes/coordinates, задаваемые клиентом; decoder маркирует отношения как `CREATIVE_RELATION_PROPOSAL_NOT_SOURCE_ENTAILMENT`. `formal_interpret` при импортированных предложениях проверяет sort/связность переменных/источник, но происхождение `provider.kind` считается декларацией, а семантическая привязка остаётся `PROPOSED`.

Непосредственные эксперименты и реальные id — в `docs/RCA_NEW_EXPERIMENTS_RU.md`, `evidence/LIVE_RUNS.json`. Не переписывать результаты задним числом.

## II. Новый механизм: две последовательные границы, не один недоказанный «перевод»

### A. Source → Structural proposal domain

Входной объект должен содержать **точные** UTF-8 байты, SHA256, rights, нормализацию (None/NFC + обратную карту), сегменты, explicit context и сигнатуру задачи: сорта и роли предикатов. Сигнатура может быть явной или предложенной отдельным провайдером; предложенная сигнатура НЕ является истинной без принятых предпосылок.

`SourceAnalysis` должен давать source-bound объектные кандидаты: сущности, типы, предикатные роли, кванторы, отрицание, область действия, анафору, эллипсис и открытые альтернативы. Допускается LLM для первичной разметки, но поле `origin` и receipt обязательны. Вход без подключённого поставщика не должен выдавать фиктивно «автоматические» формулы; допускается `PROVIDER_UNAVAILABLE` или `SOURCE_UNDERSPECIFIED`.

На каждой альтернативе хранить два слоя:
1. **наблюдения**, прямо поддержанные байтами (`span`, `quote`, tokenization, lexical form, syntactic relation only if supplied with origin);
2. **добавленные предпосылки**, в том числе дискурсные, лексические и прагматические, которых нет в буквальном тексте.

Никаких `if "Каждый исследователь"` и аналогичных conditionals в production. Те же механизмы обязаны переноситься на переименованные имена, переставленные аргументы, новые глаголы, другой порядок слов. Обязателен `NO_WELL_TYPED_DECODING` как нормальный результат.

### B. Structural proposal domain → FormalCandidate (новый explicit decoder)

Добавить **отдельный адаптер** `NLProposalBridge/1`, который превращает *задокументированные* структурные предложения в набор typed FOL AST для существующего `formal_interpret`. Не изменять алгоритм `white_star_explore`; не объявлять его numeric weights truth/confidence или знаками кванторов. Различие:

- `G0` — source-only формализатор (одна и та же LLM/клиент/temperature/prompt бюджеты и сигнатура);
- `G1` — тот же source-only слой + допускаемые структурные **следы** White Star; произвольная формула не становится «порожденной Белой звездой», пока нет проверенной последовательности source frame → предложенный AST move → итоговый AST hash;
- `G2` — контроль с переставленными/фиктивными кадрами при тех же бюджетах;
- `G3` — другой seed/небольшое изменение обоснованной encoder разметки на том же source; допуск без универсальной инвариантности.

Нужен **внутренний типизированный граф порождения** (не новый универсальный DSL):

```
SourceByteSpan ──> Lexical/Syntactic proposal (with origin)
               └─> StructuralFrame/History witness (optional, exact ref)
Both ──> CandidateMove (typed, source-licensed?, premise-added?)
     ──> Formal AST (existing FOL IR)
     ──> Existing formal_interpret(typecheck)
     ──> Existing formal_model_check / formal_contrast
```

`CandidateMove` может менять приоритет/область кванторов, альтернативу привязки, анафорическую связь, предикатное чтение и указанное допущение **только через общий well-typed AST builder**, а не через имена тестовых задач. На каждом изменении — AST before/after, источник разрешающего различия, `addition_assumption`, `operator_trace_ref`. Если структурный кадр невозможно преобразовать в осмысленную операцию с формулой, честно вернуть `UNDECODABLE_FRAME`, не выдумывать операцию.

Отдельно сохранять **сырой набор предложений до дедупликации** и результат дедупликации **только по явно выбранной доказанной или проверяемой в заданном классе эквивалентности**. При совпадении истинности на конечном наборе моделей — не удалять различающиеся AST и не писать `LOGICALLY_EQUIVALENT`.

## III. Критический новый защитный контракт (P0)

`formal_interpret(candidate_provider.kind="white_star")` по нынешнему API является **импортом декларации** и может принимать фальшивый `run_id`; это видно в эксперименте E3. Сохранить обратную совместимость старого `formal_interpret` — он должен продолжать хранить человеческие гипотезы как `PROPOSED`, без ложного обещания честного origin.

Ввести отдельный путь `propose_from_verified_trace`/`formal_nl_propose` с обязательно проверяемой цепочкой:

```
source_ref (owned) + exact SHA
    → existing white_star run_id in same project
    → immutable common_snapshot/source sha equivalence
    → frame_id actually present in inspect output, or symbolic DAG node/operation
    → validated source evidence & explicit derivation step
    → fully typed candidate AST sha
    → linked existing FormalCandidate
```

Произвольный пустой/неизвестный `run_id`, `F99`, неправильный source, чужой проект, перестановка source spans, подмена координат после snapshot, несуществующий parent node, поддельный AST hash → `UNBACKED_ORIGIN` / `SOURCE_BINDING_MISMATCH` / `REJECTED_PROVENANCE`, **никакой** `VERIFIED_ORIGIN`. Не путать `VERIFIED_ORIGIN` с истинностью предложенной семантики! Imported `DECLARED_UNVERIFIED` разрешён, но явно разметить.

Ввести `origin_status` как поле отдельно от `type_status` и `semantic_alignment_status`, например:
- `DECLARED_UNVERIFIED`, `SOURCE_BOUND_CHECKED`, `TRACE_LINK_CHECKED`, `UNBACKED_ORIGIN`;
- `TYPED`, `TYPE_REJECTED`;
- `PROPOSED`, `SOURCE_UNDERSPECIFIED`, `EXTERNAL_ADJUDICATION_REQUIRED`.

Приёмочный контрпример: `candidate_provider.kind=white_star` с 64 нулями в run_id и frame `F99` не должен **в новом verified-path** пройти как подтверждённое происхождение. Старое импортное API может принимать декларацию, только с явным предупреждением.

## IV. Minimal API — не раздувать MCP

Предпочтительно **один новый opt-in метод** `formal_nl_propose` и чтение его результатов через расширенный `formal_inspect` / `formal_nl_inspect` только если старый inspector не допускает нужные страницы; зарегистрировать в текущем FastMCP (HTTPS/OAuth), а не создавать приложение рядом.

Предлагаемый контракт (ТОЛЬКО проектный, имя/поля ещё не установлены):

```
formal_nl_propose({
  project, request_key, source_ref, target_signature,
  source_analysis_ref?, encoder_ref?,
  structural_run_refs?: [ {engine, run_id, frame_ids?, node_refs?} ],
  provider: {kind, binding_ref?, model_id?, runtime_policy?},
  policy: {mode: source_only|white_star_structural|white_star_numeric|matched_ablation,
           max_candidates, max_model_calls, max_tokens,
           max_cpu_ms, max_frames, seed},
  requirements: {exact_source_bindings: true, typed_ast: true,
                 independent_checker: true, no_gold_labels: true}
}) -> {run_ref, candidates[], rejected_moves[],
       unresolved[], provenance_receipts[], metrics, budget, status}
```

Если LLM доступна только через подключение пользователя или серверное opt-in, требовать реальное подключение и receipt, не кэшировать в режиме «настоящего нового вызова». Если доступен только внешний клиент, сделать source-bound `candidate_provider.kind=external_llm` и изолировать его от ядра. Состояние `NOT_EXECUTED` для отсутствующих вызовов.

Для каждого кандидата минимум:

```
FormalCandidatePlus {
  source_ref, source_sha, candidate_ast_sha,
  source_spans[], token_role_links[],
  source_analysis_ref?, white_star_trace_refs[],
  structural_move_log[], added_assumptions[], competing_parse_refs[],
  origin_status, type_status, semantic_alignment_status,
  premise_ledger[], scope:{model_class,quantifier_domain,context_refs},
  creator:{provider,model_id,seed,receipt_digest},
  checker_receipt_ref?, contrast_refs[]
}
```

Trace binding обязательно свидетельствует **реальное использование** White Star при построении/переборе кандидатов. Просто прикрепить произвольный run_id к тому же output → не зачёт.

## V. Режим «Белая звезда порождает» — как проверить причинную роль

Не разрешается утверждать, что White Star улучшила формализацию, только потому что модель прочла кадры с метками `ALIGN/TENSION`.

Тестировать **при одном и том же** исходном тексте, экспертной/синтетической формальной задаче, target signature, версии provider, token/tool/call budgets и фиксированном наборе допустимых интерпретаций:

A. source-only baseline;
B. source + действительные structurally traced frames;
C. source + permuted/shuffled frame labels and same-size payload;
D. source + other coordinate encoding при фиксированном буквальном источнике;
E. optional `same proposer, no active contrast`.

Для каждого изменения: доказать (i) его `formal AST` действительно появился из честной трассы, (ii) формальный результат хорошо типизирован, (iii) внешне оценена допустимость интерпретации, (iv) изменение результатов относительно A/C не объясняется числом генераций/токенов.

**Жёсткий stop-rule:** если B не лучше A/C на слепых независимых тестах при matched cost, результат — `WHITE_STAR_INCREMENTAL_BENEFIT_NOT_ESTABLISHED`. Это не объявляет механизм бесполезным вообще; только не разрешает claims о текущей полезности. Не менять численную физику ради прохождения теста.

## VI. Приёмочные эксперименты и оракулы

### Предварительный пилот: P0, P1 (короткий)

Использовать 6–12 **dev** исходных фраз и минимальные contrast/model проверки. Выбирать не самые очевидные, а диагностичные: одно/два прочтения, отрицание и scope, анафора с двумя антецедентами, «все/не все», явно неподдержанные термы, семантические минимальные пары с одинаковым α-паттерном. Для `CandidateMove` должны работать отрицательные контрпримеры. На dev допускается итеративная разработка; никаких чисел heldout в train.

### Blind acceptance: P2, P3

Не менее **36 новых** русскоязычных исходных текстов, сгруппированных **по 6** в шести независимых семействах: (1) scope/quantifiers, (2) uniqueness/cardinality, (3) negation, (4) anaphora/coreference, (5) modality/temporal context, (6) lexical predicate swaps/ellipsis/unsupported signature. Сегментировать **по семействам/шаблонам**, а не случайно по парафразам. Отдельный набор с изоморфными переименованиями всех имён и с adversarial pair из E1.

Для каждого test-source — source SHA, ориентирующий (не исчерпывающий) **набор допустимых прочтений**, ссылки на независимые экспертные аннотации или synthetic-authorized gold, отдельные проверяемые false readings. Из текста часто невозможно установить единственное intended meaning: оценивать coverage *допустимых альтернатив*, не «угадай одну метку».

Gold не находится в payload `white_star`, LLM-подсказке, search labels и версионированных rules. Заморозить candidate-set, signatures, prompts и их SHA перед вскрытием. Минимум два независимых человеческих оценщика для **claims об естественно-языковой допустимости**; если они отсутствуют — `EXTERNAL_ADJUDICATION_NOT_EXECUTED` и не сообщать реальную semantic accuracy. Синтетический oracle допускает техническую sanity проверку, но это не человеческая валидность.

### Контроли типизации/доверия: P4

Обязательно включить:
- non-existent White Star run/frame; чужой project/ref; изменённый SHA source/AST;
- `SOURCE_SPAN_TEXT_MISMATCH` контроль (действующий checker уже отклоняет);
- `Checked(hypothesis,researcher)`, unbound variables, unknown predicate symbol;
- хорошо типизированная, но источником не поддержанная формула `∀r∀h Checked(r,h)`;
- тот же α-паттерн при смене глагола: «прочитал»/«потерял»;
- `ε`/`a` для несовпадающих CF/DFA правил — регрессии контрастного поиска;
- разная интерпретация при нейтральной замене имён и неизменной семантической роли — контроль устойчивости;
- source-only success с White Star OFF (чтобы интерфейс не стал обязателен);
- source-only vs shuffled-frame placebo;
- replay frozen snapshots, проверка неизменности old numeric/symbolic/formal kernels.

### Метрики, а не декоративный «100%»

`N_sources`, `N_allowed_readings_gold`, `N_generated`, `N_Typed`, `N_trace_verified`, `N_source_supported_external`, `N_contrast_found`, `N_abstain`, `N_rejected`, `N_unknown`, `N_hallucinated_unlicensed`, `N_false_equivalence`, `N_external_annotation_missing`; confusion & set-level coverage с явным неопределённым знаменателем. Замерять `token/call/USD` когда данные доступны, model latency, worker CPU/RSS, число новых AST от White Star сверх G0 и **добавочную полезность** сверх shuffled control. Кванторные/модельные теоремы не выходят за объявленный model class.

Не считать кандидата «семантически правильным» по совпадению в одной конечной модели. Не считать `NO_COUNTERMODEL_WITHIN_BOUND` доказательством эквивалентности формул вообще. Система должна сохранять все альтернативы, даже если их finite truth vectors одинаковы.

## VII. Условия приёмки и архитектурная защита

**P0 (блокирующий):** новый `verified-origin` маршрут реально проверяет run/frame/source/AST и отвергает E3 spoof; импортное legacy API остаётся рабочим.

**P1 (блокирующий):** реальные source-aligned structural→typed candidates, минимум два разных корректных чтения одной диагностической фразы, операторные traces/добавленные предпосылки и replay. Доказать, что трасса реально участвовала в порождении, а не просто приклеена к выводу; если LLM не подключена, явно `PROVIDER_UNAVAILABLE`.

**P2:** три роли (`proposed`, `typed`, `finite checked`) раздельно; без silent collapse, не менее 36 blind-фраз, отрицательные контроли, независимый label holder. Если human adjudication нет, статус **PARTIAL, semantic generalization NOT_EVALUATED**.

**P3:** честное matched A/B/C/D. Белая звезда может оказаться не лучше. В этом случае **принимать корректность интеграции**, но **не принимать claim об улучшении смысла**; R&D продолжается без рефакторинга Белой звезды.

**P4:** старые 31 A/B gates, формальные 1024 decisions, существенная часть negative proof/replay и source checks не регрессируют, numerical75 и symbolic_v1 биты/протоколы не изменены. Изменения отдельным backward-compatible namespace, feature flag opt-in, private source/right-aware export, append-only, offline replay. Никаких разрешений execution через semantic provenance.

## VIII. Обязательные артефакты передачи

```
BASELINE_STATUS.json
MCP_SCHEMA_DIFF.json
PROVENANCE_ATTACK_MATRIX.json
SOURCE_ALIGNMENT_MATRIX.json
PROPOSAL_GRAPH_EXAMPLES.json
BLIND_SOURCE_FIXTURES.json
REFERENCE_GOLD_PRIVATE.json (не передавать production generator)
ARM_ABLATION_MATRIX.json
MODEL_CONTRAST_EVIDENCE.json
INDEPENDENT_CHECKER_RECEIPTS.json
REGRESSION_REPORT_RU.md
RCA_RU.md
IMPLEMENTATION_REPORT_RU.md
UNRESOLVED_OBLIGATIONS.md
PROMPTS_MODEL_RECEIPTS_AND_COSTS.json
REAL_FILES_CHANGED.json
```

Они должны содержать реальные run refs, SHA, byte offsets, statuses/UNKNOWN, замеренные расходы и `NOT_EXECUTED` вместо выдуманных результатов. Тестовый oracle не должен быть импортирован из продакшн генератора. Снимите git HEAD, дифф, состав файлов и установленное MCP состояние **до и после**, сохраните упакованную `delivery.zip` со всеми изменениями, ТЗ, промптом, тестами, отчётом и инструкцией rollback.

## IX. Чего нельзя делать

Не хардкодить «каждый», «одну», Nostradamus, Dyck, Read/Lost или конкретный исходник как производственные правила. Не подменять White Star автономной LLM и не называть LLM-гипотезы результатом математики. Не внедрять несуществующие `white_star→FOL` аксиомы. Не увеличивать бюджеты из-за локальной неудачи без RCA. Не менять old ledgers, numerical75, runtime binary в обход checks, не добавлять фоновые задачи без явно разрешённой конфигурации. Не выводить научную правоту/материальную реальность из логической типизации/finite countermodel.
