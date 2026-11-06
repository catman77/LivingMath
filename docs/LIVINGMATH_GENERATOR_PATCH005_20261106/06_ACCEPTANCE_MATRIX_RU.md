# Матрица приёмки PATCH-005

## Реальные endpoint-вызовы

Версия сервера должна показывать новый `observer_synthesis_v1`/kernel binding. Вызывать `white_star_symbolic_observer_synthesize` на project `whitestar_dialog_test` или новом тестовом проекте. Все данные: `kind=train` с `accepted`, `kind=queries` строго без `accepted`; запросы `holdout_labels_visible=false`, `enabled_builtins=[]`, `promotion_policy.mode=compositional_ast|auto`, `candidate_sources=derivation_trace`, `require_independent_checker=true`; каждый запуск с новым `request_key`.

## P0: минимальный причинный регрессионный тест

| Train | Expected train-compatible AST | Результат старого сервера | Ожидаемый новый |
|---|---|---|---|
| 16 слов Σ⁴ (B) | PAL recursive | promotion PASS | PASS |
| B + `SS` (positive) | PAL recursive | FAIL, seen 7 compatible 0 | PASS |
| B + `PP` (positive) | PAL recursive | FAIL, seen 7 compatible 0 | PASS |
| B + `SP` (negative) | PAL recursive | PASS, seen 10 compatible 2 | PASS |
| B + `PS` (negative) | PAL recursive | PASS, seen 10 compatible 2 | PASS |

**Важное:** ожидание PASS означает найденный train-compatible typed recursive AST с независимым checker; просто `score>0.5` по готовым builtin недопустим.

## P1: смешанные длины и перенос

- Train Σ²∪Σ⁴ (20) PAL → holdout все 64 Σ⁶ и все 256 Σ⁸: FP=FN=0, coverage=100% в границах max_tokens=8.
- Train Σ¹…Σ⁴ (30) PAL → holdout все 128 Σ⁷: FP=FN=0, в том числе endpoint_equal counterexamples.
- Train Σ¹∪Σ³∪Σ⁵ (42) PAL → holdout все 128 Σ⁷: FP=FN=0.
- Train Σ²∪Σ⁴∪Σ⁶ (84) PAL → holdout все 256 Σ⁸: FP=FN=0 (или честно `RESOURCE_LIMIT`, но не математическое no-compatible, если AST найден в независимо заданном finite catalog).
- Палиндром с только Σ⁴ → Σ⁶/Σ⁸: сохранить 64/64, 256/256.
- COPY train Σ²∪Σ⁴ (20) и train=52 → Σ⁶,Σ⁸: без регрессии и без навязывания только PAL шаблона.
- Написать отрицательный endpoint-only тест на Σ⁷: есть 48 ложноположительных на один из старых обучающих режимов; расширение внутреннего сравнения необходимо.

## Безопасность/математика

- `verify` подтверждает оригинал, отклоняет mutation одного source span, output hash, SPLIT position, запрещённого operator и отсутствующего witness, **даже после пересчёта верхнего digest**.
- Сертификат говорит `CHECKED_FINITE_INSTANCE`, `universal_invariant=false`, `UNDERDETERMINED` если не доказана уникальность; после max_tokens=8 — UNKNOWN/score=null.
- `source_run_id` другой train → `SOURCE_TRAIN_MISMATCH`; чужой проект → NOT_FOUND; загрузка holdout labels → `HELDOUT_LABEL_LEAKAGE`.
- Экспорт+реплей нового composition proof — `REPLAY_MATCH`, журнал `PASS`, `holdout_labels_read=false`.
- SP finite complex N=4,N=10 неизменен: (9,14,8) и (351,1614,3360), π1 trivial with checked certificate; without 2-cells → NOT_PROVED.
- Legacy numerical `base_v1/cj_v1` READY; исторический `symbolic_v1` replay MATCH.

## Контроль против самообмана

- Отдельно от точности выводить TP TN FP FN abstentions, balanced accuracy и объёмы train/test (в случае PAL длины 8 baseline always-negative 240/256 = 93.75%, не 0%).
- `train-compatible` НЕ значит независимое открытие универсального закона; `NONE compatible` при исчерпанном времени не значит математическую невозможность.
- Зафиксировать не менее 2 seed и новые request_key. Если новый результат не совпал с ожидаемым — внести RCA, а не переписать фикстуру.
