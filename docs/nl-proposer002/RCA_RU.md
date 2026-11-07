# RCA LM-NL-PROPOSER-002

Подтверждено: реальные source-bound provider предложения, типизация, сохранённые
конкурирующие AST, проверка происхождения и конечные контрмодели. Не установлено:
семантическая точность, общий NL→FOL и добавочная польза White Star.

Исправленные дефекты разработки (исходные FAIL-трассы сохранены в delivery):

- Runtime packaging исключил native/build: ENGINE_UNAVAILABLE. В финальный runtime
  перенесён прежний собранный .so с исходным SHA; математика не менялась.
- Клиентский fixture передавал лишнее protocol.k. Исправлен сам клиент на
  candidates_per_step; серверная валидация не ослаблялась.
- Трассированный NL reserve повторно брал flock внутри transaction: реальный504.
  Immutable input/trace resolution вынесен из критической секции; реальная
  same-project symbolic регрессия ограничена трёхсекундным ожиданием.
- Replay не связывал полностью request/policy/trace. Общий build_request,
  source reconstruction, SHA raw response, ответы и trace digest теперь
  проверяются до decoder. Все воспроизведённые подмены отклонены.
- Concurrent admission пропускал12 задач при заявленных4 и блокировал retries.
  Admission сериализован; capacity проверяется только для нового старта, после
  idempotency lookup.4/12 admitted; остальные отклонены без новых starts.
- Первый formal QA использовал прежнюю83-tool baseline до DYCK006. Взята
  фактическая baseline непосредственно перед Formal001. Опция allow-nl-api
  удаляет только два новых имени из legacy сравнения; прежние assertions сохранены.
- В первом draft примере source_ref ошибочно был digest(data), а не blob ref.
  Исправлен по фактическому formal_store, полная опубликованная последовательность
  прошла настоящий public HTTPS/OAuth, replay и идемпотентный повтор.
- Первый public QA начал OAuth до завершения восьмисекундного HTTP startup.
  После готовности listener повторён тот же приёмочный прогон; исходный отказ
  сохранён. Operator helper теперь ждёт готовность socket вместо fixed sleep.
- Транспортный ReadError не отменяет принятую задачу. Runner сохраняет исходную
  ошибку и переподключается с теми же byte payload/request keys; новый опыт не
  создаётся. Число новых модельных вызовов учитывается по receipts.

Численные кадры допускают только явно реализованный typed move. Если нужных
source anchors/перестановки нет, UNDECODABLE_FRAME сохраняется. Это не основание
менять ядро или подгонять лексические правила под тест. Переход источника к FOL
всё ещё содержит LLM-предпосылки. Type/provenance/finite truth не устанавливают
авторский смысл. Два независимых человеческих оценщика отсутствуют:
EXTERNAL_ADJUDICATION_NOT_EXECUTED, PARTIAL, semantic generalization NOT_EVALUATED.

Независимый synthetic holder работает в отдельном контексте, gold запечатан до
candidate freeze; OS owner общий, поэтому это процедурная, не криптографическая
изоляция. Model revision/seed/temperature UNKNOWN; фактические расходы различны
при одинаковых nominal budgets. WHITE_STAR_INCREMENTAL_BENEFIT_NOT_ESTABLISHED.

Финальные контрольные показатели: source-only A1, numeric B6, permuted C6,
alternate D7 совпадений с неэталонными synthetic finite vectors. Поэтому
увеличение числа typed/trace-linked кандидатов нельзя объявлять улучшением качества.

Дополнительная проверка control fixtures: два blind случая с family adversarial_verb
на самом деле не образуют E1 alpha-пару. Они сохранены без изменений как негативные
контроли несовпадения текста и сигнатуры (abstain во всех плечах). Предписанная
E1 Read/Lost пара отдельно проверена на исходных dev и свежих публичных MCP
вызовах A/B/C/D. Метрики frozen blind набора не заменялись и не пересчитывались
для улучшения результата.
