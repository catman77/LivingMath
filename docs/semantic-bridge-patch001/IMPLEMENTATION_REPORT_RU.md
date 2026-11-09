# Semantic Bridge PATCH001: реализация и приёмка

**G0–G9: PASS.** Реализовано, локально проверено и развёрнуто четыре новых
opt-in инструмента. Production `v0.4.13-developer-preview`,102 tools,
`semantic-bridge001-20261109T024106Z`. Адрес `https://difficulty-nightlife-rca-missions.trycloudflare.com/mcp` сохранён,
аутентификация по прежней политике владельца отсутствует.

Baseline commit: `e65b1a1e06914d63f6048a04b5e065a610adb68d`.
Точный deployed code commit: `963fe1dfd0be96f003d8831cf8354e4bd6e7768e`. Последующие публикационные commits
изменяют документацию/receipts, не runtime-код. Source snapshot/tag/delivery SHA
публикуются в PUBLICATION_CERTIFICATE.json и PACKAGE_CONTENTS.json релизного ZIP.
[Матрица](TEST_MATRIX.json), [происхождение](PROVENANCE.json), [MCP-примеры](QUICKSTART_RU.md).
[План](IMPLEMENTATION_PLAN.md) · [Изменённые файлы](CHANGED_FILES.md) ·
[Changelog](CHANGELOG.md) · [Поставка](DELIVERY_RU.md).

## Реализовано

`semantic_bridge_register/analyze/inspect/replay` находятся в добавочном
`semantic_bridge/contextual/`, поскольку родительский пакет уже содержит9
legacy методов. Старые233 исходных файла, все98 схемы, Formal Bridge, NL decoder,
UDAV, CAD и native сохранены байт-в-байт. Из прежнего runtime изменён только
bootstrap: опциональная регистрация и capabilities; пакет Python0.4.13.dev0.

Регистрация проверяет реальные source refs через FormalService.owned, SHA,
UTF8 spans, существование AST paths и immutable request keys. Формулы,
assumptions, OPEN obligations, construction trace и creator declaration раздельны.
Неподдержанные/невалидные кандидаты сохраняются с причиной. Derived language_gap
не добавляет и не переименовывает пользовательские obligations.

После неизменённого FOL typecheck α-норма использует лексический binder index,
сохраняет сорт/предикат/позиции аргументов и порядок дочерних узлов. Независимый
checker заново строит норму. Затем разрешён только одинаковый forall-prefix
с Boolean matrix без внутренних кванторов: не больше10 позиционных атомов,
все2^k assignments, отдельный сертификат и независимая реконструкция.
Equality остаётся консервативным независимым атомом, не новой аксиомой.

Остальные направления используют неизменённый fol.countermodels в отдельном
изолированном worker. Поиск ведётся в ALL_CANDIDATE_ASSUMPTIONS_HOLD; directional
guards — только ограничения поиска. Каждая модель проверяется fol.evaluate для
обеих исходных формул и assumptions, затем независимым внешним evaluator.
Два направления несравнимости сохраняются, гипотезы не объединяются.

## Фактически протестировано

| Проверка | Итог |
|---|---|
| Исходный baseline suite |485 PASS|
| Финальный установленный wheel |511 PASS, из них26 новых|
| Legacy suite с оригинальной frozen017 policy |1066 PASS/20 прежних SKIP|
| Настоящий staging MCP |65 PASS/102 tools|
| Настоящий публичный HTTPS MCP |65 PASS/102 tools|
| H0/H2 |PROVED_ALPHA_EQ,0 formal_contrast/переборов|
| H1⇒H0 |PROVED_ENTAILMENT,16 строк; обратное имеет M1|
| H0/H3 |Обе независимые контрмодели M2/M3, несравнимость|
| M4 |H0 TRUE, A_exist FALSE, CONTEXT_INCOMPATIBLE|
| M5 open |UNKNOWN; нет принудительного FALSE|
| H4 future |LANGUAGE_INSUFFICIENT, сохранён OPEN gap|
| Дополнительное математическое ревью |44 certificates/704 finite implications PASS|
| Register/analyze replay |Реальный пересчёт совпал, standalone CLI тоже MATCH|
| Подменённые packet/result/binding bundles |3/3 отклонены|

Независимый SB_EXP01_VERIFY.py запущен из отдельной копии; результат в точности
совпал с предоставленным JSON. Исходный reference/ не переписывался. Все20
типизированных scenario cells и5 unsupported cells сверены; M4 означает отсутствие
Supervises edges при **непустом** manager domain, не отсутствие сорта.

Пределы:6 гипотез,8 исходных obligations/16 links на гипотезу,10 пар/8 сценариев,
128 FOL nodes/depth16,10 Boolean atoms. Общая symbolic quota2 active/16 queued,
прежние5 CPU sec/6 wall sec/512MiB. [Реальные measurements](RESOURCE_MEASUREMENTS.json).
Исчерпанный evaluator немедленно завершает анализ UNKNOWN_BOUND; его оставшаяся
step allocation учитывается консервативно как исчерпанная. Halt сохраняет уже
проверенную часть и не означает0 различий или эквивалентность.

## Развёрнуто и сохранено

До реализации:4 SQLite online backup и полный архив106566 Workspace файлов.
Во время остановленного HTTP — quiescent SQLite snapshot и delta overlay.
Туннель не перезапускался, staging-проекты не импортировались. Проверены исходные
inode/path, все прежние строки/байты и journal hash-prefix; canonical audit
сохранил4817 записей и прежний head. [Integrity](PRODUCTION_INTEGRITY.json),
[откат](BACKUP_ROLLBACK_RU.md). Новая база вместо рабочей не создавалась.
QA-источники изолированы; неизменённые AGENTS.md и87 пользовательских правок
вне задачи сохраняются. Полные request/response/wire находятся в release ZIP.

Новый слой разделяет существующую проверку выдачи refs по проектам. Публичный
endpoint остаётся anonymous по указанию владельца; индивидуальную сетевую
аутентификацию этот патч не добавляет и не заявляет.

## Научно не установлено

Это проверка конечного инженерного механизма на заранее заданном synthetic
SB-EXP01. LLM/human предложили формулы и сценарии вне MCP. Сервер не оценивает
русский смысл, намерение автора, causal LLM uplift или физическую реализацию.
TYPECHECK, bytes/provenance, exact proof и replay не лицензируют источник.
source_alignment остаётся PROPOSED/LANGUAGE_INSUFFICIENT,
semantic_adjudication=NOT_EVALUATED, LLM_calls=0, execution_permission=false.

Предпосылки — явные предложения, linguistic obligations остаются OPEN.
Пустые assumptions означают NO_DECLARED_ASSUMPTIONS. UNKNOWN_BOUND и
FINITE_SAME_ON_BOUND не являются EQUIVALENT. CPU-bound replay может отличаться
точкой отсечения и тогда честно отклоняется. [RCA и сохранённые ошибки](RCA_RU.md).
