# LivingMath — Recursive / Nonlocal Observer PATCH-004

**Состояние:** исследование выполнено; этот ZIP — **ТЗ и эталон для кодового агента**, а не обновлённые исходники MCP. Проверенная на момент исследования production версия: `v0.4.5-developer-preview`, `fix-b2-20261106T025708Z`. Актуальную версию агент обязан проверить повторно.

**С чего начать агенту:** открой `05_PROMPT_CODE_AGENT_RU.md`; затем `03_TECHNICAL_SPEC_RU.md` и `02_FORMAL_MODEL_RU.md`. Не нужно согласовывать новый проект с нуля.

## Принципиальный результат

Существующий `symbolic_v1` уже находит рекурсивный операторный AST палиндрома и переносит его на новые длины (64/64, 256/256). Новый `observer_synthesis_v1/2` видит тот же AST как `TRAIN_COMPATIBLE`, но не может зарегистрировать его: `NO_LABELLED_DISTINGUISHING_CONTEXT`. Свежие реальные серверные прогоны с уникальными request_key повторили отказ. Это узкий дефект интеграции механизма синтеза.

Расширение на COPY (две одинаковые половины) — отдельная research-stage задача: такого AST действующий сервер пока сам не нашёл. Нельзя выдавать существование приложенного референса за его открытие.

## Содержимое архива

| Путь | Назначение |
|---|---|
| `01_RESEARCH_RCA_RU.md` | Факты серверных экспериментов, точный RCA, ресурсные границы |
| `02_FORMAL_MODEL_RU.md` | Типы, семантика рекурсивной композиции, границы сертификатов |
| `03_TECHNICAL_SPEC_RU.md` | Полное ТЗ P0 PAL, P1 COPY, P2 дальнейшие полигоны |
| `04_MCP_CONTRACTS_RU.md` | Аддитивные API-контракты и пример evidence, помеченный как proposed |
| `05_PROMPT_CODE_AGENT_RU.md` | Готовый промпт для реализации в настоящем репозитории |
| `06_ACCEPTANCE_MATRIX_RU.md` | Gate A01–A25, B01–B06 и P2 |
| `07_RESEARCH_ROADMAP_RU.md` | Маршрут Dyck/Нострадамус после положительной приёмки |
| `reference/typed_ast_reference.py` | Отдельный **ручной** эмиттер/интерпретатор typed PAL/COPY AST |
| `reference/independent_checker.py` | Иная реализация верификатора операторных трасс, без обращения к evaluate |
| `reference/test_typed_ast.py` | 16 unit tests; полные Σ⁴, Σ⁶, Σ⁸ и adversarial corruption |
| `fixtures/` | Generated full train и запросы; query-only без меток, gold отдельно |
| `reports/` | Логи исполняемого эталона, прошлый run manifest, новые live run IDs |
| `SHA256SUMS.txt` | SHA256 содержимого файлов без собственного манифеста |

## Быстрый локальный тест

```bash
cd reference
python test_typed_ast.py
python typed_ast_reference.py --rule PAL --length 6
python typed_ast_reference.py --rule PAL --length 8
python typed_ast_reference.py --rule COPY --length 6
python typed_ast_reference.py --rule COPY --length 8
```

Локально пройдено **16/16 тестов**. Получены PAL и COPY 64/64, 256/256; это подтверждает правильность двух **заранее заданных** операторных вычислителей на конечном корпусе и независимой повторной проверки их traces, но не доказывает работу production MCP после предлагаемого патча.

## Главные запреты

Не переписывать численную Белую звезду, `symbolic_v1`, 2-комплексы и UDAV. Не создавать новый DSL. Не использовать LLM в математическом ядре. Не подменять выделение структур алгоритмом поиска именованных строк. Не давать авторизованные новые права через ZIP. Не возвращать FALSE вместо UNKNOWN вне domain. Не объединять статистику на holdout с доказательством уникальности грамматики.

## Внимание к старым запускам

На этом MCP одинаковый `request_key` сохраняет прежний результат исторически, даже после нового deploy. Для проверки изменений всегда **новый `request_key`** и сверка `bridge_system_status` / `kernel_binding`.
