# LM-NL-PROPOSER-002: результат

Установлен **v0.4.10-developer-preview**,93 MCP-инструмента. Два новых метода:
`formal_nl_propose` и `formal_nl_inspect`. Все91 прежние схемы и214 runtime
компонентов сохранены побайтно; изменён entry для подключения отдельного адаптера.
Адрес: `https://fares-september-rebel-board.trycloudflare.com/mcp`.

Источник проходит проверку точных UTF-8 байтов, реальный hosted provider даёт
конкурирующие FOL proposals, а typed decoder может изменить область кванторов
по проверенному следу White Star. Каждый такой move содержит исходный/новый AST,
source spans, настоящий trace и явно добавленную предпосылку. Смысл остаётся
`PROPOSED`; подтверждение происхождения не означает истинность.

Завершено сравнение50 текстов×4 плеча:36 основных,14 контрольных; по9 свежих
вызовов модели на плечо. Gold независимого synthetic holder открыт после
заморозки всех кандидатов. [Таблица A/B/C/D](RESULTS_B_C_RU.md).

B дал70 typed кандидатов против49 у A,20 связаны с реальным AST move. Покрытие
сравнимого synthetic эталона одинаково:40/40. Всего эталонных чтений47;
семь остались UNKNOWN_BOUND при конечной vector проверке. Совпадения с контрольными неэталонными
чтениями в том же конечном классе: A1/B6/C6/D7. Дополнительные кандидаты
не означают лучшее понимание. **WHITE_STAR_INCREMENTAL_BENEFIT_NOT_ESTABLISHED**.
Нейтральные переименования:4/4 пары сохранили alpha-AST набор в каждом плече;
публичный контроль Read/Lost с одинаковым alpha-pattern сохранил разные source refs
и разные предикаты. Человеческая оценка не выполнена: **PARTIAL; semantic generalization NOT_EVALUATED**.

Проверки:447 source PASS,447 installed-wheel PASS и447 PASS в отдельном
production-окружении; legacy1066 PASS/20 прежних SKIP. Прежние31 gates и
869 formal проверок/667 публичных MCP calls PASS. Offline replay подтвердил36
замороженных ответов и102 исходных численных/символьных результата по точному SHA.
Публичные HTTPS/OAuth вызовы и10 adversarial provenance проверок PASS.

Четыре исходные базы целы;75369 начальных файлов и75727 cutover-файлов сохранены.
Исходный audit:4817 записей и прежний последний hash. Все84 journal chains валидны;
629 QA-операций завершились ровно один раз. Новые execution grants не выдавались.
[Полная проверка](PRODUCTION_INTEGRITY.json), [deployment](DEPLOYMENT.json).

[Рабочая последовательность JSON без placeholders](QUICKSTART_RU.md) проверена
через настоящий публичный MCP, включая повторный request_key и replay.
Если ChatGPT показывает старый список методов, переподключите LivingMath по тому
же адресу; актуальный tools/list содержит93 инструмента.

[Реализация и границы](IMPLEMENTATION_REPORT_RU.md), [RCA](RCA_RU.md),
[незакрытые обязательства](UNRESOLVED_OBLIGATIONS.md), [откат](ROLLBACK_RU.md).
