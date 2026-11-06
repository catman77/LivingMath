# LivingMath PATCH-005 — mixed-length compositional candidate discovery

**Статус:** исследование на живом MCP выполнено; этот архив — ТЗ для кодового агента и независимый эталон. **Продакшн PATCH-005 ещё не внедрён.**
**Базовая сборка:** `v0.4.6-developer-preview`, `recursive004-20261106T060730Z`, `observer_synthesis_v1/3-compositional-promotion`.
**Дата:** 2026-11-06.

**Передача агенту:** прочитать `05_AGENT_PROMPT_RU.md` и `03_TECHNICAL_SPEC_RU.md`; не подменять требование исследования кодом из `reference/`.

Внутри:

- `01_EXPERIMENTAL_RCA_RU.md` — живые продакшн-прогоны, минимальные воспроизводимые ошибки.
- `02_FORMAL_ARGUMENT_RU.md` — PAL/COPY, сравнение контекстной и композиционной гипотез, ограничения вывода.
- `03_TECHNICAL_SPEC_RU.md` — P0/P1 требования к генератору и ранжированию кандидатов.
- `04_API_AND_DIAGNOSTICS_RU.md` — совместимые изменения полей диагностики и независимого проверяющего.
- `05_AGENT_PROMPT_RU.md` — инструкция разработчику.
- `06_ACCEPTANCE_MATRIX_RU.md` — полный список положительных/отрицательных приёмочных тестов.
- `reference/pal_copy_oracle.py` — чистый независимый интерпретатор конечного AST и утилиты для меток.
- `reference/test_pal_copy_oracle.py` — тесты эталона (`python -m unittest -v`).
- `fixtures/expected_case_matrix.json` — machine-readable expected pass/fail of *current production* and expected oracle.
- `manifest.json`, `SHA256SUMS.txt` — файлы пакета и контрольные суммы.

**Недопустимое сокращение задачи:** зашить правило `PAL`, использовать метки holdout, расширить полноту простым большим перебором или назвать эмпирическую грамматику доказанной универсальной теоремой.
