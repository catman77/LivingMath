# Промпт кодовому агенту

Ты модифицируешь текущий действующий LivingMath v0.4.1 `symbolic_v1/1-patch001`. Прочти `README_RU.md`, отчёт и ТЗ PATCH-002. Используй именно текущий production source checkout, не реконструируй сервер с нуля и не заменяй его прошлой версией из предположений.

Задача строго ограничена: bounded deterministic fallback при локальной стагнации символьного Удава и проверяемые diagnostics. Сохрани все интерфейсы PATCH-001, исходный алгоритм White Star и корректность SP/alpha witness.

Сначала проведи source-level RCA для `NO_NOVEL_CANDIDATES` по воспроизводимому Nostradamus fixture и `run_id=61c5af7aa611ed03e914ec72848a0ec84c608a785b44cab4c286696ec6001475`. Диагностика сообщает непробованный оператор RENAME и неутверждённое полное исчерпание. Проверь, что тупик действительно обусловлен policy/frontier, а не спецификой данных; не переноси выводы из вариантов с разными операторами без контролируемого сравнения.

Реализуй минимальный патч, без новых серверных подсистем. Не увеличивай ресурсы. Пиши автоматические unit/property/integration тесты из `04_TEST_MATRIX_RU.md`. Сохрани предыдущие registry, data-only export, replay, exact source provenance и immutable журнал. Проверь старую numeric White Star и новый grammar predictive.

Доставь воспроизводимый архив: diff/patch к текущему production source, тесты и команды их запуска, отчет RCA с evidence, before/after таблицу на одинаковых запросах и бюджетах, коды/ID MCP, результаты golden regression и новый deployment/version hash. Если P0 невозможно закрыть безопасно — фиксируй blocker и контрпример, не заменяй результат отчётом о запланированной работе.
