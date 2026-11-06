# Готовый промпт кодовому агенту — LM-OBSERVER-COMPOSITION-004

Ты — кодовый агент, работаешь с **реальным репозиторием действующего LivingMath MCP**. Пользователь передал архив `LIVINGMATH_RECURSIVE_OBSERVER_PATCH004_20261106.zip`. Твоя задача — **точечно расширить** синтезатор операторных наблюдателей, не создавать новую архитектуру и не нарушать уже работающие модули.

## Порядок чтения

1. `README_RU.md` — критерии и состав;
2. `01_RESEARCH_RCA_RU.md` — результаты настоящих серверных прогонов и точный RCA;
3. `02_FORMAL_MODEL_RU.md` — семантика и граница доказанности;
4. `03_TECHNICAL_SPEC_RU.md` — обязательные требования P0, P1, P2;
5. `04_MCP_CONTRACTS_RU.md` — предложения аддитивных контрактов;
6. `06_ACCEPTANCE_MATRIX_RU.md` — проверяемые критерии;
7. `reference/typed_ast_reference.py`, `reference/independent_checker.py`, `reference/test_typed_ast.py` — **исполняемый, но не интегрированный** эталон;
8. `fixtures/*` и `reports/*` — данные и логи.

## Жёсткие правила исполнения

- Сначала прочитай реально установленный код, статусы API и тесты; не угадывай пути или структуры пакетов. Установленная проверенная версия при подготовке ТЗ: `v0.4.5-developer-preview`, observer `observer_synthesis_v1/2-context-promotion`. Она может измениться — используй фактическую `bridge_system_status` на момент своей работы.
- Не переписывай численную Белую звезду, SUTI, SP-2комплексы, старый `symbolic_v1`, UDAV или immutable хранилище. Не подменяй историю одной нормальной формой слова.
- НЕ добавляй hardcoded PAL/COPY/Dyck flags в production, готовые ответы, внешнюю LLM, DSL, eval/exec или безлимитный перебор. Разрешены только типизированные композиции **уже существующих операторов** и ограниченная генерация таких композиций.
- Разделяй `candidate found`, `train compatible`, `operator execution checked`, `heldout scored`, `universal theorem`. Нельзя делать `PROVED_EXACT` или `universal_invariant=true` из конечного train.
- Не читай hidden holdout labels внутри сервера. Модель freeze до queries. Truth/test scorer только в независимом harness.
- **Для каждого нового испытания используй новый request_key.** Старые request_key исторически idempotent и не показывают изменения новой версии.
- Не запускай бессмысленные многочасовые прогоны. Эталон мал: `Σ⁴`/`Σ⁶`/`Σ⁸`, ограниченный worker, 16 коротких локальных тестов уже работают.
- Никаких фиктивных статусов о выполненной работе: каждый claim в сдаче должен соответствовать реально полученному результату настоящего MCP, со ссылкой на run_id.

## Шаг 1: RCA и минимальный дизайн

Найди ветку, которая порождает AST `iterate_on_inner_fragment` и на train `Σ⁴` маркирует его `TRAIN_COMPATIBLE`, но затем переходит в `NO_LABELLED_DISTINGUISHING_CONTEXT -> NOT_PROMOTED`. Установи конкретный call graph и место отказа. Опиши его в `RCA_RU.md` с ссылками на код.

Выдели второй путь: **typed composition promotion**. Прежде всего используй уже существующие `aligned_token_equality`, `all_observed_relations`, `iterate_on_inner_fragment`; для COPY позднее разреши параметризованный `SPLIT` на середине и `literal_word_equality`. Не создавай дополнительный язык программирования. Возвращай несколько конкурирующих train-compatible AST, а не скрывай неопределённость.

## Шаг 2: P0 — PAL как исполнимый операторный наблюдатель

На 16 точных training words длины 4 без builtins:

1. Генерировать/загрузить typed AST `iterate_on_inner_fragment`;
2. проверить static types и строгую терминацию `|inner|<|word|`;
3. исполнить AST на каждом train с source-hash/span-aware trace;
4. независимо перепроверить исполнение и полную coverage;
5. зарегистрировать immutable feature `origin=DERIVED_FROM_OPERATORS`, не `BUILTIN`;
6. использовать его при предсказании query-only `Σ⁶` и `Σ⁸`;
7. вывести training witness digest, candidate hypothesis family, `UNDERDETERMINED`, область применимости, `verified=false` если какой-либо шаг не прошёл.

Acceptance P0: TP=8,TN=56, FP=FN=0 на длине 6; TP=16,TN=240, FP=FN=0 на длине 8. Контроль `derive_relations=false` и denylist feature обязан реально менять результаты. Если этого нет — P0 FAILED, не маскировать метрику общей accuracy.

Обязательно поддержать безопасную передачу `source_run_id` старого индуктора; кандидат должен быть из того же project и согласован с train_digest. Даже без source_run_id локальный `derivation_trace` должен работать.

## Шаг 3: P1 — две одинаковые половины (не «готовый COPY»)

Используй общую bounded композицию `SPLIT` по structural midpoint и `literal_word_equality` двух **полных** половин. Генератор должен сам подобрать эту конструкцию из примитивов по train (`Σ² ∪ Σ⁴`, 20 записей). Не копируй `AST_COPY` из reference как «результат поиска»: это **эталон, а не discovery**.

P1 success: verified `DERIVED_FROM_OPERATORS`, реальные сравнительные шаги, separate train/holdout, 64/64 `Σ⁶` и 256/256 `Σ⁸` при рабочем source lineage; отрицательная абляция показывает полезность признака. Если генератор не нашёл — честно отметь P1 NOT PASSED, даже если отдельный reference/evaluator правильно вычисляет COPY.

## Шаг 4: независимый checker и adversarial tests

Проверяющий обязан повторно выполнить каждый шаг независимо от generator. В reference реализованы два разных кода (`typed_ast_reference.evaluate` и `independent_checker.execute_checked`). Там ограниченная подсистема, **не copy-paste-ready production**. Используй её как источник тестов, не доверяй её структуре как готовой интеграции.

Убедись, что все негативные мутации дают `REJECTED`: output hash, wrong position, UTF-8 span, missing witness, malformed AST, illegal op, label leakage, fake origin, false universal claim, out-of-scope. Проверить `UNKNOWN` без score вне объявленных max_tokens/depth.

## Шаг 5: регрессии

Прогнать старые `contains(SP|PS|SS)` FIX-B2, Dyck low-level baseline, все S/P-complex N=2..10 с partial negative cells, `white_star_symbolic_replay`, numerical `base_v1,cj_v1`, `white_star_symbolic_extension_replay`, source/private project boundaries и idempotency. Запрещено переобучить модель на holdout labels.

## Шаг 6: сдача

Сдай **единый ZIP** с реальными диффами/изменёнными исходниками относительно репозитория, git commit, точными версиями и kernel hashes, новой схемой MCP (если нужна), `RCA_RU.md`, `CHANGELOG_RU.md`, `ACCEPTANCE_RU.md`, run manifest с **НОВЫМИ request_key**, SHA и evidence; недоработки P1 честно перечислить. Не выдавай запуск reference за production acceptance.

**Ключевой запрет:** не решай задачу перебором «всех палиндромных слов», не подменяй рекурсию short-template matcher. Мы тестируем возможность переносить **способ построения отношения**, а не запоминание конечного набора строк.
