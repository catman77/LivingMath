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

Передайте в `research_autonomy_ingest` arguments из
[готового Meaning014 JSON](examples/research_autonomy_ingest.meaning014.json).
Это JSON-объект аргументов MCP-инструмента, не HTTP body отдельного REST endpoint.

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
Другие поддерживаемые interpretation: `general011`, `observer012`, `observer013`;
при отсутствии поля действует существующий режим по умолчанию.

## Точный объект rights

Обязательные поля `rights` — **`basis` и `origin`**; `attribution` — необязательная
строка с указанием авторства. Полный машиночитаемый контракт:
[rights.schema.json](examples/rights.schema.json). Не заменяйте их объектами
`license`, `public_domain`, `holder` или `permission`.

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

## Получение результата

Ответ ingest содержит `case_ids`; используйте возвращённый ID:

```json
{"project":"QA_MEANING014_EXAMPLE","case_id":123}
```

Это arguments для `research_autonomy_status`; `123` — пример, замените реальным
ID. Для `research_autonomy_history` добавьте `"view":"report"`, для полной
истории — `"view":"export"`. Экспорт может требовать постраничного чтения;
следуйте возвращённым указателям, чтобы получить все фрагменты.

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
