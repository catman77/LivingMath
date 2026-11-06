# LivingMath PATCH-003 — независимая приёмка production MCP

Дата: 2026-11-06. Сервер `v0.4.3-developer-preview`, deploy `symbolic-patch003-20261105T230048Z`. Движки `symbolic_complex_v1/1-patch003`, `observer_synthesis_v1/1-patch003`, оба READY. Проект вызовов `whitestar_dialog_test`.

## Вердикт

**Условная приёмка, НЕ полный release sign-off.** P0 математический SP-комплекс и независимый verifier: **PASS** на конечных предписанных комплексах. P1 наблюдатели: **PARTIAL** — builtin audit/ablation/holdout isolation работают; получение *нового полезного наблюдателя* из элементарных операций не продемонстрировано (`NO_VERIFIABLE_NEW_OBSERVER`). P2 Нострадамус: **PARTIAL** — небольшой реальный слепой пилот выполнен, но полная новая межцентурная приёмка 942 катренов и иерархические source spans не подтверждены.

## Базис

Пакет ТЗ: `LIVINGMATH_SYMBOLIC_COMPLEX_OBSERVER_PATCH003_20261106.zip`, файл `06_ACCEPTANCE_PROTOCOL_RU.md` (REG-001..007, SP2C-001..019, SYN-001..012, NOS-001..010).

Независимый локальный эталон из этого пакета: `python -m unittest discover -s tests -v` — **12/12 PASS**; `reference/sp_complex_reference.py --max-len 10` и `--face-policy none` — корректные точные значения.

## 1. Новый SP 2-комплекс (реальные MCP вызовы)

| N | V | E | graph β1 | local peaks/2-cells | rank d2(F2) | H1(F2) | pi1 status | verify |
|---:|---:|---:|---:|---:|---:|---:|---|---|
| 2 | 3 | 2 | 0 | 0 | 0 | 0 | PROVED_TRIVIAL_WITH_CERTIFICATE | CHECKED_INSTANCE |
| 4 | 9 | 14 | 6 | 8 | 6 | 0 | PROVED_TRIVIAL_WITH_CERTIFICATE | CHECKED_INSTANCE |
| 6 | 29 | 74 | 46 | 80 | 46 | 0 | PROVED_TRIVIAL_WITH_CERTIFICATE | CHECKED_INSTANCE |
| 8 | 99 | 354 | 256 | 560 | 256 | 0 | PROVED_TRIVIAL_WITH_CERTIFICATE | CHECKED_INSTANCE |
| 10 | 351 | 1614 | 1264 | 3360 | 1264 | 0 | PROVED_TRIVIAL_WITH_CERTIFICATE | CHECKED_INSTANCE |

Все числа совпали с эталоном. Верификатор идентифицирует себя как `SP-finite-independent-checker/1`; `boundary_squared_zero=true`, `missing_peaks=0`, пустой список проваленных обязательств. `pi1_status` относится строго к конечному комплексу с явно приклеенными всеми локальными пиками; это не доказательство свойства всех возможных структурных нулей вне этой модели.

### Отрицательные проверки

- N=10, `cells.policy=none`: V=351 E=1614, rank d2=0, H1=1264; `pi1_status=NOT_PROVED`. `verify` -> NOT_PROVED, missing peaks 3360.
- N=6, `bigons_only`: 48 faces, rank=28, H1=18; pi1 NOT_PROVED; missing peaks 32.
- N=6, `diamonds_only`: 32 faces, rank=30, H1=16; pi1 NOT_PROVED; missing peaks 48.
- Изменённое ребро в typed certificate: `REJECTED`, причина `UNVERIFIED_EDGE`.
- Низкий бюджет (`max_cells=3`, N=10): `BUDGET_EXCEEDED`, точный путь ошибки `/budgets/max_cells`.
- N=10 повтор с идентичным запросом: оба `result_digest=ba8aee9806014fe375a47c70d023b87fbff6de73272b695c277a034904ab8b98`. Идемпотентный `request_key` N=4 вернул тот же run_id.
- Экспорт N=4 и `white_star_symbolic_extension_replay`: `REPLAY_MATCH`, `journal_hash_chain=PASS`, независимая перепроверка.
- Попытка inspect из иного проекта: `NOT_FOUND`. Старые numeric/symbolic inspect и legacy symbolic replay: OK / REPLAY_MATCH.
- Импорт маленькой сохранённой символьной истории (5 узлов/0 verified edges): корректно `NOT_PROVED`; большая история (~686 узлов) упёрлась в CPU budget=4s (`BUDGET_EXCEEDED`), без ложной топологической теоремы.

### Выявленный дефект отчётности P0

На `none`, `bigons_only`, `diamonds_only` в `summary.assumptions` всё равно фигурирует строка `all_local_peaks_filled`, хотя все пики не заполнены. Сам `pi1_status` и checker остаются **корректными**, но список предпосылок является ложным и может вводить читателя в заблуждение. Исправить в metadata/status construction; negative regression required.

## 2. Observer synthesis: реальные исходные метки, sealed queries

Регистрация приватных train/query datasets с точным SHA-256: успешна. Отдельная попытка положить `accepted` в `kind=queries`: отвергнута как `HELDOUT_LABEL_LEAKAGE`.

### Dyck на balanced SP-словах

Train: все 28 balanced слов длин 2,4,6, метки «каждый префикс неотрицателен»; запросы **без меток**: 70 слов длины 8, 252 слова длины 10. Метки вычислены независимо за пределами сервера и применены после замораживания предиктора.

| Сценарий | TP | TN | FP | FN | Accuracy |
|---|---:|---:|---:|---:|---:|
| N=8, все наблюдатели | 14 | 56 | 0 | 0 | 70/70 |
| N=10, все наблюдатели | 42 | 210 | 0 | 0 | 252/252 |
| N=8, без `sp_reduce` | 14 | 56 | 0 | 0 | 70/70 |
| N=8, deny `pair_0_max` | 12 | 48 | 8 | 2 | 60/70 |
| N=8, deny всех `pair_0_*` | 13 | 3 | 53 | 1 | 16/70 |
| N=8, без `composition` | 13 | 3 | 53 | 1 | 16/70 |
| N=8, только `literal` | 0 | 56 | 0 | 14 | 56/70 |

Решающий `pair_0_max` **зарегистрирован как `origin=BUILTIN`**, `derived_claim_allowed=false`, с hash binding исходной реализации. Смена sealed набора (70 → 252 queries) **не изменила** `hypothesis_digest=dffa262a02dcd421c460dbb01539d1cb25de87e56e129133b1a36990691b3f00`.

В `model.context_relations` есть `origin=DERIVED_FROM_OPERATORS`, реальная трасса `SPLIT→SPLIT→CONCAT`, но это эмпирические отношения по обучающим контекстам; они не зарегистрированы как верифицированный новый полезный observer. Сервер правильно сообщает `NO_VERIFIABLE_NEW_OBSERVER`. **SYN-004 в сильной постановке (new observer actually synthesized, verified and used) пока не закрыт.**

Feature denylist/ablation применяются реально: поле `used_feature_ids` не содержит отключённых признаков, `hypothesis_digest` меняется, качество на независимой проверке резко падает. Записи в *реестре* builtin features могут оставаться даже при их отключении; это не означает их использование.

### Контроль противоречий

На двух S/P-словах `SP` и `PS` после `global_alpha` возникло `CONTRADICTORY_TRAINING`, а для α-неразличимой query-пары `NOT_IDENTIFIABLE`. Для иной пары с наблюдаемым различием статус `UNDERDETERMINED`. Никаких тестовых меток сервер не читал (`holdout_labels_read=false`).

## 3. Нострадамус — малый реальный слепой пилот

Исходники взяты из *уже сохранённых* серверных входов прежней обработки Sacred Texts: I центурия, 12 катренов train (оригинал и swap строк 2/3), IX центурия, 8 катренов queries-only. Токены отделены явным `SEP`, к каждому варианту привязан SHA-256 производного текстового предъявления. Это **не** полное испытание 942 катренов и **не** критическое издание.

| Представление | Верных предпочтений | Неверных | TIE | NOT_IDENTIFIABLE |
|---|---:|---:|---:|---:|
| global_alpha | 1 | 1 | 6 | 0 |
| local_alpha | 1 | 1 | 6 | 0 |
| punctuation | 0 | 0 | 0 | 8 |
| length | 0 | 0 | 0 | 8 |

`punctuation` и `length` дали `CONTRADICTORY_TRAINING`; при `exclude_with_report` сервер пометил конфликтные классы и не выдумывал прогноз. При текущем source / representation mapping различимость этих контролей не подтверждена; **не интерпретировать** как доказательство принципиальной невозможности их использовать на других представлениях.

## 4. Решение по релизу

- P0: **PASS** (кроме локального metadata bug).
- REG: **PASS** по проверенным numeric/symbolic/export/privacy интерфейсам.
- P1: **PARTIAL**. Надёжное происхождение builtin, sealed holdout, реальные ablations — PASS; полезный *новый* observer — **NOT DEMONSTRATED**.
- P2: **PARTIAL**. Реальный sample и корректные abstention — PASS; полная иерархия и 942-quatrain reproducible benchmark — НЕ ПРОВЕРЕНЫ.
- Общий: **CONDITIONAL ACCEPTANCE**, не маркировать как `all pass clean`.

Приоритет: исправить список предпосылок в summary, написать положительную приёмочную фикстуру для реально *синтезированного* наблюдателя с verifier и ablation; отдельно закончить NOS-002/NOS-005 на source-bound tree и раздельных изданиях.
