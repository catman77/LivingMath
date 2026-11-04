# Промпт Codex — RELEASE-R0/R1

Ты работаешь над LivingMath × SUTI по roadmap `ROADMAP_LM_SUTI_RELEASE_V0_1.md` и ТЗ `TZ_RELEASE_R0_R1.md`. Источник: приложенный оригинальный `LM_SUTI_ASSURANCE_003_DELIVERY.zip` с вложенными историческими 001/002. Задача — сделать пользовательский developer-preview путь из существующего проверяемого QA-ядра. Это НЕ новый математический эксперимент.

Сначала инвентаризируй существующую архитектуру, полные протоколы, commit/source hashes, schemas, test/replay commands, split between verifier/binder/LLM proposer. Проверь SHA-манифест поставки; зафиксируй baseline before changes. Сохрани все архивы, raw results, negative controls. Начни с read-only действий.

В изолированной ветке реализуй R0/R1: единое ядро или тонкий facade к frozen core, one-user CLI workflow, явно типизированные artifacts, human-readable reports, export/offline replay и ручной путь предложения кандидата. Оставь модель как необязательный proposal adapter, не как авторитет. Используй существующие проверенные semantics и не меняй правило admission ради удобства. Если wrapper не способен применить существующие schemas без потери поля — FAIL, не дополняй данные догадкой.

Никакого Qwen/моделей малого размера, нового обучения, агентов, расширения языка, мегаперебора, RH-доказательства или физического FTL. Native SUTI и Lean не подключай: только укажи NOT_EXECUTED/UNAVAILABLE. Живые production и MCP/OAuth/TLS не трогай. Защиту от path traversal/секретов и publication rights включи с самого начала.

Обязательные проверяемые случаи: historical 23/24 false ENTAILED, корректное bounded proof, потеря source field при проекции, UNKNOWN/HOLD, несогласованность source/scope, offline replay без сети и модели, clean install. Отдельно измерь (не выдумывай) сколько шагов требует пользователь от source import до выгрузки валидного bundle. После реализации запусти старые тесты и новый smoke, зафиксируй выводы без подтасовки. Не исправляй ошибочные ответы моделей; они остаются в журнале как отрицательные записи.

Финал: сформируй все deliverables из ТЗ, сводку PASS/FAIL по каждому gate и конкретный список того, что осталось до R2 и R3. Укажи реальные версии и hashes, а не предположения. Если blocked, выдай точный blocker, репродукцию и минимальный патч. Не называй QA успех production release.
