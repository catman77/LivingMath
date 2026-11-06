# Остаточная P1-проблема: от операторных контекстов к верифицированному наблюдателю

**Наблюдаемое:** `observer_synthesis_v1/1-patch003-acceptance1`, `v0.4.4`: `derive_relations=true` строит трассы `SPLIT/SPLIT/CONCAT` и `R(u,v|observed_context)`, но результат `NO_VERIFIABLE_NEW_OBSERVER`, независимо от наличия меток коротких производных и запрета builtins. `observer_provenance` содержит только `BUILTIN`, а `used_feature_ids` не ссылается на новый объект. Условия реального продвижения отношения в новый feature не срабатывают в проверенных задачах. Это не доказательство отсутствия механизма во всех возможных входах, но достаточно, чтобы не принять требование P1.

## Минимальное ТЗ FIX-B2

1. Разделить **операторный witness** (история с сохранёнными byte spans) и **проверяемый observer** (typed predicate, AST, executable semantics, инвариантность, зависимости, train-test contract). Не объявлять каждый контекст новым инвариантом.
2. Обеспечить хотя бы один заранее объявленный *позитивный* класс, где target отсутствует в `BUILTIN` и может быть создан как ограниченная композиция реальных `SPLIT`, `CONCAT`, `REVERSE`, `RENAME` и точных сравнений. Нужен train-only `verified_witness`, определённая область применимости и независимая повторная проверка через `white_star_symbolic_observer_verify`.
3. При подтверждении — реально зарегистрировать first-class `feature_id`, `origin=DERIVED_FROM_OPERATORS`, `execution_verified=true`, полный AST/step trace, input-output digests, UTF-8 source lineage и зависимые features. При невозможности — мотивированный `NO_VERIFIABLE_NEW_OBSERVER` с отчётом какой obligation не выполнен.
4. Отключение любого parent feature в denylist должно сделать новый признак недоступным; запрет `pair_0_*` не должен обходиться через переименование builtin. Отдельный контроль с `enabled_builtins=[]`.
5. Сравнить frozen rule на совершенно новых запросах с теми же бюджето-ограничениями, включая baselines `derive_relations=false`, literal-only, available builtin-only и majority. Привести confusion/abstention и число реально проверенных операторных правил, не только выбранный best candidate.
6. `observer_verify` обязан принимать настоящий derived feature и отклонять: (a) изменённый промежуточный output hash, (b) неверный source span, (c) неразрешённый operator, (d) поддельный `origin`, (e) использование скрытых labels.
7. Сохранить `UNDERDETERMINED` и `UNKNOWN` для случаев, где данные не определяют семантику/закон. Ни universal grammar, ни физические выводы по конечному train не заявлять.

## Приёмка

P1-PASS только если существует **конкретный новый зарегистрированный признак**, независимо верифицированный с `CHECKED_INSTANCE`, с фактическим приростом quality/coverage на запечатанном контроле относительно эффективной ablation и с честным source evidence. Простая успешность builtin `pair_0_max` или `R(u,v|C)` со статусом UNKNOWN не подходит. Допустим небольшой конечный эталон без часов вычислений; серверную безопасность, numeric engine и SP-complex не трогать.

**Стартовые воспроизводимые run_id:** Dyck restricted `85093f85...`; no deriv `874b53d9...`; no builtins `f1e35162...`; positive contains-SP derived `6072bffc...`; positive contains-SP builtin `b86d7c89...`; Nostradamus `4298c4f1...`.
