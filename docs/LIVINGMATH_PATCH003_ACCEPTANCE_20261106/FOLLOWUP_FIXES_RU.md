# Минимальные правки после приёмки PATCH-003

## FIX-A — доказательная отчётность, P0

**RCA:** `summary.assumptions` содержит `all_local_peaks_filled` для `cells.policy=none`, `bigons_only` и `diamonds_only`, несмотря на `unresolved_peaks > 0`. Следствие — ложная метаданная предпосылка при правильном `pi1_status=NOT_PROVED`.

**ТЗ:** строить assumptions только из *фактически проверенных* условий. При `policy != all_local_peaks` показывать `selected_cells_policy`, `unresolved_peaks`, `partial_attachment`; не включать `all_local_peaks_filled` до `unresolved_peaks==0`. Checker и frozen numeric/SP engine не трогать. Regression test на N=6 bigons/diamonds и N=10 none.

## FIX-B — действительное порождение наблюдателя, P1

**RCA:** сервер умеет исполнять `SPLIT/SPLIT/CONCAT` и сохранять `context_relations`, но предиктор по-прежнему опирается на `pair_0_max` (`BUILTIN`). Ответы `synthesis_status=NO_VERIFIABLE_NEW_OBSERVER` корректны, но цель появления полезного собственного наблюдателя не достигнута.

**ТЗ:** дать один заранее зафиксированный класс задач, где целевой различающий предикат *не входит* в builtin registry, и синтезировать его как finite compositional observer из разрешённых операций. Сохранять полный AST, input/outputs, исходные байтовые span, независимый verifier и ablation. Достаточно локальной конечной конструктивной демонстрации; не заявлять open-ended learning по одному успеху.

Acceptance:
1. Запретить `pair_0_max`, `pair_0_min`, `pair_0_final` в allowlist и фактически отключить зависимости.
2. Положительный test должен вывести `DERIVED_FROM_OPERATORS` *как новый feature с `execution_verified=true`*, а не лишь `context_relation`.
3. Замороженная версия нового признака должна улучшить отложенную метрику против отключенного режима; train/heldout IDs и labels не смешиваются.
4. Один изменённый шаг AST / неверный output hash / unsupported operator — `REJECTED`, никакой тихой подмены builtin.
5. Указать честные границы: finite empirical candidate ≠ universal invariant.

## FIX-C — корпусные данные, P2

Проверить source-bound дерево century→quatrain→line→word на всех 942 основных катренах, версии/варианты редакций, отдельные `pair_id`, пер-вариант α-канонизацию и равные ресурсы для `global_alpha`, `local_alpha`, `punctuation`, `length`, majority. Не брать числа с разных validation splits за одну таблицу. Использовать коллекции датасетов для обхода лимитов, не снимать ограничения workers.

## Готовый промпт кодовому агенту

«Возьми установленный PATCH-003 `v0.4.3-developer-preview` и приложенный протокол приёмки. Не переписывай numeric White Star, symbolic_v1, SP 2-complex и независимый verifier. Исправь только FIX-A и минимальную P1 реализацию FIX-B. FIX-C — воспроизводимый корпусный harness без новых семантических аксиом. Сначала прогони текущие 12 локальных тестов и server regression, затем новые негативные и позитивные fixtures. Верни commit, patch, exact MCP requests, run IDs, SHA-256 и матрицу PASS/FAIL. Запрет на fake success, builtin-as-discovery, подмену H1→π1, утечку holdout и многочасовые прогоны». 
