# LM-NL-PROPOSER-002 — причинный анализ и новые эксперименты

Дата: 2026-11-07. Статус: **новые опыты на действительно подключённом MCP v0.4.9**, а не демонстрационные результаты эталонного Python. Каждый run_ref указан в `evidence/LIVE_RUNS.json`. Производственный патч не применялся.

## Исходная база

Живая приёмка Formal Bridge v1 ранее дала CFG/DFA/контрмодели, сохранение forest, контрастные запросы, независимые проверки и replay. `formal_bridge_v1.semantic_proposer` в `bridge_system_status`: `EXPLICIT_HUMAN_OR_IMPORTED_PROPOSALS; no general NL decoder`. `formal_interpret` — хранилище **явно присланных** FOL предложений. `white_star_symbolic_explore` — работа с токенными историями без LLM и без собственного FOL-декодера. Численная `white_star_explore` принимает **заранее заданные** концепты/2D оси/координаты.

### E1: Лексический контраст при одинаковом α-паттерне

Источник (UTF-8 SHA `f4b1839d56e9f039553d03a70951007fed2cdfb948c9bab899e8daba80e8a60d`):

```
Каждый студент прочитал одну книгу.
Каждый студент потерял одну книгу.
```

`white_star_symbolic_explore`: FREE, whitespace, две строки, local α, seed 2211, 30 шагов, 3 кандидата/шаг, без обучающих меток. Реальный `run_id=5ad2cad63f84ba9a5f1988fa5ba348e5e0f7dabbb2df4fbfbf28d3dbc1690756`.

Результат: 89 узлов, 90 попыток кандидатов, 32 α-класса, 198 свидетелей, `empirical_claims=0`, `grammar.status=UNDERDETERMINED`, `evaluation=UNASSESSED`, `LLM_calls=0`.

Точные source-bound claims: `literal_word_equality=false`, `alpha_equality=true` (обе строки имеют паттерн `[0,1,2,3,4]`), полная наблюдательная сигнатура различается благодаря буквальному глаголу. **От α-эквивалентности не следует семантическая эквивалентность.** Движок не предложил формулы `Read`/`Lost` или кванторные области действия.

### E2: Численная Белая звезда со смысловыми осями, заданными извне

Текст: «Каждый исследователь проверил одну гипотезу», SHA `1bfb913518481ba0899018a463ab11fecb272ae1703d9139dc1f0ba27fc07389`. Концепты (`Каждый`, `проверил`, `одну`) и их byte spans привязаны к исходнику. Оси `scope`/`cardinality` и координаты **выбраны исследователем**. Seed 42, 24 шага, 4 кадра.

Run A `a918c1cce18e69213a710f87cfb1b2ebbb1cb60498a825afc355f81e9e63f4bc`: `beta0=1`, `beta1=1`; первые 4 декодируемые отношения содержат `ALIGN` и `TENSION`, 4 frame slots, `LLM_calls=0`.

Run B `a4339a511499861e93762cca957887a8cf46d8e80384a9889a1d8cb5cff058d1`: тот же буквальный источник/seed/протокол, **менялись лишь координаты понятия «одну»**: `[1,2]` → `[-1,-2]`; `beta0=1`, `beta1=0`, первый link `ALIGN` → `TENSION`, другой result_digest. Проверка численной зависимости от энкодера, НЕ мера семантической полезности.

Decoder выдаёт `CREATIVE_RELATION_PROPOSAL_NOT_SOURCE_ENTAILMENT`, элементы `ALIGN/TENSION/UNRESOLVED`, numeric graph/frame и **не содержит** типизированных FOL-формул. Любой текстовый/логический decoder должен быть отдельным явным кандидатом с provenance, а не называться уже реализованной частью Белой звезды. Нет основания считать signed_weights вероятностями интерпретаций или truth scores.

### E3: Разрыв provenance: фиктивный White Star run принимается как декларация

`formal_store(kind=source)` создал source_ref `fe7631a5996d7d8de27822346399c7934ca1ee4c251f5a1ef6872e3e801c23a4`. Подан корректный типизированный FOL AST с `candidate_provider.kind=white_star`, но provenance намеренно содержит несуществующие `run_id=000...000`, `frame_id=F99` и такой же несуществующий источник деривации.

Результат `formal_interpret`: `PROPOSED`, кандидат `4ec4f88ba9e9a4a36c76462fb46da55d965a6dfc77e4bcaa98a800b14449645f`; `type_status=TYPED`, `semantic_alignment_status=PROPOSED`. Для текущего контракта это **ожидаемое декларативное поведение**, а не «провал существующего чекера». Но будущая автоматическая связка обязана проверять **реальное** происхождение, а не доверять тексту `provider.kind`.

### E4: Типизация допускает содержательно неверную (но корректную) формулу

Для той же фразы подана формула `∀r:Researcher ∀h:Hypothesis Checked(r,h)`, утверждающая, что каждый проверил все гипотезы. Она корректно типизируется и сохраняется `PROPOSED`, `TYPED` (run `67a98f030eebc87650d58b812f929f119d6856959315ec2ae8c404495677bbad`). **Типизация не подтверждает близость значения к источнику.** Семантические ограничения, лицензируемые числительным и лексикой, нужны как проверяемые hypotheses/assumptions с контролем допустимости/внешней аннотацией.

### E5: Проверка неверной привязки source span

Контрпример `literal='Каждый', byte_utf8=[13,39]` в действительности ссылается на «исследователь». `formal_interpret` отверг запрос как `SOURCE_SPAN_TEXT_MISMATCH`. Эта часть защиты уже существует; НЕ ДУБЛИРОВАТЬ с нуля, а сохранить и интегрировать в новый конвейер.

## RCA / минимальные исправления

1. **MISSING_DECODER:** между White Star frames / symbolic histories и typed FOL/CFG AST отсутствует контракт `decode/expand → typed candidate + ancestry`. Требуется новый явный адаптер/пропозер; нельзя приравнивать `ALIGN` к `∀`, а знак веса — к отрицанию.
2. **PROVENANCE_IS_DECLARATION:** `provider.kind=white_star` — декларация пользователя, а не криптографическая цепочка реальных run/frame. Для *автоматически промотируемых* кандидатов нужен `verified origin receipt` с существующими refs, immutable SHA, frozen source, frame/trace, bind to candidate AST hash; для стороннего импорта оставить `DECLARED_UNVERIFIED`.
3. **SEMANTIC_GROUNDING_OPEN:** checker проверяет типы и истинность в конкретной модели, но не соответствие смыслу исходной фразы. Нужно развести `source-aligned`, `typechecked`, `externally-adjudicated`, `finite-model consequence`. Ни одно из этих свидетельств поодиночке не доказывает intent автора.
4. **ENCODER_SENSITIVITY:** геометрическое поведение Белой звезды сильно зависит от ручной разметки; полезность требует контролируемых A/B сравнений: source-only, WhiteStar, shuffled frame, placebo coordinates при равных LLM calls/tokens.
5. **CONSTRAINED_LANGUAGE:** нынешний FOL typed signature позволяет формально корректные, но source-unsupported формулы. Нужна проверяемая карта терминов/ролей, допускающая `UNRESOLVED` и несколько разборов; запрет хардкода нужной фразы в продукте.

## Последующее тестирование (до публикации результатов)

- Публичные claims: `PROPOSED` (генерация), `TYPED` (формальный AST), `CHECKED_INSTANCE` (проверка на модели), `EXTERNAL_SEMANTIC_JUDGEMENT` (отдельный независимый эксперт). НИКАКОГО `VERIFIED_SEMANTICS` из контрмодели.
- Не менее 36 русскоязычных фраз в слепой тестовой программе; часть семейств — semantic minimal pairs, некоторые — без корректного FOL прочтения в выбранной сигнатуре.
- Невозможность reconstruct missing signature/lexicon → `NO_WELL_TYPED_DECODING`, `SOURCE_UNDERSPECIFIED`, `ABSTAIN`; внешняя ручная формализация сохраняется как baseline.
- Исходники и протоколы можно replay без загрузки авторизованных LLM повторно; LLM receipts отдельно и никогда не превращаются в теорему.
