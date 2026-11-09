# ПРОМПТ ДЛЯ КОДОВОГО АГЕНТА — SEMANTIC-BRIDGE-PATCH001

Ты работаешь в production-репозитории **catman77/LivingMath**. Задача — реализовать **небольшую добавочную opt-in надстройку Semantic Bridge PATCH001** строго по документу `TZ_RU.md` из приложенного архива. `reference/` — неизменённые доказательные данные предыдущего эксперимента. Не считай этот архив реализацией и не путай желаемые методы с существующими.

## 1. Честный осмотр и RCA перед правками

1. Зафиксируй фактический `git HEAD`, `git status`, версию запущенного MCP, tools/list, ограничения worker, контрольные SHA старых tool schemas и native-кода. При составлении задания baseline main был `e65b1a1e06914d63f6048a04b5e065a610adb68d`, endpoint — v0.4.12/98 tools. Если версия изменилась — зафиксируй различия и адаптируй патч минимально.
2. Прочти `formal_bridge/{fol,engine,service,contracts,mcp}.py`, `nl_proposal/{decoder,service,provenance,contracts}.py`, `udav_core/{service,mcp}.py` и точный bootstrap. Найди, какие существующие функции можно композиционно вызывать без риска регрессий. Документируй в `RCA_RU.md`, почему прежний `source_order → quantifier permutation` не проверяет смысл, а `formal_contrast` на α-паре выдавал `UNKNOWN_BOUND`.
3. Сохрани backup/rollback и снимки контракта. Не обращайся к нерелевантным проектам или пользовательским данным. Никаких background network/provider calls в новом слое.

## 2. Реализация

Создай отдельный `src/lm_suti_assurance/semantic_bridge/` с четырьмя новыми opt-in MCP methods `semantic_bridge_register`, `semantic_bridge_analyze`, `semantic_bridge_inspect`, `semantic_bridge_replay`. Переиспользуй настоящую Workspace/CAS, owner guard, worker isolation, immutable refs и `FormalService`. Не меняй поведение ни одного старого инструмента, в том числе `formal_nl_propose`, `formal_nl_redecode` и `udav_symbolic_explore`.

Главная математика: после `fol.typecheck` проверяй α-эквивалентность через лексические индексы связанных переменных с проверяемым сертификатом; консервативно и точно доказывай H1=>H0 для замкнутых общим `forall`-префиксом булевых матриц (16 строк) с независимым checker. Только остальные направления передавай существующей конечной модели `formal_contrast`; проверяй контрмодели через `fol.evaluate`. Не прячь `UNKNOWN_BOUND` и не объявляй no-countermodel доказательством эквивалентности. Сохраняй **обе** модели при доказанной несравнимости.

Гипотезы (AST), source spans, assumptions, obligations, контексты, независимые результаты и расчётные статусы храни раздельно. Сценарный вектор обязан возвращать `formula_truth`, `assumption_truths`, `applicability`, `source_alignment_status` без подмены смысловой экспертизы. Неподдержанный `future` фиксировать как `LANGUAGE_INSUFFICIENT`/`TYPE_REJECTED`, не домысливать новое FOL. В `assumptions` не пихать непроверяемые языковые пресуппозиции как истинные факты: хранить их отдельными открытыми обязательствами; формализованные предпосылки — только явно предложенные LLM/human.

## 3. Предварительно замороженные test vectors

Используй `reference/SB_EXP01_FROZEN_INPUT.json` без переименования смыслов:
- H0/H2 доказанно α-эквивалентны, **zero** model enumerations;
- H1⇒H0 доказанно, обратное опровергнуто моделью M1;
- H0/H3 несравнимы, предъявить M2 и M3 с двойной проверкой истинности;
- H4 содержит unsupported `future` и не становится допустимым FOL;
- отсутствующая Supervises relation: H0 TRUE при A_exist FALSE => CONTEXT_INCOMPATIBLE;
- `world=open`: UNKNOWN;
- cross-project refs, поддельный source SHA, неправильный UTF8 span, request_key reuse with altered payload, replay with altered content — fail closed;
- actual replay code + independent reference test.

Запусти **все** G0–G9 из `ACCEPTANCE_MATRIX.json`. Сначала дешёвые модульные тесты, затем существующие regression tests, затем ограниченный canary MCP. Не запускай бессмысленные многочасовые/миллиардные перебиратели. Тестовые результаты фиксируй только после реального выполнения, с командами, хешами, run IDs и exit codes.

## 4. Запреты и статус

**Запрещено** модифицировать native White Star, NOPS, CAD, UDAV, алгоритмы FOL оценки и прежние API ради «красоты». Не добавлять серверный LLM, правила русского языка или фиктивное `SEMANTICALLY_VERIFIED`. Не смешивать исходную математическую эквивалентность с совпадением на перебранных моделях. Не ставь `PASS` за неспроведённые или отменённые тесты. Не стирай старые runs/DB/journal. Не публикуй пользовательские источники, ключи и provider receipts с секретами.

Итог: сформируй **единый скачиваемый ZIP**, включающий весь изменённый код или применимый patch, ТЗ-совместимые API-схемы, модульные/integration/negative тесты, результаты с SHA/replay, `IMPLEMENTATION_REPORT_RU.md`, `RCA_RU.md`, `TEST_MATRIX.json`, `BACKUP_ROLLBACK_RU.md`, `CHANGELOG.md`, `MANIFEST_SHA256.txt`. Укажи точные baseline/deployed commits. Если что-то невозможно — дай **PARTIAL** с конкретными блокерами и воспроизводимой RCA, а не сочинённый успех. При необходимости сохранения старых контрактов предпочитай не внедрять проблемную часть, чем незаметно сломать production.

В ходе работы не запрашивай лишних подтверждений: ориентируйся на данное ТЗ и делай наименьшую корректную реализацию. По завершении предоставь архив и краткую матрицу: реализовано / протестировано / развёрнуто / научно не установлено.
