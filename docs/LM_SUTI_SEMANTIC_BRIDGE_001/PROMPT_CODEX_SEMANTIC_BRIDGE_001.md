# Промпт кодовому агенту — LM–SUTI–SEMANTIC–BRIDGE–001

Тебе переданы `TZ_LM_SUTI_SEMANTIC_BRIDGE_V02.md`, `ACCEPTANCE_MATRIX.md`, `SEMANTIC_RECORD_EXAMPLE.json` и README. Работай в существующем репозитории LivingMath × SUTI на базе `v0.1.0-developer-preview` и release-поставки `LM_SUTI_RELEASE_V01_DELIVERY.zip`.

**Задача:** реализовать минимальный **text → versioned interpretation → source/evidence binding → declared structural loss → assurance → offline replay** адаптер. Это релизная продуктовая доработка, а не новый академический бенчмарк и не новая основа математики.

## Непереговорные правила

1. Сначала inspect `README_QUICKSTART_RU.md`, `BASELINE_LOCK.json`, `src/lm_suti_assurance/{core.py,cli.py,mcp.py,bundle.py,offline.py}`, текущие API/schemas; сохрани реальные hashes и `assurance_doctor`. Не придумывай несовместимые методы, классы, права и API.
2. `_frozen/`, старые verifier и binder — **read-only**, не редактировать и не форкать. Любой новый check — отдельный строгий preflight и/или существующий assurance facade, не скрытая замена frozen check.
3. **Утверждения модели недоверенные.** Binder никогда не исправляет смысл, не дописывает цитаты, не изобретает relation или новые premises за LLM. Deterministic source binding заполняет только уже pinned context/spans/permissions.
4. Интерпретационные высказывания — `INTERPRETATION` внутри нового typed ledger; в assurance допускаются лишь как гипотезы с `UNKNOWN`/`CONDITIONAL_HYPOTHESIS`/`HOLD`. `SOURCE_ATTESTED` только для байтов/полей/подтверждённой декларации разметки, а не «автор хотел сказать». Никакого `PROVED_FORMAL`, физической истины, наивной `VERIFIED`.
5. Отказаться от локального Qwen/0.6B и соревнований моделей. Использовать один имеющийся работающий hosted generator либо честно вывести `MODEL_UNAVAILABLE`; ручные фикстуры не считать модельным успехом.
6. Никакого stealth production deployment, правок legacy SQLite или root AGENTS, записи в другие проекты, утечки ключей или обхода publication policy. Не меняй release-gate `R3=PENDING`.
7. Все результаты первоначально сохраняй append-only, с отрицательными случаями и неудачными raw proposals. Никаких quality retries с выбором лучшего ответа; если инструмент недоступен, фиксируй это и продолжай независимые deterministic regression.

## Этапы исполнения

### E0. Контракт и freeze (до inference)

Прочитай локальные схемы и действительные MCP capabilities. Запиши `PRECOMMIT.json`: версии, SHA checker/binder, source/rights, ровно 3 произведения, 2 прохода на каждое, допускаемые scopes, фиксированные проверки, бюджет (не более 16 model attempts для 6 чтений + ошибок транспорта; `null` для неизвестных денег), режим генератора и shutoff. Публичные электронные редакции сверяй по доступным локальным/известным источникам; запиши непроверенную редакцию как `UNCERTAIN_EDITION`, не фантазируй. Для 6 обязательных модельных чтений (2×3) достаточно шести содержательных вызовов; никакого масштабного benchmark.

### E1. Модель данных + source anchors

Введи самостоятельные versioned JSON Schemas для `SourceAnchor`, `SemanticFrame`, `RevisionEdge`, `ProjectionContract`, `StructuralLossWitness`, `ResearchDossier`. Точный byte-slice unicode тест обязателен. Конкретный source ref не может быть сгенерирован моделью. Все новые записи с project/source/parent ids и digest. Добавь строгую регистрацию `FRAME_UNTRUSTED`, `FRAME_VALIDATED`, `FRAME_REVISED`, `FRAME_WITHDRAWN`, независимо от эпистемического статуса claim.

### E2. Реальный генератор и версии прочтений

Выбери литературный корпус из ТЗ; на каждый текст: initial (самостоятельное чтение, до challenge), затем revise с полным source и frozen initial. Сохрани обе версии, raw prompts/outputs и связь между ними; не стирай исходное прочтение. Каждая версия содержит минимум: 2 source-bound literal anchors, 2 proposed relations/motifs, 1 явное ограничение, 1 альтернативную трактовку или unresolved ambiguity. Не надо гарантировать «глубину» художественного анализа — измеряем структуру, происхождение и воспроизводимость.

Нельзя дать модели gold-ответ вроде «Блок точно спираль»; оставляй альтернативы. Модель, не сумевшую создать валидный frame, не переписывай биндeром — фиксируй failure.

### E3. Comparison / loss

Создай детерминированный `compare(left,right,projection,declared_Q)`: изменения, сохранения, source refs, witness и неопределённость. Для Блока отдельный positive regression: ручные/модельные аннотации с одинаковым `image_set`, но различием `image_order` и деталями `canal`; проекция на image_set должна дать `LOSS_DETECTED` с точным q/witness. Отрицательный: полная проекция на relevant поля не должна давать LOSS. Не выдавать `PRESERVED_FOR_DECLARED_Q` без полностью проверенного Q. Не выдавать семантическую неэквивалентность стихотворений только потому, что различаются списки токенов.

### E4. Assurance и автономный replay

Реализуй source-claim checks и hypothesis HOLD/UNKNOWN через текущий facade. Проверь намеренно ложную цитату, неподтверждённый «абсолютно тождественный цикл мира», притворное сохранение всех полей. Выполни `report`, затем `export(private, source bytes authorized)`; отдельно `export(private, no source bytes)` должен получить `MISSING_SOURCE_DEPENDENCY` при offline replay. Оба self-contained `direct/compiled` должны давать PASS и одинаковые logical digests. Replay не вызывает модель и не перегенерирует frames — он проверяет сохранённые объекты/журнал/проверяемые контракты.

### E5. Regression and release QA

Запусти прежние тесты и негативные финитные fixtures (включая ложное 23/24 `ENTAILED`), новые матрицы и tamper/traversal/rights/Unicode tests. Проверь настоящие источниковые refs и статус unknown. Если MVP можно запустить через CLI — добавь `semantic draft/revise/compare/report`; MCP расширяй только после успешного QA и owner-approved deploy. Отдельно воспроизведи пакет в чистом окружении без LLM, OAuth, network. Создай `demo_poetry_private.zip` и полные артефакты.

## Definition of Done

- Доступно **6 сохранённых модельно-сгенерированных последовательных прочтений** (если модель реально доступна), для трёх текстов, включая три revision edges и минимум три явные альтернативы; failed reading не приравнивается к выполненному.
- Результат читабелен исследователю: source anchors, версии, что изменилось, что осталось спорным, где обнаружена потеря различения, какие утверждения только гипотезы.
- Все source literals подтверждены/отвергнуты независимо; никакая модель не может сама присвоить `SOURCE_ATTESTED`.
- Точный witness для structural loss, минимум один negative no-loss control, и правильно маркированная неопределённая смысловая интерпретация.
- Direct+compiled offline replay PASS, одинаковые logical digest; source dependency failure без разрешённых байтов, integrity tamper detection; zero secrets.
- Frozen hashes прежние, старые тесты без регрессий, production не изменён, R3 остаётся PENDING.

В конце напиши `USER_REPORT_RU.md` с таблицей по каждому из 6 прочтений, `RCA.md`, реальные команды установки и QA, `CAPABILITIES.json`, `CHANGED_FILES.md`, `INTEGRITY_AND_REPLAY.json`, `MODEL_ATTEMPTS.jsonl`, SHA manifest. Если блокер, не имитируй успех, выдавай конкретный error и минимальную правку. Не заканчивай отчёт фразой «всё готово», если хотя бы один обязательный gate не прошёл.
