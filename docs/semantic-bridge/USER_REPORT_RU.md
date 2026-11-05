# LM–SUTI–SEMANTIC–BRIDGE–001 — результат

**Semantic Bridge реализован и установлен на production после локальной и реальной HTTPS/OAuth приёмки.** Адрес сохранён: https://fares-september-rebel-board.trycloudflare.com/mcp. Версия `v0.2.0-developer-preview`, deployment `semantic001-20261105T015444Z`, manifest `9dfdb88a783b9fa372329da16d0d78345bf10e41cacbd854689fcae79086d519`. R3 двух внешних участников остаётся PENDING.

## Что работает

Точный текст → pinned SourceEdition → недоверенное предложение → независимые UTF-8 anchors → версии SemanticFrame / RevisionEdge → ограниченные assurance checks → сравнение объявленной разметки → приватный экспорт → автономный replay. Использованы существующие Workspace, immutable objects и исходное assurance-ядро. Нового математического DSL или native SUTI runtime нет.

Опубликованы девять semantic_* инструментов, всего64; входные схемы всех прежних55 совпадают с baseline. В ChatGPT обновите подключение приложения для перечитывания каталога инструментов; адрес менять не требуется. Первый вызов: `semantic_contract`, затем `semantic_report(project="semantic-poetry-001")`.

## Шесть реальных модельных прочтений

Один requested model `gpt-6.1-sol`, Codex CLI0.166.0, существующий ChatGPT login без API-ключа. Проведено9 попыток:3 отказа provider schema до генерации и6 содержательных генераций. Quality retries и выбор лучшего ответа отсутствуют. Точный provider revision не раскрыт. Известный subtotal usage: 142729 input / 11010 output tokens; usage3 неудачных попыток и денежная стоимость неизвестны (`null`). Реальные MCP-прогоны переиспользовали именно эти сохранённые ответы через owner pipe; новых генераций в них0.

| Текст | Версия | Временное прочтение | Literal / гипотезы | Frame SHA prefix | Смысловой статус |
|---|---:|---|---|---|---|
| Ночь, улица, фонарь, аптека | 1 | cyclic | 4 / 3 | `19a87f225c34…` | UNKNOWN |
| Ночь, улица, фонарь, аптека | 2 | ambiguous | 4 / 3 | `94b8bd947510…` | UNKNOWN |
| Анчар | 1 | linear | 4 / 3 | `96f74dd60221…` | UNKNOWN |
| Анчар | 2 | linear | 6 / 4 | `836dbf605fa8…` | UNKNOWN |
| Я вас любил: любовь ещё, быть может | 1 | ambiguous | 3 / 3 | `78d7e1183945…` | UNKNOWN |
| Я вас любил: любовь ещё, быть может | 2 | ambiguous | 4 / 4 | `1ee4d6cb7cf0…` | UNKNOWN |

Для Блока ревизия сохраняет альтернативы, разделяя повтор слов, порядок образов и недоказанное тождество мира: cyclic → ambiguous. Для «Анчара» разведены адресованное насилие, повествовательная причинность и физический механизм; непосредственная причина смерти остаётся гипотезой. Для «Я вас любил» отделены сообщение о чувстве, намерение отступить и фактическое невмешательство; биографическая мотивация не установлена. Полные альтернативы, rationale и source anchors находятся в досье; исходные версии не заменены.

Три текста заморожены до inference. Сверены точные строки пользовательских транскрипций с доступными публичными страницами; оригинальные bytes, ё, тире и LF не исправлялись. PUBLIC_TRANSCRIPTION_LINE_MATCH не является независимой сертификацией издания или юридических прав. Модельные оговорки «редакция не сверена» сохранены: генератор не выполнял внешний аудит источников. Raw text SHA отличен от SHA JSON-контейнера SourceSnapshot. Публикация корпуса ограничена private.

## Loss и границы вывода

Два отдельно помеченных FIXTURE-контроля Блока имеют одинаковый image_set, но различаются по image_order и canal_details. Проекция на image_set даёт LOSS_DETECTED с двумя конкретными q(u)≠q(v) при P(u)=P(v). Ложное заявление PRESERVED отклонено. Полная проекция сохраняет все вопросы объявленного Q на конечном домене из двух records (4 упорядоченные пары); пустое Q → UNDETERMINED. Вопрос о буквально том же мире → HYPOTHESIZED_SEMANTIC_LOSS, без научной верификации. Контрольные разметки не включены в число6 модельных прочтений. QA append-only отозвал одну контрольную разметку в production; модельные6 остались на месте.

SOURCE_ATTESTED удостоверяет только точные quote-envelope bytes после самостоятельного source-byte preflight. Проза LITERAL, авторское намерение и интерпретационные отношения не становятся доказанными. UNKNOWN/HOLD не равен опровержению; execution_permission=false во всех новых решениях.

## Приёмка и сохранность

| Проверка | Факт |
|---|---|
| Установленный wheel, Python3.13 /3.14 |155 PASS на каждом|
| Старый серверный набор |1066 PASS,20 SKIP,0 FAIL|
| Матрица S01–S11 /I01–I10 /L01–L05 /R01–R10 |36/36 PASS|
| Настоящие MCP HTTPS/OAuth staging /production |25/25 PASS на каждом|
| Self-contained replay direct /compiled |PASS, одинаковый logical_digest; fresh offline install и kernel network namespace|
| Source omission /tamper /false preservation /status escalation |ожидаемые отказы|
| SQLite canonical /typed /DAV исходные строки |все сохранены, полное сравнение со всеми backups|
| Четыре SQLite integrity_check и прежние121 файлов |PASS|
| Основная audit chain |4817, прежний head c9c0048be5cc2e782cb2f2377da524e5ad04303d86b65792ef1d503b8c1c3d50|
| События canonical /typed; obligations canonical |2058 /2072;769 сохранены|
| Frozen verifier /binder; root AGENTS |без изменений|
| Внешний human gate /native SUTI |PENDING /NOT_EXECUTED|

Production обновлён по прямому запросу владельца после QA — это отдельное разрешение rollout поверх исходного no-stealth ограничения архива. До переключения сделаны online и quiescent BackupAPI-копии всех4 SQLite и копии рабочих файлов. HTTP перезапущен, tunnel PID1801300 и URL сохранены. Изменение SQLite-схем не потребовалось; добавлен только новый файловый QA-проект. OAuth-сессии имеют естественную ротацию, их копии сохранены приватно, а токены в поставку не входят.

## Воспроизведение

Распакуйте приватную поставку, установите wheel из wheelhouse и запустите `PYTHON=.venv/bin/python ./replay_offline.sh`. Вызовы и установка описаны в [Quickstart](QUICKSTART_RU.md). Полные MCP request/response и wire JSON-RPC — `mcp/production/`; сырые prompts/outputs — `model-receipts/`. Три исходных provider schema ошибки и ранние QA-отказы не скрыты. Только вспомогательные CLI warnings с приватным путём исключены из экспортируемых receipts с SHA-ссылкой на неизменённый оригинал; модельные входы и ответы сохранены буквально.

Самодостаточный bundle: `demo_poetry_private.zip`; машинные результаты: `ACCEPTANCE_RESULTS.json`, `READING_TABLE.json`, `INTEGRITY_AND_REPLAY.json`, `PRODUCTION_INTEGRITY.json`, `MODEL_ATTEMPTS.jsonl`. Это работающая ограниченная исследовательская инфраструктура, не измерение литературной accuracy и не доказательство превосходства над LLM. R3/final external admission остаются PENDING; отсутствующие внешние свидетельства не синтезированы.
