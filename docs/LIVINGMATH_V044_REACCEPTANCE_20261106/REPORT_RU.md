# LivingMath v0.4.4 — повторная приёмка PATCH-003

Дата проверки: 2026-11-06. Источник результатов: фактические вызовы MCP на `whitestar_dialog_test`, а не анализ предполагаемого кода. Статус деплоя: `symbolic-patch003-acceptance-20261106T010226Z`; версия `v0.4.4-developer-preview`; kernel binding `d83508d18d7ba5758d99729b7610441fc0627de135fce5919ef4eac3fdeab178`.

## Release verdict

**CONDITIONAL PASS.** P0 математическое ядро, FIX-A (корректные assumptions), независимый verifier, отрицательные доказательные тесты, replay, compatibility, private isolation — PASS. P1 заявленная способность обнаружить *новый полезный verified operator observer* — NOT DEMONSTRATED / FAIL в проверенных позитивных сценариях. Нельзя объявлять полный исследовательский релиз принятым по факту наличия endpoint `observer_verify`.

## Математика и proof checks

| N | V | E | C2 | beta1 графа | rank(d2, F2) | H1(F2) | независимый verifier |
|---|---:|---:|---:|---:|---:|---:|---|
| 2 | 3 | 2 | 0 | 0 | 0 | 0 | CHECKED_INSTANCE |
| 4 | 9 | 14 | 8 | 6 | 6 | 0 | CHECKED_INSTANCE |
| 6 | 29 | 74 | 80 | 46 | 46 | 0 | CHECKED_INSTANCE |
| 8 | 99 | 354 | 560 | 256 | 256 | 0 | CHECKED_INSTANCE |
| 10 | 351 | 1614 | 3360 | 1264 | 1264 | 0 | CHECKED_INSTANCE |

Все перечисленные полные комплексы имеют `pi1_status=PROVED_TRIVIAL_WITH_CERTIFICATE` при **конкретной** политике `all_local_peaks` и строгом убывании длины S/P-редукций. Отдельно запущены 12 автономных тестов из прежнего PATCH-003: `Ran 12 tests ... OK`.

Негативные тесты:
- `none`, N=10: C2=0, H1=1264, `pi1_status=NOT_PROVED`; в assumptions больше нет `all_local_peaks_filled`.
- `bigons_only`, N=6: C2=48, H1=18, 32 нерешённых пика, `NOT_PROVED`; ложная предпосылка отсутствует.
- `diamonds_only`, N=6: C2=32, H1=16, 48 нерешённых пиков, `NOT_PROVED`; ложная предпосылка отсутствует.
- Поддельное ребро в `certificate.edges`: `REJECTED`, `UNVERIFIED_EDGE`.

**FIX-A закрыт.** H1=0 не использован как самостоятельное доказательство pi1.

## Аудит P1: operator-derived observers

Эталон Dyck: обучение на 28 словах длины 2/4/6, 70 запечатанных запросов длины 8. В `feature_denylist` запрещены все `pair_0_max/min/final`.

- `derive_relations=true`: 16/70 правильных; `NO_VERIFIABLE_NEW_OBSERVER`, использованы только встроенные `adjacent_equal`, `lag_*_mismatches`.
- `derive_relations=false`: 16/70, тот же критерий; отсутствие измеренного эффекта derivation в этой задаче.
- `enabled_builtins=[]` + `derive_relations=true`: 56/70 (классификация всех слов как не-Дик), `used_feature_ids=[]`, новых feature records нет.
- `observer_verify(feature_id='pair_0_max')` возвращает `BUILTIN`, `derived_claim_allowed=false`. Несуществующий `feature_id` даёт `NOT_FOUND`; поддельное описание не превращается в проверенный признак.

Дополнительный позитивный стресс-контроль — `contains('SP')`: 14 размеченных примеров длины 1-3, все 16 слов длины 4 в sealed queries, включая известные метки некоторых производных удалением. В режиме no-builtins+derivation зафиксированы 9 `COMPATIBLE_ON_OBSERVED_K`, 3 `DISTINGUISHED`, 2 `UNKNOWN` relations, но ноль registered `DERIVED_FROM_OPERATORS`, `NO_VERIFIABLE_NEW_OBSERVER`, результат 5/16 (тривиальная всегда-отрицательная классификация). При разрешении builtins 13/16, но selected features только BUILTIN. Версия без derivation также 5/16.

**FIX-B НЕ закрыт**: `context_relations` вычисляются с трассами, но не становятся first-class validated predictive feature в registry. Не установлено, вызвано ли это фундаментальной невыразимостью выбранного DSL или отсутствием этапа promotion/training; требуется code-level RCA. Положительный тест для `observer_verify` на действительно новом признаке пока невозможен из-за отсутствия самого зарегистрированного feature.

## Corpus Nostradamus smoke

Обучение на первых 12 катренах I центурии и их перестановках 2/3 строк; тест — первые 8 катренов IX центурии с парными запросами без test labels. `global_alpha`: 1 правильный выбор, 1 неправильный, 6 TIE, `NO_VERIFIABLE_NEW_OBSERVER`; `punctuation`: `CONTRADICTORY_TRAINING` и 8 `NOT_IDENTIFIABLE`. На этом мини-разбиении нет оснований утверждать перенос смысловой грамматики; это только регрессионный smoke.

## Replay / security / compatibility

- Extension export SP4: `REPLAY_MATCH`, `journal_hash_chain=PASS`, independent checker `CHECKED_INSTANCE`.
- Observer export: `REPLAY_MATCH`, `journal_hash_chain=PASS`, `holdout_labels_read=false`, `hypothesis_frozen_before_queries=true`, `LLM_calls=0`.
- Попытка положить `accepted` в queries: `HELDOUT_LABEL_LEAKAGE`, корректное отклонение.
- Cross-project read: `NOT_FOUND`, отказ.
- Idempotency same request_key+request SP4: same run_id.
- Legacy symbolic data bundle replay: `REPLAY_MATCH` со старым digest `f17aa98dd5695692c9efd31b46256d4ef1ec44025f12cad2b742db47b15cb62f`.
- Legacy numeric White Star: `base_v1`, `cj_v1` READY; frozen manifest SHA-256 `25fe59c504c4fbc531999f2a16da7b98d6e7d3d6ab23e53347ef534fad2dbba1`.

## Ограничения объёма аудита

Это чёрно-ящичная функциональная/математическая приёмка через публичные MCP-вызовы и независимый Python oracle, не аудит всего исходного кода, инфраструктуры, нагрузочных границ и формального soundness. На Нострадамусе проверен малый контроль, не весь корпус. Нельзя перенести 12 локальных unit-тестов на глобальную гарантию корректности реализации.
