# PATCH004: LivingMath Recursive Observer

Установлен **v0.4.6-developer-preview**, deployment **`recursive004-20261106T060730Z`**.
URL сохранён: https://fares-september-rebel-board.trycloudflare.com/mcp.
Полный публичный HTTPS/OAuth MCP прогон: **910 PASS**, **360 реальных tools/call**,
все **A01–A25 / B01–B06 PASS**. В числе проверок320 отдельных локальных
вызовов supplied-AST evaluator/checker; они явно не считаются MCP-discovery.
Стенд: 910 PASS. Полные request/response и wire включены в delivery ZIP,
точные gates — [acceptance_matrix.json](acceptance_matrix.json).

## Что стало работать

Существующая рекурсивная гипотеза теперь проходит promotion в immutable feature,
исполняемую через настоящие SPLIT/REVERSE и полное равенство токенных слов.
Генератор также самостоятельно строит сравнение двух фрагментов после структурного
разреза. Нет новых фундаментальных операций, программируемого DSL, LLM или
language-name flags в production. Ручной AST остаётся отдельным evaluator-control.

- PAL feature **`derived_ee42a6c799ce3ba3a777`**, AST `b5c20366e2902983352e88b017f458f7244c16145cde7d502ace9757b5c4170f`.
- COPY feature **`derived_cf773c00dc649edfb1cb`**, AST `d4eb15cc1f5b69ad630dcded5a587ab9dbdc9629de2c2e6e0b9969588afce2b8`.
- PAL run **`f0c868a221731ca4247a6b49f4a1a1f4c715ac407b774d61529f4ce6b47471ab`**, COPY run **`ccba2f29f2c5492ae4d5bc4c503054e8ce3aed05317d3e3c3da81fc01b18fb13`**,
  проект **`qa-recursive004-prod`**. [Прямые принятые MCP-вызовы](api_examples.json).
- Independent checker: CHECKED_INSTANCE для16 PAL/20 COPY train witnesses;
  исходные UTF-8 байты, spans, промежуточные состояния/хеши и каждый primitive step
  проверяются заново, без вызова producer. Scope/operator binding входят в feature identity.

## Измеренный конечный результат

| Задача | Queries | TP | TN | FP | FN | Balanced accuracy |
|---|---:|---:|---:|---:|---:|---:|
| PAL n=6 | 64 | 8 | 56 | 0 | 0 | 100% |
| PAL n=8 | 256 | 16 | 240 | 0 | 0 | 100% |
| COPY n=6 | 64 | 8 | 56 | 0 | 0 | 100% |
| COPY n=8 | 256 | 16 | 240 | 0 | 0 | 100% |

Coverage100%, UNKNOWN0 внутри указанных наборов. No-derive/actual-feature-deny
дают balanced accuracy50% (PAL и COPY на n6: TP0/TN56/FP0/FN8;
на n8 offline: TP0/TN240/FP0/FN16). Accuracy отрицательного majority87.5%/93.75%
обусловлена дисбалансом; она не заменяет confusion matrix. Seed137 и42 выбрали
одинаковые AST. Для каждого seed гипотеза одинакова на queries n6/n8, fit не
читает queries или внешний gold. Переименование S/P в кириллицу/непрозрачные
имена и разворот queries сохраняют предсказания. Реальный COPY-контрпример
SSPPSS отвергает endpoint-only/half-bag surrogate. [Полные метрики](SCORES.json).

Настоящий старый Symbolic V1 PAL run `80457c8536c12fb4e18e302c14542ca4568e9c83cb650def98af3fb49cd92baa`
прочитан через source bridge с проверкой input/result/kernel/AST/train; новый run
сохранён отдельно. Источник связывается по семантике буквальных train tokens и
labels, не по выдуманному тождеству разных изданий. Новый certificate отдельно
связывает новые source records. Несовместимые и чужие ссылки отвергаются.

## Защита и совместимость

Добавлен только необязательный request.promotion_policy; число инструментов83,
все прежние required inputs, output schemas и annotations сохранены. Literal
context route остаётся default. Новая source-ссылка без opt-in получает
SOURCE_CANDIDATE_ROUTE_NOT_ENABLED; повтор старого сохранённого ключа возвращает
точный старый run. Свежий одинаковый payload даёт новый run с тем же result_digest.

Неверные output hash/SPLIT position/UTF-8 span, недостающие witnesses,
RUN_SCRIPT, origin/провенанс, hidden labels, универсальные притязания и JSON
bool/int/float подмены отвергаются даже с пересчитанным внешним digest.
Максимумы:8 tokens,32 AST nodes, depth8,8 recursive steps,256 train witnesses;
за scope возвращается UNKNOWN/score=null. Старый context cap64 сохранён.
Worker CPU5s/wall6s/RAM512MiB и общая квота2 active/16 queued не ослаблены.

## Отрицательный результат и границы

Короткий Dyck: **NO_VERIFIABLE_NEW_OBSERVER**. Для нынешних equality/structural-cut
форм SP и PS имеют одинаковую структуру равенств при разных orientation labels.
Новый допустимый observer отсутствует, а не спрятан за неопределённым контрактом.
По этапам/stop criterion исходного roadmap дальнейшие корпусные C02/C03 **не
запускались**. Общий semantic transfer, новые смыслы текстов и универсальная
грамматика не подтверждены. Family UNDERDETERMINED; CHECKED_INSTANCE не означает
mathematical verified. Native SUTI NOT_EXECUTED, внешняя R3 приёмка PENDING.

## Проверки и production

366 source PASS;366 installed-wheel PASS вне checkout;1066 legacy PASS/20 SKIP;
16 reference PASS. Все19 предоставленных исторических runs сохранены;
FIX-B2 SP/PS/SS64/64 каждый, SP2/4/6/8/10 и partial negatives,
численные base_v1/cj_v1 и старые Symbolic/observer export/replay проверены реально.
PAL/COPY/SP export повторены без сети в отдельном namespace: REPLAY_MATCH,
journal hash-chain PASS. Поставленные numeric75files, frozen core, Symbolic V1,
SP model/checker и workspace.py побайтно сохранены.

До правок и при остановленном HTTP выполнены независимые backup4 SQLite и всех
workspaces. Сохранены26876 initial/35601 cutover files, все исходные исследовательские
строки/объекты/префиксы hash-chain;4/4 SQLite integrity ok. Базы не заменены,
пути/inodes прежние, canonical audit неизменён. Перезапущен только HTTP;
адрес и PID tunnel сохранены. QA grants не создавались, все запуски завершены.
[Целостность](integrity_results.json), [точный установленный состав](release_manifest.json).

Runtime source commit `8e622f584e3d5fda3c685ed1bb0f54bc0eeebca7`; QA commit `b92e868da696ad66ca3a8bb5a175e4f37834d58a`.
Wheel SHA256 `c2221fbfb9914815088857b23f1440149ab3da0aa85bc49d4d154d83417b6c0e`.
Runtime manifest SHA256 `c4e5cd04b2cf688e08cedeecc260576b8277bc020de6b29d83b5d3c1a1466ea3`.
GitHub Actions отдельно: account billing lock препятствует старту jobs; локальные
PASS не объявляются GitHub CI PASS. Публикуется developer-preview prerelease,
не окончательный научный/семантический релиз.
