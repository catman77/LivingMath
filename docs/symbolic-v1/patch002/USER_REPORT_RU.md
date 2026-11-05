# PATCH002 — результат для пользователя

Production обновлён до **v0.4.2-developer-preview**, адрес прежний: https://fares-september-rebel-board.trycloudflare.com/mcp.

Исправлен конкретный тупик исследователя: локальное повторение больше не завершает
поиск, пока остаётся untried сохранённый фронтир и исходный ресурсный бюджет.
При смене узла сохраняются причина, точная операция, source spans и DAG.

| Корпус, один и тот же request | v0.4.1: узлы / шаги | v0.4.2: узлы / шаги | Fallback | Завершение v0.4.2 |
|---|---:|---:|---:|---|
| nostradamus_original_local_word | 18 / 5 | 383 / 99 | 1 | MAX_NODES |
| mallarme_original | 640 / 141 | 640 / 141 | 0 | MAX_NODES |
| mallarme_reverse | 60 / 12 | 466 / 160 | 2 | MAX_STEPS |

Лимиты не увеличены. Исходный локальный Удав и грамматический индуктор сохранены.
Выбранная грамматическая гипотеза остаётся9/9 при UNDERDETERMINED семейства.
Количество узлов показывает охват структур, а не обнаружение литературного смысла.

Проверки:272 PASS source и wheel,1066 PASS/20 SKIP legacy,247 staging и248
production MCP,38 controlled checks. Все исходные rows/objects/hash-chain prefixes
сохранены,19 журналов валидны. Старые symbolic и numerical replay работают.

[Полный отчёт](PATCH002_IMPLEMENTATION_RU.md), [RCA](RCA_RU.md),
[JSON результатов](REGRESSION_RESULTS.json), [before/after](BEFORE_AFTER.json).
Матрица T01–T08 PASS в указанной области; full pentest/hosted CI не проводились.
Все75 схем прежние; после HTTP restart при обрыве старой сессии достаточно
переподключить LivingMath по тому же адресу. Дополнительные права не требуются.
