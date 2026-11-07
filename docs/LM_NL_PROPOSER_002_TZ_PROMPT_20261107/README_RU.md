# LM-NL-PROPOSER-002: ТЗ, промпт и экспериментальное основание

Это отдельное следующее задание для кодового агента по уже принятому `LM-FORMAL-001`.

**Основные файлы**:
- `docs/TZ_CODE_AGENT_RU.md` — требования, новый verified-origin/semantic proposer, критерии приёмки и A/B;
- `docs/PROMPT_CODE_AGENT_RU.md` — точный исполняемый промпт агенту;
- `docs/RCA_NEW_EXPERIMENTS_RU.md` — пять диагностических экспериментов с живым MCP, включая SHA/seed/run_id;
- `evidence/LIVE_RUNS.json` — машиночитаемые id и параметры;
- `fixtures/DEV_SOURCE_AND_FOL.json` — явно помеченные dev формулы, **не** результат автономной Белой звезды;
- `tools/preflight_fixtures.py` — локальная независимая проверка source UTF-8 spans и хешей;
- `evidence/PREVIOUS_*` — принятая матрица 0.4.9 и прошлый RCA.

**Результат текущего шага**: наблюдательный и White Star код **не менялся**; запущены диагностические инструменты на подключённом MCP v0.4.9. В частности, доказано, что source-only symbolic layer НЕ возвращает FOL, ручная геометрия меняет White Star graph, фиктивный provider lineage является декларацией, а валидность source spans и typed FOL уже контролируется в существующем Formal Bridge.

**Действия кодового агента**: реализовать новый opt-in `NLProposalBridge/1` как дополнение к уже действующему MCP и дать достоверный live acceptance/ablation. Не переписывать Formal Bridge, symbolic/native, numerical Белую звезду. Отделить mathematical syntax/proofs, источник и semantic plausibility. Изменения должны пережить replay, отрицательные проверки и независимый holdout. Входные/эталонные фразы здесь служат **открытым dev**, не скрытым тестом: для blind генератору требуется независимый label holder.
