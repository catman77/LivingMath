# NLProposalBridge/1: использование

Адаптер добавляет `formal_nl_propose` и `formal_nl_inspect` в существующий
HTTPS/OAuth MCP. Старые восемь `formal_*` инструментов и их схемы сохранены.
`formal_interpret` принимает декларации происхождения: даже `kind=white_star`
не проверяет run/frame. Новый proposer разрешает ссылки только в том же проекте.

1. Создайте проект через `assurance_project_new`.
2. Сохраните TextSource через `formal_store(kind="source")`. Здесь `rights` —
   **не объект**, а непустая строка; это контракт Formal Bridge, отдельный от
   `livingmath-artifact/1`. Весь следующий пример — валидное `data`:

```json
{"text_utf8":"Каждый исследователь проверил одну гипотезу.","sha256":"1bfb913518481ba0899018a463ab11fecb272ae1703d9139dc1f0ba27fc07389","rights":"synthetic-original","spans":[],"context_refs":[]}
```

3. Вызовите `formal_nl_propose` (единственный placeholder ниже — фактический
   `stored_object_ref` из ответа шага 2):

```json
{
  "project":"qa_nl002_demo",
  "request_key":"proposal-1",
  "source_ref":"STORED_OBJECT_REF",
  "target_signature":{"sorts":["researcher","hypothesis"],"predicates":{"Checked":["researcher","hypothesis"]}},
  "provider":{"kind":"owner_hosted"},
  "policy":{"mode":"source_only","max_candidates":4,"max_model_calls":1,"max_tokens":60000,"max_cpu_ms":4000,"max_frames":4,"seed":2211},
  "requirements":{"exact_source_bindings":true,"typed_ast":true,"independent_checker":true,"no_gold_labels":true}
}
```

Ответ `RUNNING` — принятая задача, не полученная формула. Опросите
`formal_nl_inspect(project,run_ref,view="summary")`, затем `view="result"`.
Крупные ответы используют `encoding="base64"`, byte `offset`, `next_offset`,
полный SHA256; соберите все страницы. `view="bundle"` возвращает приватные
исходники и receipt. `view="replay"` проверяет замороженный ответ без LLM/сети.
Не публикуйте пользовательские источники и rights без отдельного разрешения.

Для `white_star_structural` передайте `structural_run_refs` с
`engine="symbolic_v1"`, настоящим `run_id` и опциональными `node_refs`.
Для `white_star_numeric` используйте `engine="white_star"`, опциональные
`frame_ids`. Run обязан завершиться, иметь тот же точный source и принадлежать
проекту. `input_sha256` и `snapshot_sha256` — дополнительные проверяемые guards.
Режим `matched_ablation` — явно маркированный переставленный контроль; его
изменения не получают `TRACE_LINK_CHECKED`. До шести `items` делят один вызов
модели, с одинаковой политикой и отдельными source/signature/trace для каждого.

`TYPED`, `TRACE_LINK_CHECKED` и `FINITE_COUNTERMODEL` описывают разные проверки.
Смысл остаётся `PROPOSED`; математического `verified` и execution grant нет.
`UNDECODABLE_FRAME`, `NO_WELL_TYPED_DECODING` и `PROVIDER_UNAVAILABLE` —
сохраняемые результаты, а не повод подставить шаблонную формулу.

Для полностью offline replay скачанного QA-пакета (без HTTP):

```bash
python tools/nl002_replay.py --candidates CANDIDATES_FROZEN.json --output replay.json
```

Опционально `--snapshots STRUCTURAL_RUN_SNAPSHOTS.json` повторяет также
настоящие численные/символьные вычисления с точным сравнением result SHA256;
для него предварительно установите math-зависимости и подготовьте native.
Обычный replay декодера не загружает модель и запрещает открытие сокетов.

Два полных JSON-запроса без placeholders:
[`formal_store`](fixtures/valid_source_store.json),
[`formal_nl_propose`](fixtures/valid_nl_propose.json).
Перед ними создайте `qa_nl002_demo`; вызывайте по порядку. Content-addressed
`source_ref` в примере — настоящий blob ref из `formal_store`, соответствующий
**ровно** опубликованному `data`. Это не SHA текста и не digest самого `data`;
при любом изменении source используйте ref из настоящего ответа `formal_store`.
[Полные схемы новых инструментов](NL_PROPOSER_SCHEMAS.json).
