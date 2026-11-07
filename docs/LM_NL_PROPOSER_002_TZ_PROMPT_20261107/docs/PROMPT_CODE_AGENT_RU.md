# Рабочий промпт кодовому агенту — LM-NL-PROPOSER-002

Ты работаешь **в действительном репозитории** `catman77/LivingMath` и развёрнутом MCP `SUTI–Bridge–LivingMath`. Это продолжение принятого `LM-FORMAL-001`. Прочитай `docs/TZ_CODE_AGENT_RU.md` и `docs/RCA_NEW_EXPERIMENTS_RU.md`, а также последние `docs/formal-bridge001/QUICKSTART_RU.md`, `IMPLEMENTATION_REPORT_RU.md`, `LIMITATIONS_AND_NEXT_OBLIGATIONS.md`, `docs/symbolic-v1/QUICKSTART_RU.md`, `docs/white-star/QUICKSTART_RU.md`. Примеры/refs в этом ZIP — действительно наблюдавшиеся на сервере, но могут быть недоступны из твоего workspace; **не подделывай** run, при необходимости создай новый.

**Главная цель**: не ещё одна таблица language accuracy, а работающий *source-bound* конвейер, который из текста и структурных предложений Белой звезды порождает **несколько** typed FormalCandidate с конкретным проверяемым происхождением, сохраняет альтернативы и использует существующие независимые FOL/model/contrast проверки. Не выдавай типизацию за проверку авторского смысла. Белая звезда — поисковый генератор альтернатив, а не семантический оракул.

## Последовательность работы, без пропусков

1. Сними `git HEAD`, `git status`, deployed version, kernel hashes, список MCP tools, старые proofs и тесты. Проверь, что `formal_interpret` сохраняет explicit/imported FOL и **не** заявляет автоматического русского декодера. Не пиши новые методы до этого аудита.
2. Запусти baseline существующего CFG/DFA/FOL, regression и current source-provenance/replay tests. Зафиксируй серверное поведение по четырём контрпримерам E1–E5 из RCA. Особенно E3: фиктивный `white_star` run accepted as *declaration* сегодня. Новая verified-интеграция должна делать отказ, не ломая import API.
3. Реализуй минимальный отдельный `NLProposalBridge/1` поверх установленного `formal-bridge/1`/`white_star_*`; один опциональный новый MCP вызов, расширенный inspect если нужно. Не создавай параллельный сервер, не меняй численное C++ ядро, не заменяй CAD/UDAV.
4. Для source-only режима используй явно разрешённый доступный provider (LLM как фиксированную функцию); отчёт обязан фиксировать provider/model/version, prompt digest, источник, seed, usage, latency, rights и provenance. Если LLM недоступна — оформи `PROVIDER_UNAVAILABLE`, отладь импортный режим с ручными dev examples, но не объявляй автономную генерацию выполненной.
5. Реализуй **реальный** White Star bridge: sourced text + verified symbolic DAG/numeric frame → предложенный `CandidateMove` → проверяемый typed AST. Вариант, где LLM только видит `ALIGN/TENSION` и независимо пишет любую формулу, НЕ получает `VERIFIED_ORIGIN` без проверяемой move/trace. Никакой маскировки под mathematical entailment.
6. Поставь жёсткий trust-gate: источниковый sha/run/frame/node/AST-hash на конкретном проекте, полная цепочка свидетельств. Подставной `run_id=0×64`, `F99`, чужой workspace, stale snapshot, incorrect source spans, typed-but-semantically unsupported candidates должны получить разные статусы; последние допустимы как `PROPOSED` без поддержки смысла.
7. Доведи до работающего end-to-end пилота с несколькими competing readings (на тех же явных сигнатурах, плюс на новых фразах) и независимым `formal_model_check`/`formal_contrast`. Сохрани альтернативы, различающие конечные модели, а при нехватке информации `UNKNOWN/ABSTAIN`. Не оптимизируй на «одной угаданной истине».
8. Проведи matched A/B/C/D: source-only vs WhiteStar vs shuffled frames vs alternate coordinates, одинаковые LLM calls/temperatures/budgets. Если WhiteStar не улучшает coverage, **так и напиши**; корректный новый интерфейс и научная полезность WhiteStar — два разных критерия.
9. Только после dev-проверок заморозь код, промпты, manifests и SHA. Проведи blind 36-source тест по независимым феноменам/источникам; labels отделены от кодовой базы/LLM inputs. Если независимых людей для human judgment нет, отчёт `NOT_EXECUTED` для claims об адекватности реальным русским фразам. Внутренний synthetic gold отдельно.
10. Запусти по крайней мере 5 falsification/tamper tests, replay и официальные regression проверки. Подтверди сохранение old kernels/records либо зафиксируй изменения и RCA. Выгрузи `git diff`, исходники изменённых модулей, тесты, машинные логи, actual MCP request/response, SHA/replay, указание cpu/rss/LLM cost, rollback и единый ZIP.

## Критерии готовности

- Подлинное происхождение White Star проверяется **в новом пути**, импорт по старому API не ломается.
- На одной фразе ≥2 формальные альтернативы с source/trace, хотя бы одна **контрмодель** для их различия, независимый `TYPED` результат, ни одной выдуманной семантической теоремы.
- При отключённой Белой звезде доступен source-only baseline; при отсутствии provider — честный отказ, а не фальшивое выполнение.
- Тесты реально проходят на подключённом MCP (не только локальные unit); replay и разделение false/unknown/under-specified.
- Evidence report описывает *какая альтернатива создана White Star после конкретного оператора*, либо White Star contribution=0.
- Нет специальных production-веток по известным словам или задачам.

## Стоп-условия

Если P0 trust-gate не пройден, не переходи к демонстрации «понимания»; сначала исправь. Если работающий FOL-декодер требует LLM, а provider отсутствует, не имитируй его правилами, запиши `BLOCKED_PROVIDER`. Если B не лучше source-only/shuffled на blind matched evaluation, не считай White Star улучшением. Если есть TYPE_OK, но source semantics не поддержана — сохраняй как `PROPOSED` и явную added assumption, не считай proof. Если к концу бюджетов результата нет — `PARTIAL` с RCA, никакой бесконечной лестницы попыток.

## Сдача

Полный фактический `IMPLEMENTATION_REPORT_RU.md`, `RCA_RU.md`, `REGRESSION_REPORT_RU.md`, `MCP_SCHEMA_DIFF.json`, `PROVENANCE_ATTACK_MATRIX.json`, `ARM_ABLATION_MATRIX.json`, `PROPOSAL_GRAPH_EXAMPLES.json`, `INDEPENDENT_CHECKER_RECEIPTS.json`, `UNRESOLVED_OBLIGATIONS.md`, `REAL_FILES_CHANGED.json`, tests и один **реально скачиваемый** ZIP. Раскрыть точные запросы, actual refs, statuses, неполные ветки и стоимость. Не обещать «я закончу позже».
