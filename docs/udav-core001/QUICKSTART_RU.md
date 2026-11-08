# UDAV Core: точный MCP-контракт

Подключитесь к прежнему `/mcp` без Authorization. После обновления списка
должно быть98 методов. Если ChatGPT показывает94, обновите подключение или
переподключите приложение по тому же URL. Проект создаётся явно:

```json
{"name":"assurance_project_new","arguments":{"project":"my-udav-test","request_key":"init"}}
```

В [MCP_EXAMPLES.json](MCP_EXAMPLES.json) находятся полные `tools/call` params,
без многоточий: создание проекта, symbolic, numeric, inspect и replay.
Чтобы получить новый прогон, замените project на созданный проект и задайте
новый request_key. Для inspect/replay используйте run_id из своего ответа.
Исходник и rights приведены полностью, SHA соответствует UTF-8 байтам текста.

Символьный запрос использует `frontier_argument_coverage_v1`, только descriptive
задачу и реальные старые операторы. `new_raw_observation` считает raw witness,
`new_structural_class` — заявленный quotient; без structural observer последнее
равно null и статус STRUCTURAL_NOVELTY_UNDEFINED. MAX_* и CPU_BOUND сохраняют
частичный DAG и не доказывают исчерпания.

Для численного пути требуется явный `selection_policy="cat_distinction_tiebreak_v1"`.
Первичный graph novelty остаётся первым критерием. Только однозначная canonical
source-ID пара может быть новым точным различием; все альтернативные aliases
доступны в diagnostics. Переданные координаты и отношения остаются декларациями.

`udav_inspect(view="bundle",offset=0,limit=48)` возвращает base64-страницу.
Последовательно запрашивайте next_offset, соедините **декодированные байты** и
проверьте sha256 полного JSON. Данные bundle не содержат исполняемого receipt.
В поставке готовы symbolic-bundle.json и numeric-bundle.json с полными трассами.

```bash
python tools/udav001_replay.py symbolic-bundle.json --expected-sha256 <SHA_из_MANIFEST>
```

Офлайн требуется установленный0.4.12 wheel, Python3.13/Linux и подготовленное
native ядро. Код берётся из установленного пакета; LLM и сеть не используются.
Привязка к binding строгая. Обычные конечные прогоны воспроизводятся точно;
CPU-bound отсечка может произойти в другой позиции, тогда replay честно
отклоняется с REPLAY_MISMATCH. Статус не подменяется успехом.
