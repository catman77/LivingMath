# PATCH002 — controlled before/after

| Корпус, один и тот же request | v0.4.1: узлы / шаги | v0.4.2: узлы / шаги | Fallback | Завершение v0.4.2 |
|---|---:|---:|---:|---|
| nostradamus_original_local_word | 18 / 5 | 383 / 99 | 1 | MAX_NODES |
| mallarme_original | 640 / 141 | 640 / 141 | 0 | MAX_NODES |
| mallarme_reverse | 60 / 12 | 466 / 160 | 2 | MAX_STEPS |

Условия каждой пары одинаковы; фактические requests, budgets, source SHA, digests и proposed/accepted/duplicate/forbidden/resource_limited per operator сохранены в [BEFORE_AFTER.json](BEFORE_AFTER.json). Счётчики v0.4.1 построены только по его реально сохранённому trace; unrecorded_candidate_attempts не угадываются. Новая версия учитывает каждую попытку.

Большее число состояний — результат охвата уже доступных операций, не evidence смысла. Выбранный grammar classifier9/9 при UNDERDETERMINED; его исходник и golden predictions неизменны. Ни один литерарный исход не получает mathematical verified.
