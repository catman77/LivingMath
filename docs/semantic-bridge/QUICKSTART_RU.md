# Semantic Bridge — установка и проверка

Полный численный набор проверен на Linux/Python 3.13; assurance/Semantic CLI
также проверяется отдельно на 3.14. Установите текущий пакет из корня репозитория:

```bash
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install '.[white-star,mcp,test]'
lm-suti doctor --smoke
lm-suti white-star prepare
python -m pytest -q
```

Для установки текущего пакета без сети сначала соберите wheelhouse на машине
с тем же Python/платформой и доступом к зависимостям:

```bash
python -m pip wheel '.[white-star,mcp]' -w wheelhouse
```

Скопируйте wheelhouse на целевую машину:

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install --no-index --find-links wheelhouse 'lm-suti-assurance[white-star,mcp]==0.4.5.dev0'
```

Сохранённые semantic bundles проверяйте через `lm-suti replay BUNDLE.zip --offline`
с `--engine direct`, затем `--engine compiled`: оба должны вернуть одинаковый
logical_digest. Replay не вызывает модель, OAuth или сеть. Приватные bundles с
текстами/prompts не входят в публичный GitHub checkout.

## Проверка через ChatGPT / MCP

Адрес production сохранён: `https://fares-september-rebel-board.trycloudflare.com/mcp`.
Основная версия — **v0.4.5-developer-preview**, 83 инструмента;
`semantic_contract.release` сохраняет версию semantic-контракта v0.2.
Обновите подключение, если клиент использует старый `tools/list`.
[Полный MCP-интерфейс](../MCP_INTERFACE.md). Это временный Cloudflare tunnel:
его перезапуск может изменить URL.

Начните с read-only вызовов:

```json
{"name":"semantic_contract","arguments":{}}
```

```json
{"name":"semantic_report","arguments":{"project":"semantic-poetry-001"}}
```

Досье содержит три источника, шесть HOSTED_MODEL-прочтений, три revision edges, два отдельно обозначенных FIXTURE-контроля и все отрицательные предложения. Одна контрольная разметка отозвана при QA; её история и свидетели сохранены. Интерпретации не получают verified.

Экспорт и replay сохранённого пакета:

```json
{"name":"semantic_export","arguments":{"project":"semantic-poetry-001","audience":"private","include_source_bytes":true}}
```

Передайте возвращённый `bundle_ref` (SHA-256) в `semantic_replay` вместе с тем же project и `engine="direct"`, затем `engine="compiled"`. Не отправляйте большой ZIP обратно в POST: SHA-ref сохраняет прежний лимит HTTP. При `include_source_bytes=false` ожидается `MISSING_SOURCE_DEPENDENCY`, а не PASS.

## Новый текст и две версии

1. Создайте отдельный проект `assurance_project_new`. Через `assurance_contract` получите точную SourceSnapshot-схему и publication-policy. Зарегистрируйте разрешённый текст через `assurance_source_add` с JSON-строками `snapshot_json` и `publication_policy_json`.
2. Вызовите `semantic_source` с полученным source_ref. `metadata_json` — JSON-строка с ровно пятью полями: `author`, `title`, `edition`, `editorial_source_url`, `edition_status` (`DECLARED_EDITION`, `UNCERTAIN_EDITION` или подтверждённый `PUBLIC_TRANSCRIPTION_LINE_MATCH`). Нужны actor, reason и request_key. Это подтверждение ограниченного source/hypothesis scope, не истинности трактовки.
3. Передайте возвращённый edition_ref в `semantic_draft(project, edition_ref, request_key)`. Оставьте `proposal_json` отсутствующим: сервер использует существующий owner Codex login. При недоступности модели получаете явный MODEL_UNAVAILABLE. Для ручного режима передайте proposal_json по схеме `semantic_contract.schemas.proposal`; он будет MANUAL.
4. Вызовите `semantic_revise(project, frame_ref, challenge, request_key)` с независимым диагностическим вопросом. Первая версия остаётся неизменной; вторая получает parent и RevisionEdge.
5. `semantic_compare` принимает projection_json. Например: `{"fields":["/image_set"],"declared_Q":[{"id":"order","kind":"STRUCTURAL_FIELD","field":"/image_order","question":"Порядок заявленных образов"}],"complete":true,"expectation":"REPORT"}`. Область проверки — пара указанных frames, включая все её пары; это не универсальная семантическая эквивалентность.

CLI-эквиваленты после регистрации source и edition:

```bash
lm-suti semantic source --project poetry --source-ref SOURCE_REF --metadata edition.json --actor owner --reason 'Точные байты, только источниковые проверки и гипотезы' --request-key edition-1
lm-suti semantic draft --project poetry --source-ref EDITION_REF --private ./private-receipts --request-key initial-1
lm-suti semantic revise --project poetry --frame-ref FRAME_REF --challenge 'Какую альтернативу не исключает источник?' --private ./private-receipts --request-key revise-1
lm-suti semantic report --project poetry --format json --output dossier.json
lm-suti export --project poetry --audience private --output poetry.zip
lm-suti replay poetry.zip --offline --engine direct
lm-suti replay poetry.zip --offline --engine compiled
```

SOURCE_REF / EDITION_REF / FRAME_REF заменяются реальными адресами из предыдущих ответов. Все мутации требуют request_key: одинаковый повтор возвращает прежнюю запись, изменение содержания с тем же ключом даёт REQUEST_KEY_CONFLICT. Новая редакция или новые права требуют новой регистрации и scope review. Сырые предложения, ошибки и withdraw сохраняются append-only. Hosted backend: установленный `codex`, существующий ChatGPT login, модель `gpt-6.1-sol`, без API-ключа; каталог receipts должен быть приватным (0700).

`SOURCE_ATTESTED` здесь относится к точным цитатам после byte preflight. `LOSS_DETECTED` — к заявленной разметке и Q. Литературные/физические трактовки остаются UNKNOWN/HOLD; native SUTI не исполняется, R3 двух внешних участников остаётся PENDING.
