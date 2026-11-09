# Промпт кодовому агенту — Semantic Bridge PATCH002

Ты — инженер-разработчик LivingMath с доступом к действующему GitHub-репозиторию, установленному MCP и окружению для тестов. Твоя задача — **точечно устранить выявленные в EXP02 ошибки**, без перестройки общей архитектуры.

Прочти **целиком** `TZ_RU.md`, `ACCEPTANCE_MATRIX.json`, `fixtures/PATCH002_CASES.json`, `reference/REPORT_RU.md`, `reference/NEXT_AB_PROTOCOL_RU.md`. Сначала проверь code commit развёрнутого `v0.4.14`, snapshot и SHA актуальных файлов `src/lm_suti_assurance/semantic_bridge/contextual/{relations,checker,alpha,engine,contracts,service}.py`; сравни с указанными в `BASELINE.json`. Не начинай с реализации, пока не сформулируешь короткий конкретный RCA.

**Главное:** в `relations.py` сейчас вызывается `fol.countermodels` последовательно для A⇒B и B⇒A. На тривиальном `∃e∃a(Said∧MessageEngineerWrong)⇒∃e∃aSaid` оно тратит 512 моделей на поиск невозможного контрпримера и голодает обратное направление. Не «лечи» это увеличением лимитов. Реализуй сначала sound exact proof для одинаковых смешанных `forall/exists` prefix и булевой матрицы, плюс строгую NNF эквивалентность. Затем сделай fair/symmetric model scheduling, где каждая проверенная модель может проверять обе направленности, а пары получают справедливые кванты.

Сертификаты проверяются **независимым** checker; не использовать результат самого proof-generator как доказательство. Не менять `formal_bridge/fol.py` и исторические ядра. Если нужен внутренний bounded enumerator — реализуй его внутри opt-in contextual layer, обеспечив совместимость с фактической `fol.evaluate`, честные UNKNOWN/partial, точные счётчики и fail-closed в случае ошибок. Задачи не упираются в опасный миллион переборов — держи 32/64 модели для основных regression fixtures и ≤512 для предельных.

Отдельный P0 — исправление **семантической процедуры клиента**. Подготовь два практических файла: проверочный протокол и system/user prompt для LLM, работающей с Semantic Bridge. Требуй сначала различать **содержание сообщения** и **подтверждённый факт**; затем проверять анафору, предпосылки, кванторы, отрицание, время, модальность; формировать несколько source-bound candidates и `OPEN obligations` без ложного `SOURCE_VERIFIED`. Проверь T4 и T6, но не делай server-side словарь русских слов, «понимающий смысл». Внутрь MCP запрещено встраивать ещё одну LLM и скалярный semantic scorer.

Не изменяй существующие 102 tool schemas, если задача решается через текущее `semantic_bridge_register` (`assumptions`, `obligations`, `construction_trace`) и `semantic_bridge_analyze`. Доказанные пары не сливать; source/text refs/immutable provenance сохранить. Новый `PROVED_LOGICAL_EQ` допустим только при двух доказанных направленностях. Контрмодель для A⊭B не доказывает B⇒A. `CHECKED` уровня job не означает закрытие всех рёбер: добавь явные open/decided counters.

Построй новые тесты с **реально исполненным** кодом и сохрани точные receipt:
- в T4 `HmsgE⇒Hskeleton` — proof с нулём model enumerations; `Hskeleton⊭HmsgE` — контрмодель ≤32; инверсия порядка и перестановка пар не влияют на смысл и не блокируют доступные контрпримеры;
- `HmsgBoth⇒HmsgE`, T2 `¬∀P ⇔ ∃¬P`, α и de Morgan, ∀(A∨B) vs ∀A∨∀B;
- `NO_COUNTERMODEL_WITHIN_BOUND` не выдаётся за теорему, proof не может игнорировать предпосылки; bogus type/binder/sort/forged cert отвергается;
- T4 speech-act гипотезы остаются `PROPOSED`, `ANAPHORA:OPEN`, факт ошибки не постулируется из текста;
- T5 формула TRUE, assumption FALSE ⇒ `CONTEXT_INCOMPATIBLE`; T6 temporal unsupported ⇒ LANGUAGE_INSUFFICIENT/OPEN;
- replay, tamper, чужие refs, quotas и исходные 102 tool schemas без неожиданных изменений.

Нельзя переписывать замороженные прошлые runs для их соответствия новой версии. Установи только после offline/staging, сделай backup и rollback план. Если GitHub Actions не стартует из-за биллинга, отметь `CI_NOT_EXECUTED`, а не PASS. Зафиксируй все ошибки, включая собственные. Отчёты должны отдельно называть `PROVED`, `FINITE_CHECKED`, `UNKNOWN`, `SEMANTIC_PROPOSED` и `LLM_UPLIFT_NOT_MEASURED`.

В конце предоставь **один ZIP** с изменёнными исходниками/patch, regression fixtures, независимым checker, исполненными test logs, MCP live receipts, полными SHA/commit/deployment, RCA и двумя LLM-протоколами. Не заявляй G0–G10 PASS без реально выполненных проверок. Если патч не готов, отдай честную частичную поставку и незакрытые gates. Пользователь после твоей работы сам проведёт отдельную независимую приёмку и новые исследовательские тесты.
