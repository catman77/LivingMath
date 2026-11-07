# Промпт кодовому агенту: LM-NL-CAUSAL-003

Работаешь с **существующим** репозиторием `catman77/LivingMath` на основе релиза v0.4.10. Приложены `REPORT_RU.md`, `TZ_CODE_AGENT_RU.md`, локальная диагностика и precommitted fixtures. **Не пересоздавай** ядра White Star, CAD, UDAV, Symbolic V1 и Formal Bridge.

Исследовательская цель: устранить двойную интервенцию текущего `matched_ablation` и выполнить настоящий frozen counterfactual по **одному** реальному provider receipt. Кандидат White Star U21–U25 точно воспроизводится 1 транспозицией кванторов без White Star (`5/5` SHA; скрипт в пакете). **Не заявляй** semantic benefit за этот результат.

Обязательный порядок:

1. Проверь актуальную сборку, git SHA, tool schemas и статус хранилища. Прочти `src/lm_suti_assurance/nl_proposal/{decoder,service,provenance}.py`, `formal_bridge/fol.py`, официальный frozen receipt/replay. Зафиксируй baseline и внешний gate до правок.
2. Сначала попытайся извлечь старый C run из `nl_independent_eval_20261107` без LLM; если connector недоступен, диагностируй tunnel/service и workspace. Не выдавай `NOT_FOUND` и timeout за отсутствие объекта без фактической проверки.
3. Имплементируй opt-in `formal_nl_redecode` по ТЗ: 4 arm на строго одинаковом source, LLM response, signature, base AST. Инварианты `same raw_output_sha256` и `model_calls_delta=0` — жёсткие. Sham меняет ТОЛЬКО decoder input, а не prompt; primitive closure не читает White Star и golden labels.
4. Повтори открытые U21–U25: истинностное расхождение 176/530, SHA White Star wide = SHA обычной транспозиции. Проверь U26 как известную ошибку эталона (`EXCLUDED_INVALID_ORACLE`). Сделай дополнительные отрицательные тесты на разные типы в одном кванторе, захват переменной, negation scope, missing/fake trace, foreign project, changed receipt, budget exhaustion.
5. Выполни **новую скрытую** проверку на 3+ кванторах и формальных не-симметриях, сравни с primitive closure на том же frozen answer. Для эмпирической semantic licensing не заменяй экспертов синтетическим holder.
6. Проверь полную backward compatibility и безопасность. Проведи реальный install/replay/production MCP (если доступен); приложи signed/sha receipts, честно пометь gaps.
7. Отдай один ZIP со всеми патчами, тестами, отчетом RCA, ограничениями и instructions rollback. Не включай credentials, приватный источник без разрешения или исполняемый неподписанный код из receipt.

Статусы: `TRACE_LINK_CHECKED` подтверждает только структурное происхождение; `TYPED` — типы; `FINITE_RELATION_CHECKED` — вектор на заданных моделях; `SEMANTICALLY_LICENSED` — только независимая человеческая экспертиза. Ни одна из первых трёх меток не подменяет четвёртую.

**При неуспехе:** дать точный RCA и список NOT_EXECUTED; не переименовывать старый контрфакт и не компенсировать провал дополнительными LLM вызовами. Минимальная ценность результата — корректное разделение причинных факторов и воспроизводимая граница того, что White Star пока не добавляет.
