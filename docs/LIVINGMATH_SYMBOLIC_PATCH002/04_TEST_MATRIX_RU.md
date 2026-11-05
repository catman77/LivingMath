# Матрица проверок

### T01: baseline grammar

Тренировка: позитивные ABBA, BAAB, AAAA, BBBB, негативные AABB, BBAA, ABAB, BABA. На hidden-наборе ABCCBA(+), ABCBCA(-), ABCABC(-), ABBAABBA(+), AABBAA(+), ABABBA(-), BAABAB(-), AAAAAA(+), ABABAB(-). Должно быть 9/9 для выбранного композиционного правила и сохранённый `UNDERDETERMINED`; отсутствие уникальной грамматики нельзя скрывать.

### T02: Nostradamus controlled comparison

`06_FIXTURE_NOSTRADAMUS.txt`, whitespace, lines, FREE, operators CONCAT/SPLIT/RENAME/REVERSE, seed=119, 128 шагов, max_nodes=384, max_candidates_per_step=4, history_identity=word. Сравнить v0.4.1 и PATCH-002 при **точно одинаковых** остальных параметрах. Проверить fallback при локальной стагнации. Если нет нового доступного фронтира, корректная остановка с явно ограниченной областью исчерпания допустима.

### T03: budgets

`max_steps=0`, `max_nodes=16`, небольшой `max_total_tokens`; нет превышения лимитов, тайм-аутов и неоднозначной остановки.

### T04: identity and symmetry

SSPP, SPSP, PPSS, PSPS. Отличить буквальные слова, alpha-эквивалентные пары и одинаковую SP-normal-form. При `RENAME` не терять исходное имя символа/инволюцию S↔P. При равном свёрнутом значении сохранять несвёрнутую трассу.

### T05: repeat/replay

Повторный прогон с тем же seed, source, request и policy должен давать одинаковый result_digest. Export/replay verify should return REPLAY_MATCH и journal hash PASS. Нарушенные payload/hash должны отвергаться, старые артефакты должны читаться.

### T06: real text and reversal

Малларме: 15 выбранных строк, исходный/обратный порядок. Контроль структуры: same alphabet, no identical source order, comparison не заявляет semantic truth. Нострадамус: первые два катрена, отличие локальной насыщаемости и фиксирование истинных границ.

### T07: diagnostic completeness

При локальном тупике сохранены: counter/fallback, sampled vs unproposed allowed operators, not-yet-tried frontier count, global_exhaustion_proved=false, provenance of selected fallback. Проверить, что отсутствие data не превращается в фиктивное положительное свидетельство.

### T08: legacy

Старые White Star `base_v1`, `cj_v1`, previously saved run IDs и исторические source SHA по-прежнему читаются. Никакой миграции, стирающей provenance.
