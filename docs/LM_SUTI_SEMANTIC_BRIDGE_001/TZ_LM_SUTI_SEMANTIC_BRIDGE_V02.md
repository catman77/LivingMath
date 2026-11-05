# LM–SUTI–SEMANTIC–BRIDGE–001
## Техническое задание: текст → версии смысловой модели → loss audit → assurance → offline replay

**Дата:** 2026-11-05  
**База:** установленный LivingMath × SUTI `v0.1.0-developer-preview`, deployment `release-v01-20261104T181130Z`; поставка `LM_SUTI_RELEASE_V01_DELIVERY.zip`; независимый живой MCP-пилот на стихотворениях Блока и Пушкина 2026-11-05.  
**Статус:** новое локальное расширение для release-preview; **не** новый proof checker и **не** обещание готового native SUTI.  
**Решение:** внедрять узкий семантический адаптер поверх текущего ядра; исследовательские статусы оставлять ограниченными.

---

## 0. Зачем эта доработка

Сегодня через новый MCP реально работают `assurance_contract`, `assurance_doctor`, проект, источник, review, candidate, check, report, export и replay. В проверке стихов были импортированы три текста, созданы адресные текстовые проверки, отличены корректные цитаты от ложных и сохранены интерпретационные гипотезы без их фиктивного доказательства. Итог одного частного проекта — 13 решений: 7 `SOURCE_ATTESTED`, 4 `REJECTED`, 2 `UNKNOWN`. Отдельный приватный самодостаточный экспорт двух стихов прошёл и `direct`, и `compiled` replay (4 проверки, 15 записей, одинаковый logical digest). Это **свидетельство работоспособности ограниченного assurance**, не автоматического понимания поэзии.

Текущие пробелы:
1. Интерпретации и их эволюция создаются вручную, а не по жизненному циклу исследовательского объекта.
2. Текстовая привязка, модель образов, альтернативные прочтения и ревизии не имеют одного typed lineage.
3. Проверка loss из ручных разметок воспроизводима, но provenance того, **кто и как получил разметку**, не структурирован как first-class объект.
4. Для литературной интерпретации пришлось использовать `EMPIRICAL_HYPOTHESIS` → `UNKNOWN`; это не подходящий пользовательский термин, хотя безопасный assurance-результат.
5. Старый `research_autonomy_ingest(general011)` через текущий клиент не прошёл строгую валидацию metadata/rights. **Нельзя выдавать это за успешно испытанный native literary runtime**.

**Цель:** из зафиксированного текста строить последовательные версии смысловой модели, явно хранить альтернативные гипотезы, обнаруживать изменение/утрату существенных различений при преобразовании представлений и публиковать воспроизводимый артефакт, который **проверяет источниковую и структурную дисциплину**, но **не удостоверяет литературоведческую истину**.

**Не цель:** победить базовую LLM; выжать 0.6B; реализовать всю SUTI/Syntaxium; доказать «истинный смысл» стихотворения; привязать Блока к физическому циклу; строить новую DSL/онтологическую иерархию; менять математическую семантику frozen checker; выдавать `PROVED_FORMAL`/`CHECKED_FINITE` интерпретациям; автоматически закрывать release-gate R3.

## 1. Неподвижные ограничения и поверхность интеграции

- Не редактировать `src/lm_suti_assurance/_frozen/**`, frozen schemas и `BASELINE_LOCK.json`; не меняются verifier digest `a035303149c1307126ff26e4bf60725daf3b104598be8a04a958e14388a61f08` и binder digest `8c760eeaa960cc4a2eb227ee1669d004f82db8e6e51ce871caaaa1b79c39105a`.
- Существующие `SourceSnapshot`, `task review`, `CandidateRecord`, `AssuranceDecision`, append-only ledger, source/policy permission и export/replay являются источником истины для фактических проверок. Новые интерпретационные записи — **производные приложения**, не альтернативный checker.
- Новые поля/схемы и адаптеры располагаются в новом модуле, например `src/lm_suti_assurance/semantic_bridge/` и в `docs/semantic-bridge/`; CLI/MCP команды — только добавочные, с сохранением прежних контрактов 55 tools. Сначала QA, не подменять production server, не разворачивать новую конфигурацию без отдельного rollout gate.
- Один установленный hosted proposer с реальной доступностью; ручные гипотезы — равноправный режим. Если автоматическая генерация недоступна, записать `MODEL_UNAVAILABLE`, сохранить ручные фикстуры и **не** зачесть их как автоматические шесть прочтений. Никаких benchmark-гонок разных моделей.
- Никаких ключей, OAuth-токенов, исходных приватных SQLite и персональных данных в экспортируемом bundle. Все действия read-only относительно внешнего мира; `execution_permission=false`.
- `SOURCE_ATTESTED` относится только к точным source fields/spans. `LOSS_DETECTED` относится только к заявленным структурным representation records и declared query family. `UNKNOWN`/`HOLD` для содержательной интерпретации — корректные результаты. Научная или художественная правдоподобность этих гипотез проверяющим механизмом не доказывается.

## 2. Требуемая минимальная архитектура

```text
Fixed SourceEditionSnapshot (immutable exact UTF-8 + edition + rights)
  ├─ Line/Span Index (byte offsets, exact quotes, Unicode-preserving)
  ├─ Interpretation Generator [hosted LLM OR manual] (untrusted)
  │    └─ Candidate frames / alternate readings / suggested revisions
  ├─ Semantic Bridge Binder (deterministic, validates evidence refs)
  │    └─ SemanticFrame v1 + RevisionEdge + InterpretationLedger
  ├─ Comparison & Loss Auditor (deterministic for declared typed fields)
  │    └─ StructuralLossWitness or UNDETERMINED/NOT_APPLICABLE
  ├─ Existing Assurance Facade (source claims / hypotheses only)
  │    └─ SOURCE_ATTESTED / REJECTED / UNKNOWN / HOLD
  └─ Immutable Bundle + direct/compiled OFFLINE replay (no LLM)
```

Нельзя внедрять модельно-генерируемые source hashes, task refs, byte spans или права как доверенные поля. Детерминированный binder заполняет ссылки/rights/scope из ранее импортированных аутентичных snapshots. Сам генератор отвечает за гипотезы, признаки, relations, контрпрочтения; *binder не выбирает вместо него верное литературное содержание*.

## 3. Формальные объекты и контракты

Каждый объект версионируется, имеет строгую JSON Schema, `schema_version`, `project_id`, `source_snapshot_digest`, `origin_kind`, `producer_ref`, `created_by`, `parent_refs`, `content_digest`. Запрещены неизвестные поля в доверенном ядре. Использовать `sha256` от канонически сериализованного объекта; само исходное стихотворение сохраняется как исходные **байты**, не как переотформатированный текст.

### 3.1 SourceEditionSnapshot / SourceAnchor

`SourceEditionSnapshot`: `source_id`, `author`, `title`, `edition`, `editorial_source_url`, `content_utf8` (либо приватная immutable зависимость), `source_sha256`, `rights.origin`, `rights.status`, `rights.can_embed`, `rights.attribution`, publication policy, `provenance`.

`SourceAnchor`: `(source_ref, source_sha256, byte_start, byte_end, quote_utf8, quote_sha256, unit=source_utf8_bytes)`. В валидаторе обязателен точный инвариант:

\[
\mathrm{UTF8Bytes}(source)[a:b]=\mathrm{UTF8Bytes}(quote),\quad
\mathrm{sha256}(quote)=quote\_sha.
\]

Значения `a,b` — полуоткрытый интервал в UTF-8 байтах. Unicode-нормализация, переносы строк и `е/ё` **не исправляются молча**. При несовпадении вернуть `SOURCE_ANCHOR_MISMATCH`. Нумерация строк — лишь вторичный навигационный индекс с версионированным правилом разбиения. Привязка к «изданию» — declaration источника, не независимая текстологическая экспертиза.

### 3.2 SemanticFrame v1

Поля:

- `frame_id`, `poem_ref`, `revision_index`, `parent_frame_ids`, `generator_ref`, `generation_mode` (`HOSTED_MODEL`/`MANUAL`/`FIXTURE`), `seed_or_unknown`, `model_version_or_unknown`;
- `claim_atoms[]`: `{id, kind: LITERAL|FORMAL_STRUCTURE|INTERPRETATION|UNRESOLVED, text, source_anchor_refs[], premises[], epistemic_status, alternatives[]}`;
- `motifs[]`: явно объявленные элементы и source references, не «истинные» литературные сущности;
- `relations[]`: например `PRECEDES`, `REPEATS_MOTIF`, `CONTRASTS`, `CHANGES_SPEAKER_ROLE`, `CAUSES_IN_NARRATIVE` как **interpretive labels**, с адресными свидетельствами и уровнем вывода;
- `temporal_reading`: `cyclic|spiral|linear|ambiguous|unspecified` **как предложенная интерпретация**, а не статус факта;
- `scope`, `assumptions`, `limitations`, `open_questions`, `counterreadings[]`, `declared_observables[]`;
- `source_bindings`, `projection_contract_refs`, `status=PROPOSED|REVISED|CHALLENGED|WITHDRAWN` (workflow status **не** научный assurance).

`LITERAL` получает независимую source-check, если его machine term корректно связан. `FORMAL_STRUCTURE` проверяется только когда заявлен точный, поддержанный finite/source контракт; иначе `HOLD`. `INTERPRETATION` в assurance маппится на недоказанную гипотезу, возвращает `UNKNOWN`/`CONDITIONAL_HYPOTHESIS` без фактической верификации содержания. `UNRESOLVED` остаётся `UNKNOWN`.

### 3.3 RevisionEdge / lineage

`RevisionEdge` фиксирует `parent_frame`, `child_frame`, `operation` из `ADD|REFINE|RELABEL|WITHDRAW|BRANCH|MERGE`, `rationale`, `new_source_anchor_refs`, `added_claims`, `withdrawn_claims`, `changed_relations`, `preserved_claims`, `changed_scope`, `claimed_invariants`, `loss_witness_refs`, `status_before/after`, `producer_ref`.

Ни одна версия не переписывает предыдущую. Изменение исходного текста, его редакции, права или scope → **новая source/version/task**, не скрытый rebase. В графе необходимо обнаруживать циклы, ссылку на отсутствующего родителя, ссылки на чужой проект, merge без конфликта/разрешения и попытку улучшить epistemic status без нового assurance verdict.

### 3.4 ProjectionContract / StructuralLossWitness

Проекция \(P_Q\) явно объявляет **какие поля** сохраняются, а семейство вопросов \(Q\) — **что пользователь вправе требовать** после проекции. Для структурных записей loss имеет точный смысл:

\[
\exists u,v, q\in Q:\ P_Q(u)=P_Q(v)\ \wedge\ q(u)\ne q(v).
\]

Выход `LOSS_DETECTED` допускается только при предъявлении source-bound пары `u,v`, конкретного `q`, совпадающих проекций и различающихся ответов. Для отсутствия обнаруженного witness не утверждать абсолютную losslessness: `PRESERVED_FOR_DECLARED_Q` только при исчерпывающей проверке явно ограниченного Q/допущенного домена; иначе `UNDETERMINED`/`NOT_CHECKED`.

**Семантическая интерпретация — особый случай:** если `q` («мир буквально возвращается в то же состояние») сам не формализован/не верифицируем, разрешён только `HYPOTHESIZED_SEMANTIC_LOSS`, не `SOURCE_ATTESTED`, не научная теорема. Отдельно сохранять loss из обрезанного источника, loss из человеческой разметки и loss из предложенной теории.

### 3.5 ResearchDossier и отчёт

Обязательный выход: входная редакция и SHA, шесть версий прочтений, timeline версий, конкурирующие интерпретации, таблица исходных опор, карты изменённых/сохранённых различений, ledger ошибок/сомнений, source/assurance verdicts, exact input/output model receipts, bundle manifest, replay tool identities, declared limitations. Не выдавать один «канонический смысл» за математическую истину.

## 4. Контрольный корпус — шесть прочтений

Источники привязать к одному выбранному достоверно идентифицированному публичному тексту и **заморозить до генерации**. Для первой QA использовать:

1. А. Блок «Ночь, улица, фонарь, аптека» — редакция собрания сочинений 1960; URL/байты/sha записать.
2. А. Пушкин «Анчар» — выбранная редакция с полным текстом, включая последовательность яд → раб → стрелы; URL/байты/sha записать.
3. А. Пушкин «Я вас любил» — выбранная редакция, текст и SHA зафиксировать.

**Шесть обязательных проходов = по два последовательных чтения каждого стихотворения.** В каждом первом проходе генератор строит самостоятельный `SemanticFrame v1`; во втором получает тот же полный источник, первую версию и независимое диагностическое задание (контрчтение, потерянное различение или недостающий scope) и предлагает revised frame с `RevisionEdge`. Второй проход не должен автоматически заменять первый. Для каждого произведения обязательно хотя бы одно альтернативное прочтение (не синонимическая перефразировка) и хотя бы одна содержательная неустранимая в текущем контракте неопределённость.

Ожидаемые **диагностические вопросы, не готовые gold-интерпретации:**

| Источник | Чтение 1 | Чтение 2 / adversarial challenge |
|---|---|---|
| Блок | Какие буквальные и образные повторения можно адресовать? | Откуда следует/не следует тождество мира? Чем отличаются порядок образов и смысловое прочтение «замкнутого цикла»/«спирали»? |
| «Анчар» | Какова последовательность события и действующих лиц? | Не подменяется ли «образ насилия/власти» утверждением о физической причинности? Какие альтернативные агенты и направления передачи действия допустимы? |
| «Я вас любил» | Какие эмоции и высказывания прямо присутствуют? | Чем отличается сообщение о чувстве от речевого действия отказа тревожить адресата? Не выводится ли недоказанная биографическая мотивация? |

Не вкладывать эти ответы в prompts как решения — только вопросы на втором проходе после первого frozen candidate. Любую интерпретацию привязывать минимум к одной настоящей исходной цитате либо помечать `UNSUPPORTED_INTERPRETATION`. Проверять возможную ошибку авторства/издания, если цитаты не найдены в зафиксированном источнике; не подменять редакции «как должно быть».

## 5. Обязательные negative/positive проверки

### A. Source integrity

- На каждом из трёх источников byte offsets/quote hash точны; Unicode, длинное тире и `ё` сохраняются.
- Подменённая строка, off-by-one, другая редакция, устаревший snapshot digest и выдуманный источник отвергаются.
- Реальная противоположная фраза у Блока или Пушкина не получает `SOURCE_ATTESTED`.

### B. Structural loss

- Для двух вручную или модельно заявленных структурных записей Блока одинаковый набор образов и разный порядок/дополнительные детали: проекция на `image_set` выдаёт адресный `LOSS_DETECTED` и конкретный witness; `PRESERVED_FOR_DECLARED_Q` для полного Q отвергнут.
- Другая проекция, сохраняющая и набор, и порядок, не должна давать ложный loss из-за сортировки JSON-ключей.
- В отрицательном контроле `P_Q` не теряет никакое различение из Q: не объявлять loss ради KPI.
- Неподтверждённая интерпретация об онтологическом повторении остаётся гипотезой.

### C. Interpretation and lineage

- 6 последовательных чтений действительно получены модельным proposer; если модель недоступна, gate честно `BLOCKED_MODEL_UNAVAILABLE` (ручные фикстуры не засчитывать).
- Чтения 2 имеют законные родители, изменение точно записано; нельзя задним числом переписать чтение 1.
- Альтернативы существуют и могут сосуществовать; отсутствие единого победителя — PASS.
- Контрпример подрывает предпосылку только в пределах её scope, не удаляет всю модель автоматически.
- Запрос «докажи буквально тот же физический мир Блока» → `UNKNOWN`/`HOLD`, не `CHECKED_FINITE`.

### D. Existing assurance and offline export

- `assurance_doctor` PASS и прежние source/finite/replay regression без изменений; исторический ложный `ENTAILED` (23/24) остаётся REJECTED/UNKNOWN с контрмоделями.
- Полный приватный bundle включает только разрешённые исходные байты и проходит прямой + compiled replay с одинаковым logical digest, без модели и сети.
- Bundle без включённых источников должен явным образом возвращать `MISSING_SOURCE_DEPENDENCY` — не подменять пустым источником и не объявлять PASS.
- Изменение одного source/span/frame/edge byte вызывает ожидаемый integrity failure.
- Изменение только необязательных generator metadata **не** меняет существующий assurance verdict; новая семантическая версия при этом сохраняет собственный digest и provenance.
- Нет секретов в артефактах, нет execution grants, нет `PROVED_FORMAL`, нет автоматического R3 PASS.

## 6. Implementation scope и тестируемый пользовательский путь

Рекомендуемый модуль:

```text
src/lm_suti_assurance/semantic_bridge/
  schemas/              # versioned new schemas
  anchors.py            # UTF-8 byte/line index
  frame.py              # typed frame validation
  proposer.py           # hosted/manual; untrusted
  binder.py             # deterministic source/task binding
  lineage.py            # revisions, graph integrity, append-only
  compare.py            # typed projection and counter-witness
  report.py             # Russian MD + JSON
  bundle.py             # additive semantic files, existing replay kept
  facade.py             # CLI/MCP additive commands
```

Конкретные имена допускается адаптировать к репозиторию после inspection; не писать параллельный runtime, если существующий facade расширяется минимально.

Минимальный CLI сценарий:

```text
lm-suti project new ...
lm-suti source add ...
lm-suti semantic draft --project ... --source-ref ... --phase initial
lm-suti semantic revise --project ... --frame-ref ... --challenge ...
lm-suti semantic compare --project ... --left ... --right ... --projection ...
lm-suti semantic report --project ... --output ...
lm-suti export --project ... --audience private --output ...
lm-suti replay ... --offline --engine direct
lm-suti replay ... --offline --engine compiled
```

Если CLI обёртка экспортирует команду иначе — документировать настоящий вызов и держать эквивалентный end-to-end. MCP инструменты можно добавить только после прохождения CLI QA; предусмотреть повторное подключение tool schema и права пользователя, не считать deployment готовым по локальному unit-test.

## 7. Приёмка / Go–No-Go

**M0. Контракт и baseline:** PRE_FLIGHT: exact installed version, hashes, доступность proposer, release scope, source-rights, snapshots, возможные точки адаптации. До изменения кода — lock.

**M1. Source and frame:** immutable UTF-8 source, spans, schema validation, six typed frames и append-only lineage.

**M2. Evidence/loss:** адресные claims, loss witnesses; нет ложного promotion и нет смешения declared annotations с доказанным авторским смыслом.

**M3. Offline research dossier:** один bundle с 3 произведениями и минимум 6 прочтениями, verifiable source checks и structural checks; replay `direct`/`compiled` без LLM; private rights соблюдены.

**M4. Release QA:** регрессии существующего ядра, negative/adversarial matrix, README Quickstart, независимое повторение на другом чистом окружении; никакого production rollout до отдельного gate. R3 human pilot остаётся PENDING.

**Hard rejection:** редактирование frozen checker; status promotion `INTERPRETATION→PROVED_FORMAL/CHECKED_FINITE`; несуществующие source anchors; несвязанные права; потеря истории/отрицательных гипотез; невозможность offline replay при заявленной self-contained поставке; ложное утверждение об исполнении полного SUTI; скрытая замена исходного текста.

**Вторичные метрики:** доля адресуемых claims, число реконструируемых versions, count confirmed losses vs hypothesized, нарушения provenance (целевой 0), удобство ручной проверки, стоимость генерации; **не** семантическая accuracy относительно несуществующего единственного «золотого смысла».

## 8. Deliverables для Codex

1. `USER_REPORT_RU.md` — что реально создано, 6 frames, какие источники/версии, scope и реальные статусы.
2. `RCA.md` — ошибки, причины, починенные и непочиненные ограничения; особое внимание source/span и literary status.
3. `IMPLEMENTATION_AND_CHANGED_FILES.md`, `CAPABILITIES.json`, `BASELINE_AND_PRECOMMIT.json`, `MODEL_ATTEMPTS.jsonl`, `COSTS.json` (unknown usage не 0).
4. `SOURCE_SNAPSHOT_LEDGER.json`, `SEMANTIC_FRAMES.jsonl`, `REVISION_EDGES.jsonl`, `ALTERNATIVES.json`, `LOSS_WITNESSES.json`, `ASSURANCE_DECISIONS.json`, `POETRY_REPORT_RU.md`.
5. `SOURCE_AND_RIGHTS_AUDIT.json`, `INTEGRITY_AND_REPLAY.json`, direct/compiled offline replay transcripts, test results.
6. `demo_poetry_private.zip` с readme и executable offline replay (без секретов), если права допускают; если нет — rights-safe экспорт и явно отсутствующие зависимости.
7. Машинно-проверяемый SHA-256 manifest поставки; исходные release архивы и историю не редактировать.

**Конечный итог:** работающий, честно ограниченный текстово-семантический адаптер поверх v0.1. Не «доказательство правильной трактовки Блока/Пушкина», а воспроизводимая история исследовательских прочтений и их структурных потерь.

### Приложение: контрольные исходные байты

В пакет входит `POETRY_QA_FIXTURES.json` — **рабочие транскрипции**, взятые из предшествующей живой QA-проверки. Их `raw_text_sha256` относится к строкам `raw_text_utf8`, а предыдущий пилот использовал JSON-контейнер с собственным SHA. Не смешивать эти идентификаторы и не считать автоматически подтверждённой редакцией. На E0 выбрать точный вариант каждого стихотворения, документировать byte-for-byte сверку с доступным источником (если недоступна — `EDITION_UNVERIFIED` и ограничить assurance claims транскрипцией), лишь затем запускать модельные чтения.
