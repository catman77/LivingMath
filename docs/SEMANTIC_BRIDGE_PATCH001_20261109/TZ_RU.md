# Техническое задание — SEMANTIC-BRIDGE-PATCH001

**Тип:** небольшой, добавочный, opt-in патч действующего MCP-сервера LivingMath.  
**Цель:** превратить уже проверенный цикл «LLM предлагает интерпретации → MCP проверяет формальные отношения/сценарии → LLM оценивает смысл» в воспроизводимый штатный интерфейс.  
**Основание:** `reference/SEMANTIC_BRIDGE_V0_RU.md`, `reference/SB_EXP01_REPORT_RU.md`, `reference/SB_EXP01_FROZEN_INPUT.json`, `reference/SB_EXP01_VERIFY.py`.  
**Репозиторий:** `catman77/LivingMath`; baseline SHA `e65b1a1e06914d63f6048a04b5e065a610adb68d`.  
**Статус документа:** проектная спецификация. Примеры новых MCP-методов ниже **не** означают, что они уже существуют.

## 0. Исследовательская постановка и чёткая граница ответственности

Внешняя LLM читает естественный текст вместе с контекстом, выбирает язык представления, создаёт множество конкурирующих интерпретаций и при необходимости предлагает новые сценарии. MCP принимает эти объекты **как недоверенные данные**, сохраняет их с provenance, строит только формально проверяемые отношения между ними, находит/проверяет контрмодели, отдельно оценивает предпосылки и возвращает нерешённые обязательства. Внешняя LLM получает отчёт и может создать новую версию кандидата. Сервер не выбирает «истинное прочтение», не ранжирует по смысловой правдоподобности и не генерирует формулы через LLM.

В `formal_bridge/fol.py` уже есть `typecheck`, `evaluate`, `countermodels`, `check_source`, `check_link`; в `formal_bridge/service.py` — source/candidate ownership, idempotency, CAS и replay. Использовать их, а не дублировать математический kernel. Дополнительный код — только строгая оболочка и точные структурные проверки. В старом NL-мосте `decoder.py:build_move` только переставляет кванторы по порядку байтовых source links; это **не** заменяет новый механизм. Старая NL-программа и её `matched_ablation` сохраняются неизменными.

### Обязательные инварианты

- `TYPECHECK_OK`, `SOURCE_SHA_MATCH`, `TRACE_LINK_CHECKED`, `REPLAY_MATCH` и `FINITE_SAME_ON_BOUND` никогда не повышаются до `SOURCE_MEANING_VERIFIED`.
- Величина `assumption_truth` хранится отдельно от `formula_truth`. Если `formula_truth=TRUE` и `assumption_truth=FALSE`, итоговая применимость `CONTEXT_INCOMPATIBLE`; это **не** ложность самой формулы.
- `UNKNOWN_BOUND`, `OPEN_WORLD_UNKNOWN`, `LANGUAGE_INSUFFICIENT`, `NOT_PROVED` не переименовываются в `FALSE`/`EQUIVALENT`.
- Равные AST или α-нормальные формы можно использовать для доказательства лишь заявленного структурного отношения; **записи гипотез, source spans, предпосылки и истории НЕ объединять**.
- Любой `PROVED_*` требует проверяемого proof certificate и отдельной повторной проверки либо воспроизводимой точной процедуры.
- Ни один новый метод не вызывает LLM, Интернет или физическое выполнение действий. `execution_permission=false`, `LLM_calls=0` во всех результатах.
- Неизвестный/неподдержанный оператор AST не исправлять произвольной заменой. Вернуть `LANGUAGE_INSUFFICIENT` и зафиксировать указанный LLM source fragment или `TYPE_REJECTED` с явной причиной; не симулировать поддержку модальности/времени.

## 1. Scope — строго небольшая надстройка

Создать новый изолированный пакет `src/lm_suti_assurance/semantic_bridge/` с модулями `contracts.py`, `alpha.py`, `relations.py`, `service.py`, `mcp.py` и тестами. Допускается один узкий additive hook для регистрации tools/capabilities в фактическом entrypoint, определённом после чтения current tree. В существующих `formal_bridge`, `symbolic_v1`, `udav_core`, `white_star`, `nl_proposal` допускаются **только** минимальные исправления доказанного интеграционного дефекта, с регрессионным покрытием и отдельной записью в отчёте. Предпочтительнее вообще не трогать эти пакеты. Native C++/численное ядро запрещено изменять.

Новые методы **ровно четыре**, все opt-in, нейтральные к поставщику LLM:

1. `semantic_bridge_register`: зарегистрировать immutable партию интерпретаций к одному source_ref.
2. `semantic_bridge_analyze`: проверить запрошенные пары гипотез и явные модели-сценарии.
3. `semantic_bridge_inspect`: read-only summary/graph/obligations/checks/bundle, с явной пагинацией.
4. `semantic_bridge_replay`: восстановить и перепроверить сохранённый анализ при точном kernel binding, без LLM.

Если в репозитории уже есть одноимённая функциональность, сначала сопоставить реальные схемы; не плодить дубль API. Строгие схемы с `additionalProperties:false`, bounds, обязательными SHA/refs; использовать текущую инфраструктуру JSON Schema и FastMCP. Подробные формы в `API_EXAMPLES.json` — контрактные образцы, необходимые поля уточнить по реальному DTO, но не ослаблять смысловые инварианты.

## 2. Входные сущности

### 2.1. `ContextualHypothesis/1`

Поля: уникальный в рамках партии `client_id`, `source_ref` (общий), `language="FOL_V1"`, `formula_ast` **либо** явный `unsupported` с причиной, `assumptions` (список типизированных закрытых FOL AST), `source_links` (массив `{byte_utf8:[start,end],literal,ast_path?,role?}`), `construction_trace` (непустой пользовательский provenance), `obligations` (массив `SemanticObligation/1`), `creator` (`external_llm|human|imported`, только декларация). Не смешивать `literal` source evidence и интерпретацию `role`. Если связь с AST-узлом передана, проверить существование JSON пути и точный byte span; *никаких* автоматических семантических лицензий.

Сущность `SemanticObligation/1`: `{id,kind,description,source_links?,status:"OPEN",assumption_ast?}`. `kind` минимум: `PRESUPPOSITION`, `ANAPHORA`, `SCOPE`, `NEGATION_SCOPE`, `TEMPORALITY`, `LANGUAGE_GAP`, `CONTEXT`, `LEXICAL_ASSUMPTION`. Для `assumption_ast` требуется отдельный FOL typecheck; свободные переменные запрещены. Выражения вне текущего языка сохранять как описание `LANGUAGE_GAP`, не подсовывать фиктивный AST.

Результат регистрации: `batch_ref`, `hypothesis_refs`, `source_sha256`, типовые проверки, список невалидных/невыразимых пунктов, неизменяемый журнал. Запрещено silently drop `TYPE_REJECTED`: клиент обязан увидеть `client_id` и причину. Допустима **атомарная регистрация** всех валидных+отклонённых metadata-узлов (не пытаться прогонять отклонённые AST через matcher); при невалидном SHA/source/ownership запрос целиком отклонять.

Пределы v0: 1 источник, до 6 гипотез, до 8 обязательств на гипотезу, до 16 source links/гипотезу, не больше текущего `formal_bridge` AST-node cap и глубины. Указанные числа — начальные **предложения**, не ухудшать текущие системные пределы; отклонённые по budget сущности возвращать статусом. Для упрощения реализации разрешено использовать существующий `formal_interpret`/`fol.propose` при регистрации валидных FOL кандидатов и хранить `formal_run_ref` как provenance. Не модифицировать старые результаты и ID.

### 2.2. Модели-сценарии

LLM может передать `model_refs`, предварительно зарегистрированные через `formal_store(kind=model)`, и список `pair_ids`. Только модели того же проекта; принадлежность должна подтверждаться через `FormalService.owned`, не сравниванием строковых SHA. Источник сценария — явно заявленное `LLM_PROPOSED`, `HUMAN_PROVIDED` или `FORMAL_COUNTERMODEL`. Закрытость мира обязательна для `TRUE/FALSE`; `open` возвращает `UNKNOWN`.

## 3. Обязательный порядок проверки отношений

### P0. Точный α-checker (новый, без full model enumeration)

Для **типизированных** FOL AST определять α-эквивалентность по структуре дерева и индексам де Брёйна (или эквивалентному каноническому представлению с лексическим окружением). Ключ включает `quant`, сорт связанной переменной, идентичность предиката, позиции аргументов, логический оператор, порядок дочерних узлов (не сортировать `and`/`or` без отдельного доказательства). Для переменной — лексический индекс binder от текущего узла, не буквальное имя. `typecheck` действующего FOL вызывается до канонизации; неверно связанные и теневые переменные не проходят. Не выполнять непродуманное текстовое `str.replace`.

В proof certificate: `rule=ALPHA_NORMALIZATION`, `checker_version`, `input_formula_sha256_left/right`, `canonical_sha256_left/right`, `signature_sha256`, `result=PROVED_ALPHA_EQ`; повторная проверка строго реконструирует canonical из неизменных AST. Норма H0/H2 из SB-EXP01 совпадает независимо от переменных `r,m,h` vs `u,v,t`. Контроль H0/H1 **не** α-эквивалентны. Для α-пары количество вызовов `formal_contrast`/finite-model enumerator = **0**.

### P0. Пропозициональная проверка следования в узком доказуемом классе

Опциональной **универсальной теоремой** разрешено объявлять только формулы, которым проверяющий предъявил точный сертификат; v0 должен поддерживать по меньшей мере случай *одинаковая цепочка только `forall`-кванторов по одинаковым сортам (с α-согласованием) + матрица из `and/or/not/eq/pred` без внутренних кванторов*. Для входных формул `A` и `B` доказать `A=>B`, проверив тавтологичность `body(A) -> body(B)` по всем булевым значениям **атомов в общем окружении**, при числе независимых атомов ≤ заданного малого лимита (например, 10). Это корректное достаточное условие глобального следования, даже если не всякая атомарная комбинация реализуется в реальной модели. Предикаты индексировать по имени и **связанным аргументам/позициям**, а не по локальным именам переменных. Равенство считать атомом только как консервативную абстракцию; если схема равенств требует специальных допущений, возвращать `UNKNOWN_UNSUPPORTED_PROOF_CLASS`, а не ложный verdict.

Доказательный сертификат `PROVED_ENTAILMENT` должен включать sha обеих нормализованных матриц, сортированный набор атомов, количество проверенных строк (`2^k`), версию независимого проверяющего. Отдельно проверить обратное направление, не делать его выводом из прямого. Для H1=>H0 (SB-EXP01) достаточно 4 булевых атомов и 16 строк; направление H0=>H1 опровергается контрмоделью. **Не** объявлять широкую полноту по FOL.

Если реализовать этот узкий proof fragment без риска изменения existing core невозможно, допускается пометить его `P1` в отчёте, но тогда gate `G3` остаётся FAIL, и пакет **не принимается как завершённый по настоящему ТЗ**. Приоритет — корректность, не искусственная галочка.

### P0. Различающие модели

Для неэквивалентной пары и неизвестных направлений использовать **существующий** `formal_contrast` (в его текущей замкнутой конечной модели и bounds) или его одноимённый pure `fol.countermodels` в существующем изолированном worker. Не переносить большой поиск в HTTP event loop. Проверять каждую возвращённую модель независимо через существующий `fol.evaluate` для обеих формул и всех assumptions, и сверять весь truth vector + source/bindings. При assumptions использовать область совместной применимости (`ALL_CANDIDATE_ASSUMPTIONS_HOLD`) — либо явно вернуть, что применимость неизвестна/ложна. Отдельные модели для направлений `A=true,B=false` и `B=true,A=false` сохранять обе, если они найдены.

Ключевые статусы: `PROVED_ALPHA_EQ`, `PROVED_ENTAILMENT`, `COUNTERMODEL_A_NOT_B`, `COUNTERMODEL_B_NOT_A`, `INCOMPARABLE_PROVED_BY_TWO_COUNTERMODELS`, `FINITE_SAME_ON_BOUND`, `UNKNOWN_BOUND`, `UNKNOWN_UNSUPPORTED_PROOF_CLASS`, `TYPE_REJECTED`, `LANGUAGE_INSUFFICIENT`. `FINITE_SAME_ON_BOUND` **не** влечёт `EQUIVALENT`. Когда `formal_contrast` останавливается при `RELATION_CELL_BOUND` — показать исходный код причины и число проверенных моделей, а не присвоить эквивалентность. Сценарный observer — ещё один `v_M(phi)`; не надо встраивать в ядро семантический scorer.

### P0. Обязательства и сценарный вектор

Для каждого `(hypothesis,scenario)` возвращать отдельно:

- `formula_truth`: `TRUE|FALSE|UNKNOWN|ILL_TYPED`;
- `assumption_truths`: по одной записи на проверяемый AST, `TRUE|FALSE|UNKNOWN`;
- `applicability`: `APPLICABLE|CONTEXT_INCOMPATIBLE|UNKNOWN_CONTEXT` — вычисляется только из assumptions; **не** меняет formula_truth;
- `source_alignment_status`: неизменно `PROPOSED`, `NOT_ADJUDICATED` или `LANGUAGE_INSUFFICIENT`, но **никогда** `VERIFIED`;
- `obligations`: исходные OPEN + полученные проверяемые статусы только конкретных формальных предпосылок; linguistic `ANAPHORA`, `TEMPORALITY` остаются OPEN до внешней оценки.

Если статус хотя бы одной предпосылки FALSE, `CONTEXT_INCOMPATIBLE`. Если нет FALSE, но есть UNKNOWN — `UNKNOWN_CONTEXT`; иначе `APPLICABLE`. Пустой список assumptions не равен тому, что авторское намерение установлено: это означает лишь `NO_DECLARED_ASSUMPTIONS`.

### P0. Query/replay/provenance/security

- Все новые records append-only в существующем project `Workspace` и CAS; owner scope через защищённый project context; idempotency `request_key`, повторный ключ с иным payload => `REQUEST_KEY_CONFLICT`.
- В graph links **только** реальные выданные в проекте `hypothesis_ref`, `model_ref`, `run_ref`. Обнаружение чужих ссылок => `NOT_FOUND`, а не связывание по SHA.
- Источник и private contexts должны оставаться в проекте; только owner может инспектировать bundle; ошибки не раскрывают чужие объекты.
- Не исполнять source_text, AST, модель, prompt или payload как код; payload — данные. Защищать output от prompt injection.
- Bound everything: число пар (≤10), max 8 сценариев, max_ast_nodes, steps, CPU, память, max output bytes, лимиты очереди и работы. Превышение bounds => корректный частичный `UNKNOWN_BOUND` с диагностикой, не «0 различий».
- `semantic_bridge_replay`: пересчитать чистую часть проверки без LLM, сверить input/result/kernels SHA, fail closed при несовпадении, `REPLAY_MATCH` только при фактическом совпадении.
- `semantic_bridge_inspect`: `summary|graph|obligations|checks|bundle`, пагинация JSON/base64 как в `FormalService.inspect`, без молчаливого усечения.
- У старых 98 tool names/schemas (по состоянию на v0.4.12) *байт-в-байт* сохранить контракт; только новые четыре tools; новый capability в `bridge_system_status` opt-in; при недоступности worker новый слой `UNAVAILABLE`, старый сервис не деградирует.

## 4. Минимальный тестовый сценарий SB-EXP01

Истинный корпус заморожен в `reference/SB_EXP01_FROZEN_INPUT.json`; не подменять его примерами из документа. Source SHA `2f27c8239b74438c5796715017e738aab3d0755e76c7eb1c4660412a205ad647` и сигнатура (`researcher`, `manager`, `hypothesis`, `Supervises/Checked/Planned/Reported`). Предикаты и H0–H4 в `reference/SB_EXP01_REPORT_RU.md`.

Обязательные точные результаты:

1. `H0` и `H2`: `PROVED_ALPHA_EQ`, proof SHA и проверка, модельный перебор 0.
2. `H1=>H0`: `PROVED_ENTAILMENT` только после проверенных 16 пропозициональных строк; в обратном направлении модель M1 `S=C=P=R=true` даёт `H0=true,H1=false`.
3. `H0,H3`: две независимые модели M2 (`S=R=true,C=P=false`) и M3 (`S=C=true,P=R=false`) показывают `INCOMPARABLE_PROVED_BY_TWO_COUNTERMODELS`.
4. `H4` (`future`): `LANGUAGE_INSUFFICIENT` или явное `TYPE_REJECTED`, сохранив unsupported operator, source и open obligation; ни в коем случае не предлагать фиктивный FOL.
5. M4 `S=C=P=R=false`: `H0.formula_truth=TRUE`, но при `A_exist=∀r ∃m Supervises(m,r)` => `assumption_truth=FALSE`, `applicability=CONTEXT_INCOMPATIBLE`.
6. M5 `world=open`: `formula_truth=UNKNOWN` и no forced false.
7. Source spans UTF-8 source-bound; corrupted bytes/hash/source owner rejected.
8. Replay > 0: `REPLAY_MATCH` для register/analyze; offline independent verifier из `reference/SB_EXP01_VERIFY.py` сохраняет свои наблюдения.

**Важно:** M4 — отсутствие ребра Supervises, не пустая область сорта Manager: в текущем FOL все сорта непусты. Формулировать это точно в отчётах.

## 5. Security / regression / deployment

Перед кодом: изучить `src/lm_suti_assurance/formal_bridge/{fol,engine,service,contracts,mcp}.py`, `nl_proposal/{decoder,service,contracts,provenance}.py`, `udav_core/{service,mcp}.py`, текущий entrypoint/capabilities и tests. Проверить API реально поднятого сервера и исходный commit, сделать короткий RCA. Готовые тесты **не** копировать как фиктивные `PASS`: запускать, сохранять команды, версии, durations, exit codes, независимые результаты и hashes. Включить отрицательные тесты источников, cross-project access, replay tampering, request_key conflicts, open-world, invalid AST, source span mismatch, complexity bombs, timeout, no background LLM calls. Не нагружать систему массовым перебором.

Сохранить production workspace, SQLite, старые assets и native hashes. Не обновлять production до пройденных offline tests; затем ограниченный canary workspace и, если есть разрешение на deploy, rolling opt-in deployment с проверкой tools/list. Возможность rollback к старой версии кода без удаления append-only новых событий. Не хранить секреты в коммитах/артефактах. Текущая GitHub Actions CI может быть заблокирована billing; в таком случае **не заявлять CI PASS**, показать локальные реально воспроизведённые результаты.

## 6. Критерии готовности и конечная поставка агента

Все G0–G9 из `ACCEPTANCE_MATRIX.json` должны иметь `PASS` на независимых фактических тестах, иначе статус `PARTIAL/FAIL`. Human semantic adjudication **не входит** в этот патч; соответствующий флаг остаётся `NOT_EVALUATED`.

Поставка агента в отдельном ZIP: актуальный source diff/patch или полный изменённый код с путями, `IMPLEMENTATION_REPORT_RU.md`, `RCA_RU.md`, `TEST_MATRIX.json`, `API_SCHEMAS.json`, `MCP_RECEIPTS.json`, `REPLAY_RECEIPTS.json`, `BACKUP_ROLLBACK_RU.md`, `CHANGELOG.md`, `MANIFEST_SHA256.txt`, реальные tests and fixtures. Зафиксировать commit/release/deployment и SHA, явно отделить code merged / tested / deployed.

**Не делать в PATCH001:** NL-генератор внутри MCP, новые универсальные лингвистические законы, автоматическую семантическую санкцию, обучение локальной модели, расширение FOL до модальности/темпоральности, оптимизатор бизнес-процессов, переписывание UDAV/CAD/NOPS/White Star, дорогие массовые переборы. Это отдельные будущие эксперименты после измеренного выигрыша.
