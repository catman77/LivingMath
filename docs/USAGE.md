# Использование и MCP-запросы

## Первое знакомство

После подключения вызовите `bridge_system_status`, затем `bridge_catalog`.
Текущий объединённый сервер предоставляет 44 инструмента. `mcp_server.py stdio`
остаётся отдельным старым ledger-интерфейсом; он не заменяет объединённый сервер.

Примеры arguments для инструментов:

```json
{"source_id":"P1-001"}
```

Для `bridge_validate_records` это проверка исходной пары по реальной схеме SUTI.
Она показывает потерю различий при проекции, не исполняет SUTI.
`bridge_inspect({"source_id":"ALCH006","view":"summary"})` возвращает
сохранённую исследовательскую модель, её область и неизвестные свойства.

## Загрузка исходного текста

Для работающего `1.2.0rc3-observer012` передайте в `research_autonomy_ingest`
arguments из [проверенного запроса с фрагментом «Эха»](examples/research_autonomy_ingest.observer012-public-domain.json).
Этот точный запрос принят действующим MCP 2026-11-02: проект
`BRIDGE_QA_RIGHTS_CONTRACT_20261102`, case `4575`, source snapshot `4573`.
Для пользовательского текста также есть [минимальный USER_SESSION JSON](examples/research_autonomy_ingest.artifact.json).
Это JSON-объект аргументов MCP-инструмента, не HTTP body отдельного REST endpoint.

Сначала прочитайте `bridge_system_status`: выбирайте interpretation, объявленную
установленным сервером. Следующий пример Meaning014 относится к более новому
коду репозитория. В `1.2.0rc3-observer012` используйте `"interpretation":"observer012"`;
`observer013` и `meaning014` в этой установленной версии отсутствуют.
[Отдельный пример Meaning014](examples/research_autonomy_ingest.meaning014.json):

```json
{
  "project": "QA_MEANING014_EXAMPLE",
  "request_key": "color-mass-v1",
  "source": {
    "format": "livingmath-artifact/1",
    "profile": "typed008/1",
    "interpretation": "meaning014",
    "scope": "qa/meaning014",
    "source_name": "Original diagnostic source",
    "edition": "Original diagnostic, version 1",
    "language": "en",
    "rights": {
      "basis": "USER_SESSION",
      "origin": "Original example supplied by the operator for this research session"
    },
    "raw_text": "Observer C records the color of states A and B as red in both. Observer M records their masses as 2 and 3 respectively. Both records refer to the same two samples and the same measurement session.\n"
  }
}
```

Используйте собственное имя проекта и устойчивый request key. Точный повтор
идемпотентен; для нового текста/содержимого нужен новый ключ. Не меняйте исходник,
сохраняя старый ключ. Для модельной ветки включите `serve --with-codex`.
Загрузка запускает существующий автоматический workflow, а не мгновенный ответ LLM.
При отсутствии interpretation действует существующий режим по умолчанию.
Наличие примера в репозитории само по себе не означает поддержку режима
подключённым endpoint.

## Точный объект rights

Обязательные поля `rights` — **`basis` и `origin`**; `attribution` — необязательная
строка с указанием авторства. Полный машиночитаемый контракт:
[rights.schema.json](examples/rights.schema.json). Не заменяйте их объектами
`license`, `public_domain`, `holder` или `permission`.

| Поле | Точный контракт |
|---|---|
| `basis` | Строка, ровно `USER_SESSION` либо `PUBLIC_DOMAIN`, с учётом регистра |
| `origin` | Обязательная строка длиной 1–1000 символов, не объект метаданных |
| `attribution` | Необязательная строка длиной до 1000 символов; по умолчанию `""` |
| Другие поля | Запрещены: `additionalProperties=false` |

Для собственного/предоставленного в сессии текста:

```json
{"basis":"USER_SESSION","origin":"Кто предоставил текст и в каком контексте"}
```

Для текста общественного достояния:

```json
{"basis":"PUBLIC_DOMAIN","origin":"Автор, произведение, издание/источник и основание public domain"}
```

Указывайте действительные метаданные и основание. Эта декларация не является
автоматическим определением прав сервером. В `source` нужны непустые `scope`,
`source_name`, `edition`, `language` и `raw_text`, как в полном примере.

### Если клиент пишет `source is not valid under any of the given schemas`

Это общая ошибка проверки объединённого типа `source`; она сама по себе не
указывает на `rights`. Сверьте исходный JSON со следующими причинами:

| Что проверить | Требуемое исправление |
|---|---|
| `rights.basis="public_domain"` либо `"PUBLIC-DOMAIN"` | Использовать ровно `"PUBLIC_DOMAIN"` |
| Нет `rights.origin`, передан `null` или объект | Передать непустую строку с происхождением текста |
| Переданы `rights.license`, `url`, `holder` и т. п. | Оставить только поля из схемы; описание источника можно записать в `origin` |
| Нет `source_name`, `edition`, `language` либо `rights` при `raw_text` | Передать все четыре поля; иначе `RAW_SOURCE_METADATA_AND_RIGHTS_REQUIRED` |
| `interpretation="meaning014"` или `"observer013"` на observer012 | Использовать `"observer012"` |
| Одновременно заданы `raw_text` и `snapshot` | Передать один вариант источника |

Поле `language` принимает ровно `"ru"` или `"en"`. Не подменяйте `raw_text`
полями `text`/`content`. Для первого запроса возьмите готовый JSON целиком,
затем меняйте текст, метаданные и request key согласованно.

## Получение результата

Ответ ingest содержит `case_ids`; используйте возвращённый ID:

```json
{"project":"QA_MEANING014_EXAMPLE","case_id":123}
```

Это arguments для `research_autonomy_status`; `123` — пример, замените реальным
ID. Для `research_autonomy_history` добавьте `"view":"report"`, для полной
истории — `"view":"export"`. Экспорт может требовать постраничного чтения;
следуйте возвращённым указателям, чтобы получить все фрагменты.

### Машиночитаемая формальная структура observer012

Экспорт уже реализован. Для проверенного запроса:

```json
{
  "project": "BRIDGE_QA_RIGHTS_CONTRACT_20261102",
  "case_id": 4575,
  "view": "export",
  "after_record_id": 0,
  "byte_offset": 0,
  "limit": 20,
  "max_bytes": 128000
}
```

Это arguments для `research_autonomy_history`. Для другого проекта используйте
его собственный case ID. В ответе находятся `fragments`, а не готовый объект
графа. Пока `more=true`, передавайте возвращённые `next_after_record_id` как
`after_record_id` и `next_byte_offset` как `byte_offset`. Группируйте фрагменты
по `record_id`, соединяйте `json_ascii` по `byte_offset` без пропусков,
затем разбирайте JSON записи и JSON-строку её `payload_json`.
Сохраняйте точность целых чисел: `created_ns` превышает диапазон точных целых
JavaScript `Number`. Для проверки `entry_hash` разбирайте исходный `json_ascii`
через Python `json` или другой парсер с точными 64-битными целыми; округление
при повторной сериализации повреждает клиентскую копию записи.

В `artifact_checkpoint` исходный разбор находится в
`payload.result.source_proposals.readings`: `states`, `relations`, `observers`,
`initial_state_ids` и `unknowns`. Там же сохранены `source_critic`,
`source_alignment`, `source_packet` с адресованными цитатами и `source_coverage_losses`.
В `slices[].premises` находятся формализованные предпосылки с `source_refs`.

В `artifact_result.payload` сохранены `model.spec.reaction_network`,
`model.guards`, `model.initial_states`, `model.assumptions`, `model.losses`,
исходные `premises`, `binding`, `source_context` и независимый `check.analysis`.
`model.observer` зависит от вида построенной модели: у source/meta-модели здесь
могут быть `states`, `source_annotations`, `source_graph` и `observers`, у
`SIGNED_RESPONSE` — собственная схема наблюдения. Переходы конечной модели
и их проверки не подменяют исходные текстовые отношения. Неподдержанные части
ищите также в checkpoint/plan и шагах workflow. Доступность готовой модели
проверяйте после завершения case.

`entry_hash` и исходные координаты сохраняют происхождение записей. Для
`META_ONLY` target-модель может быть `NOT_APPLICABLE`: это не следует заменять
выдуманными динамическими переходами. Новый DSL и операторы SDT для чтения
существующего экспорта не требуются.

Meaning014 сохраняет полную исходную A0 до критики, затем B/B+ и экспериментальный
блок C, цитаты, предпосылки и потери. Исправление не переписывает прежнюю историю.

## Как читать статусы

| Статус/поле | Значение |
|---|---|
| `COMPLETED` | Workflow окончен; результат может быть ограниченным или отрицательным |
| `COST_BOUND` | Исчерпан реальный лимит; отсутствующий ответ не синтезирован |
| `UNKNOWN`, `META_ONLY` | Сохранена неизвестность или полезная исходная модель без достаточного target-обоснования |
| `ENTAILED_UNDER_ASSUMPTIONS` | Следствие заявленной конечной модели и предпосылок |
| `CONFLICTING_REPORTS` | Обнаружено противоречие представленных сообщений, не автоматически ложность мира |
| `source_verified=false` | Смысл исходника независимо не удостоверен |

Система не переводит модельный результат в `verified` и не выдаёт физический
execution grant. Исследовательские предложения, аудит, активация ограниченного
эксперимента и завершение остаются раздельными. Операторские approvals/reviews
выполняются независимо через CLI, не через самоподтверждение модели.
