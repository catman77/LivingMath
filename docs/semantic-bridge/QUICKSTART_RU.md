# Semantic Bridge — установка и проверка

Проверены Linux, Python 3.13 и 3.14. Установите текущий пакет из корня репозитория:

```bash
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install '.[mcp,test]'
lm-suti doctor --smoke
python -m pytest -q
```

В приватной поставке есть `dist/`, wheelhouse для Python 3.13 и `replay_offline.sh`. Для установки без сети:

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install --no-index --find-links wheelhouse lm-suti-assurance==0.2.0.dev0
PYTHON=.venv/bin/python ./replay_offline.sh
```

Оба движка должны вернуть PASS и одинаковый logical_digest. Replay не вызывает модель, OAuth или сеть; исходные версии не регенерируются. Пакет содержит приватно разрешённые тексты и prompts; не публикуйте его автоматически.

## Проверка через ChatGPT / MCP

Адрес production сохранён: `https://fares-september-rebel-board.trycloudflare.com/mcp`. Основная версия — `v0.2.0-developer-preview`, deployment `semantic001-20261105T015444Z`. Если ChatGPT показывает старые 55 инструментов, обновите подключение приложения в настройках, чтобы перечитать `tools/list`; менять адрес не требуется. Это существующий временный Cloudflare tunnel: его перезапуск может изменить URL.

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
