# Матрица приёмочных испытаний PATCH-004

Относится к будущему релизу, а не к текущему v0.4.5. Проверять **реальный MCP** и каждый раз использовать новые `request_key`. Не останавливать работу из-за отрицательного результата: фиксировать статус и точный RCA.

| ID | Gate | Сценарий | Ожидаемое / причина отказа |
|---|---|---|---|
| A01 | P0 | `Σ⁴` (16 train), PAL, `enabled_builtins=[]` | AST `iterate_on_inner_fragment` train-compatible; 16/16 train |
| A02 | P0 | Превратить AST в immutable feature | `DERIVED_FROM_OPERATORS`, проверенный `operator_ast`, не shortcut BUILTIN |
| A03 | P0 | Independent checker | `CHECKED_INSTANCE`, 16+ свидетелей, исходные байты/спаны |
| A04 | P0 | PAL `Σ⁶`, 64 blind queries | TP=8 TN=56 FP=0 FN=0; balanced accuracy 100% |
| A05 | P0 | PAL `Σ⁸`, 256 blind queries | TP=16 TN=240 FP=0 FN=0; balanced accuracy 100% |
| A06 | P0 | Alternate `source_run_id` existing successful old grammar run | корректная проверка ссылки/AST; пригодный observer; mismatch rejects |
| A07 | P0 | Два независимых seed и fresh keys | проверить стабильность, если изменился выбор — сохранить причины; не утверждать доказанную уникальность |
| A08 | P0 | `derive_relations=false` | не использовать новый признак; контроль реально отличается |
| A09 | P0 | denylist конкретного derived feature | не использовать признак/его зависимых кандидатов |
| A10 | P0 | Queries без labels | `holdout_labels_read=false`, model freeze до queries |
| A11 | P0 | Исторические request_key | неизменённый старый run; новые ключи дают новый build |
| A12 | P0 | Попытка доступа из другого project | `NOT_FOUND`/авторизованный reject |
| A13 | P0 | Подмена `output_word_hash` в trace | `REJECTED`, field_path, не `CHECKED_INSTANCE` |
| A14 | P0 | Подмена позиции `SPLIT` | `REJECTED`, включая корректно пересчитанный wrapper digest |
| A15 | P0 | Удаление одного witness | `REJECTED` или `NOT_PROVED`, не продвижение |
| A16 | P0 | Неверный UTF-8 span («кот», «лес») | `REJECTED`, реальные байты |
| A17 | P0 | `RUN_SCRIPT`/запрещённый operator | `REJECTED`, никакого исполнения стороннего кода |
| A18 | P0 | Изменить `origin` на `BUILTIN` | `REJECTED` |
| A19 | P0 | `universal_invariant=true` без формального доказательства | `REJECTED`/`NOT_PROVED` |
| A20 | P0 | Word beyond declared max_tokens | `UNKNOWN`, `score=null`, не False |
| A21 | P0 | Repeated semantic-equivalent fresh run | equal `result_digest`; same key idem run id |
| A22 | P0 | Observer export/replay | `REPLAY_MATCH`, journal hash-chain PASS, source checked |
| A23 | P0 | Старые `SP/PS/SS` FIX-B2 | 64/64 на длине 6 каждый; независимая верификация |
| A24 | P0 | Старый S/P 2-комплекс N=2..10 | прежние counts и checked path certificates; partial 2-cell cases NOT_PROVED |
| A25 | P0 | Численная Белая звезда, старый `symbolic_v1`, immutable run | no breaking change |
| B01 | P1 | COPY train `Σ²∪Σ⁴`, without builtins | генератор **сам** порождает compare-fragments AST, source trace |
| B02 | P1 | COPY `Σ⁶`, blind 64 | TP=8 TN=56 FP=0 FN=0 |
| B03 | P1 | COPY `Σ⁸`, blind 256 | TP=16 TN=240 FP=0 FN=0 |
| B04 | P1 | COPY true splitting vs endpoint-only/bag counts | независимые различающие контрпримеры |
| B05 | P1 | COPY derived feature verification + denylist | позитивный `CHECKED_INSTANCE` и действительно ухудшенная абляция |
| B06 | P1 | COPY source-supplied AST as control | evaluator may pass, но **не засчитывать discovery** |
| C01 | P2 | Dyck-1 без pair_0_max | реальные новые структурные правила vs baseline, не pretend theorem |
| C02 | P2 | Nostradamus оригинал vs line swap | sealed cross-century holdout; not-identifiable pairs excluded from claimed accuracy |
| C03 | P2 | Boundary/literal vs alpha vs punctuation ablations | честный report; нет искусственного успеха |

## Контрольные точки / фиксированные тестовые корпуса

- PAL train: все 16 `Σ⁴`; dataset_ref старого воспроизводимого набора: `f7502b97fbb2c101cbd061b68e7036dd07038d862cb4df015ab6b1160005e452`.
- COPY train: все 20 `Σ² ∪ Σ⁴`; `a2a8e8c548a93b8509e9b8782ff6b7cb8374f5573468f86ab65c69310b926e73`.
- Queries `Σ⁶`: `0c79f9fa14e9ce1d38570f9dc83368a1d42881a9cc251866056a4c976cda4ae1`.
- Queries `Σ⁸`: `4b0817caf2bdf5bb3ae509d4e7374e2f3abfd7dd27e15f1dda0c16ed27c22b66`.
- Старый PAL successful run: `80457c8536c12fb4e18e302c14542ca4568e9c83cb650def98af3fb49cd92baa`.
- Свежий PAL new module failure: `bb66f9832dd207712845b9ec95a67f61626e46dde231b1f11caa30a7a6624679`.

Historical refs — только источники данных и доказательств состояния **до** патча; новый релиз требует новых run IDs. Ни один из приведённых refs не разрешает менять source labels или переписать archived results.

## Сопоставление с независимым эталоном

`cd reference && python test_typed_ast.py`: 16 тестов, включая positive/negative full `Σ⁴,Σ⁶,Σ⁸`, UTF-8 и adversarial mutation. Реальные production результаты P0/P1 должны сверяться с независимым scorer, а не с тем же кодом, который генерирует prediction.

## Метрики

В каждом ответе / отчёте показать: `TP,TN,FP,FN`, sensitivity, specificity, balanced accuracy, coverage, `UNKNOWN`, baseline, feature_ids, AST hashes, origin, verifier status, no-leakage check, `result_digest`, stop_reason, worker CPU/memory. Не считать `UNKNOWN` ошибкой класса False, отдельно учитывать abstention coverage. При дисбалансе 8/64 accuracy без confusion matrix недопустима.

## GO / NO GO

P0 complete только после всех A01–A25 (не все операции обязательно пересчитать в одном запросе). P1 отдельно, не подменять референс-кодом. P2 exploratory, не блокирует работающую версию, но отсутствие meaningful cross-century generalization должно быть показано явно.
