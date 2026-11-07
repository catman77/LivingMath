# PROMPT для кодового агента — LM-FORMAL-001

Ты работаешь **в реальном репозитории установленного LivingMath/SUTI-Bridge MCP**. Рядом прилагаются воспроизводимый предыдущий архив, архитектура следующего Formal Bridge, эталонный Python-код и материалы испытаний. Прочти их ПЕРЕД изменениями. Не создавай альтернативный сервер, не импортируй эталонный оракул в production synthesizer и не называй тестовые проверки «доказательством правильного смысла».

## Порядок исполнения

1. Сними фактический `git rev-parse HEAD`, состояние working tree, версии модулей, `bridge_system_status`, доступные контракты MCP. Сверь с `v0.4.8-developer-preview` / `observer_synthesis_v1/5-role-branching`. Если версии не совпадают — зафиксируй discrepancy. Найди код `_candidate_generation`, `role_branching`, независимого `observer_verify`, dataset_store/inspect/replay. Сохрани git hash и SHA компонентов.
2. Запусти существующие unit/integration/replay тесты ДО модификации. Возьми прошлые ошибки Dyck(2), четные палиндромы, even-a, ε false positive как зафиксированные regression candidates. Не переделывай их исходные метки.
3. Реализуй LM-F1/F2: общие `EPS`, `Term`, `Nonterminal`, `Seq`, `Alt` с независимым start symbol, bounded typed grammar search, candidate preservation. Укажи класс гипотез, который реально перебирается (не «все CFG»). Откажись от хардкода «Dyck/Palindrome/Parity» — названия могут появляться только в тестовом oracle.
4. Реализуй строгий независимый verifier дерева/packed forest: source spans, terminal role, production ID, child ordering, start, source fingerprint. Проверь forged certificates. При cyclic nullable forest и exhausted budget строго `UNKNOWN_BOUND`, не ложное отрицание.
5. Реализуй LM-F3: ограниченный DFA hypothesis search с witness transition table, min-state as resource constraint (не теорема минимальности без отдельной проверки), возможностью обучаться even-a на тех же sealed train/query.
6. Реализуй LM-F5: contrastive запросы между train-compatible гипотезами. **Обязательный первый кейс:** различить `S→ab|aSb` и `E→ε|aEb` запросом `ε`; затем `Dyck(2)` против generic untyped matching — `SB` (или другой точно проверенный пример).
7. Только после этих гейтов реализуй (или оформь отдельную минимальную подсистему) LM-F6: typed formal interpretation store/proposer contract и finite-model evaluator. Не обещай общий русский NLP. Для первой демонстрации три *предложенные* версии одной фразы, три проверяемых formula AST, две контрмодели. Candidate generator может быть внешним source-bound LLM (если доступен), но каждый вывод хранит `PROPOSED` и не получает статуса mathematically verified из confidence текста.
8. Заморозь гипотезы перед query, проверь отсутствие меток в predict, проведи независимый holdout с позитивными и трудными негативными примерами, прогон reference oracle вне сервера, replay и tamper. Сравни `role_branching_ast`, `auto` и новый режим на одном train/query без ручного выбора удачного зерна.
9. При частичном выполнении оставь НЕЗАКРЫТЫЕ этапы в `NOT_IMPLEMENTED/NOT_EXECUTED`; выдай RCA, реальный список изменений и отчёт. Не говори «готово», если хотя бы одна критическая ветка не запускалась.

## Особенно важно

Наш конечный научный критерий — не «ИИ назвал смысл», а **воспроизводимые разные формальные чтения одного материала, способные давать различные следствия и контрмодели**. Белая звезда производит варианты структур, живое математическое ядро строит и проверяет правила, внешний источник даёт интерпретации и объяснения, а независимый checker запрещает выдавать предположения за теоремы.

Сохраняй различие трёх уровней: `source-aligned proposal`, `typechecked formal representation`, `checked consequence in stated model`. Никогда не сокращай это до одного `confidence`.

## Бюджеты/пределы

Используй не более текущего серверного лимита для онлайн-эндпоинтов, если не оговорено явно; локальные offline проверки могут иметь самостоятельный бюджет, но должны сообщить CPU/RSS и cache/memoization. Никаких многочасовых прогонов для «просто посмотреть» и бессмысленного увеличения `max_proposals`. Лучше один минимальный различающий пример, чем тысяча случайных строк.

Приоритет P0→P1→P2→P3→P4. Изменения передавай с тестами и подписями SHA. Итог — один ZIP со всеми кодовыми изменениями, воспроизводимыми фикстурами, результатами и README запуска, а также чистый git diff. В отчёте отдельно перечисли, какие файлы действительно изменены в репозитории.
