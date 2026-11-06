# FIX-B2: повторная приёмка LivingMath

**Установлено v0.4.5-developer-preview**, deployment `fix-b2-20261106T025708Z`, endpoint сохранён: https://fares-september-rebel-board.trycloudflare.com/mcp. Реальный публичный MCP: **196 FIX-B2 +206 SP/replay +254 legacy =656 PASS**. Подключённый LivingMath plugin дополнительно вызвал verifier и получил CHECKED_INSTANCE. Сохраняются 83 инструмента и все прежние схемы/annotations.

## Конкретный положительный результат

- Новый зарегистрированный предиктор: **`derived_2aadef27f9235974c974`**, parent **`derived_eff97b656fe7e4625166`**.
- Проект: **`qa-fixb2-prod`**, новый run: **`e1a9e5b090f6a3d0491f7d640a91b6fbbe548de61432e05a61c54350f681f718`**.
- `white_star_symbolic_observer_verify`: **CHECKED_INSTANCE**, 14 source witnesses, training_compatibility=true, execution_permission=false, universal_invariant=false.
- Полный AST, шаги, hashes и byte lineage — VALID_DERIVED_FEATURE.json. Повреждённые intermediate hash, source span, operator, origin, hidden labels и parent отвергнуты; реальные ответы — REJECTED_FEATURES.json. CHECKED_INSTANCE удостоверяет вычислительные свидетельства, не mathematical verified.

**Важно:** старый run `6072bffc...` остаётся историческим отрицательным результатом. Повтор старого request_key вернёт прежний run; чтобы проверить исправление, нужен **новый request_key**. Готовый запрос к исходным datasets проекта whitestar_dialog_test и прямая проверка нового run опубликованы в api_examples.json.

## RCA: какой шаг отсутствовал

Исходные 16 immutable snapshots действительно пересчитаны исходным v0.4.4 с точным совпадением result_digest. Случай contains-SP имел 14 train и 16 queries; NO_VERIFIABLE_NEW_OBSERVER был реальным. Он не опровергал прошлый отдельный offset1-тест, но показывал другой пропуск: context_relations вычислялись после derivation и никогда не становились кандидатами registry. Старый генератор рассматривал выравнивание токенов, а не эти контексты; operator-only dependencies также не давали ему автоматически новый предикат.

Теперь контексты поступают в отдельный bounded promotion pass. Сначала требуется положительный источник, известный отрицательный output реальной операции и размеченные proper fragments; затем проверяется совместимость со **всем** train. Регистрируются два разных объекта: source-bound literal comparison с наблюдавшимся фрагментом и зависимый bounded scan контекстов. Второй действительно использован моделью. Свидетель контекста сам по себе не объявляется инвариантом.

Исполняются только прежние SPLIT/CONCAT и точное сравнение токенов; имена S/P, Dyck или языка не зашиты в production. Два закрытых вида AST описаны в OBSERVER_PREDICATE_SCHEMA.json; нет произвольного scripting или нового набора фундаментальных операций. Наблюдатель не эквивалентен source identity: literal token comparison сохраняет отдельную lineage для каждого происхождения.

Независимый promotion_verifier не вызывает producer, grammar features или его trace generator. Он заново проверяет источники, все 14 train labels/refs, родителя, минимальность фрагмента, исходный контекст, состояния, каждый промежуточный output и reconstruction. Статистика:14 контекстных свидетелей, 1 полностью проверенное predictive rule, 2 зарегистрированных feature objects (один dependency). Это не исчерпание всех правил.

## Замороженный контроль и baselines

Сохранились точные 14 исходных train-записей и 16 исходных queries. До первого нового inference добавлены 32 слова длины 5 с отдельным внешним label-holder. Train/heldout IDs не пересекаются; accepted не передаётся в queries. Один seed137 и одинаковые CPU/search caps. Baselines отличаются только разрешёнными features/derivation. Полный unrestricted builtin control добавлен как прозрачный дополнительный контроль; правило, split и метрика после просмотра результатов не менялись.

| Режим | n4 /16 | n5 /32 | Abstentions |
|---|---:|---:|---:|
| promoted | 16 | 32 | 0 |
| no_derivation | 5 | 6 | 0 |
| literal_only | 5 | 26 | 0 |
| builtin_only | 13 | 28 | 0 |
| majority | 5 | 6 | 0 |
| builtin_all | 13 | 20 | 0 |
| parent_disabled | 5 | 6 | 0 |

Полные confusion и coverage — SCORES.json/RESULTS.csv. `builtin_only` сохраняет ban pair_0_max/min/final; `builtin_all` разрешает все эти builtin features, но не derivation. Majority и no_derivation в этом контроле совпадают. Никакой random tie credit не выдаётся за верную классификацию. На 48 конечных queries новый предиктор дал TP37/TN11/FP0/FN0. Это конечная empirical демонстрация, не универсальная грамматика.

Отключение действительного parent_feature_id или операторного dependency делает child недоступным. В тестах builtin-калькулятор целиком заменён запрещающей функцией ещё до fit/predict. За пределами объявленного short-word scope (до 8 tokens) новый предиктор возвращает UNKNOWN, а не ложный ответ.

## Отрицательные исходы сохранены

Все 8 observer-сценариев из входного отчёта повторены на том же содержимом в QA-проекте. Ограниченный Dyck без нужных размеченных proper fragments остаётся NO_VERIFIABLE_NEW_OBSERVER с failed obligations; семейство UNDERDETERMINED. Литературный smoke также не объявлен найденным законом. Полного литературного перебора или нового 942-катренного эксперимента в этом исправлении не запускали. Прежний вывод об отсутствии подтверждённого semantic transfer не пересмотрен.

## Проверки и сохранность

До изменений:12 reference tests, 320 baseline tests и 254 реальных legacy MCP checks. После:337 source tests, 337 tests установленного wheel вне checkout; 1066 legacy PASS/20 SKIPPED. Стенд:196+206+254 checks PASS; production:656 PASS. Точные source hashes и все request/response — в evidence ZIP; api_examples.json содержит реальные принятые вызовы.

Перед обновлением выполнены backups4 SQLite, затем отдельные quiescent backups при остановленном HTTP. Сохранены 23524 initial и 24173 cutover files, все исследовательские строки, immutable objects и префиксы hash-chain; SQLite4/4 ok, исходный canonical audit неизменён. Все 16 входных run records совпадают с исходными. Истекающие OAuth sessions меняются штатно; backups сохранены. Лимит регистраций клиентов не ослаблялся: QA использует существующего owner client через PKCE.

Numeric White Star, frozen core, symbolic_v1, SP model и SP verifier побайтно сохранены. Старые v0.4.3/v0.4.4 extension profiles исполняются прежними hash-bound workers. Общая квота 2 active/16 queued, CPU5s/wall6s/RAM512MiB сохранена; только HTTP перезапущен, URL и PID туннеля прежние. Автоматические grants и mathematical verified не выдаются. Native SUTI NOT_EXECUTED, внешний R3 sign-off остаётся PENDING.

Код `8ef1293a308e8243951d312c9e5e4d0b68b3c1cf`. Wheel SHA256 `32ffaabeb6ecc8c2220dffb7167c8262bcd2ec60a48566cd813d1dad5b1f20fd`. Runtime manifest `c34dd91fc28b8bf07f2d89671f06c8792fe90f555872f272ce553d9d6c577fa1`. Новая рабочая конфигурация подтверждена реальным MCP-клиентом и подключённым plugin, не только локальными unit tests.
