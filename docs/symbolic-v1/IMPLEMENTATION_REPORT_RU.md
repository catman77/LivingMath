# IMPLEMENTATION_REPORT_RU — Symbolic V1

## Установленная версия

Работа P0/P1 выполнена; production **v0.4.0-developer-preview**, deployment `symbolic-v1-20261105T055049Z`. Прежний адрес: `https://fares-september-rebel-board.trycloudflare.com/mcp`. Реальный HTTPS/OAuth клиент обнаруживает **75 инструментов**. Все72 прежних input/output schemas и annotations совпадают с каталогом до обновления.

Архив пользователя сохранён без изменений: [LIVINGMATH_SYMBOLIC_V1_TZ_PROMPT_20261105.zip](../LIVINGMATH_SYMBOLIC_V1_TZ_PROMPT_20261105.zip), SHA256 `efdd4bb9c1422a09fb1070f2326fed9e6f551f5579b1ce5685a02b5cb816b2bd`;9 файлов внутреннего manifest проверены. [План исполнения](../superpowers/plans/2026-11-05-symbolic-v1.md), [инвентаризация](INVENTORY.json).

## Реализация

Добавлен пакет `src/lm_suti_assurance/symbolic/`. Source сохраняется целиком с UTF-8 hash, точными spans, исходными границами, declared hierarchy/layout и NFC-картой при явном выборе. SymbolicState хранит полные immutable tuple atoms; отдельный content-addressed DAG сохраняет родителей, операции, аргументы, события редукции и хеш результата. Отмена клиентского ожидания не отменяет принятого вычисления; restart добавляет INTERRUPTED, не переписывая старую цепочку.

Реализованы CONCAT/SPLIT, RENAME с явной локальной/глобальной областью, SUBSTITUTE без обещания эквивалентности, REVERSE, SP_INV, детерминированный leftmost REDUCE_SP и генеративный INSERT_CANCEL_PAIR. CONCAT хранит обоих родителей; границы компонентов воспроизводятся по их полным словам и исходным boundary markers. OBSERVE не изменяет state. Четыре отношения — literal, alpha, SP-normal-form и конечная observer-indistinguishability — имеют разные свидетельства.

CAD выдаёт токены/границы, α-pattern, направленное соседство, ограниченные fragment contexts, композиционный порядок, S/P q/normal form/cancellation log/prefix profile и реально переданную иерархию. Новизна — множества хешей структурных свидетелей с Pareto-включением, не scalar semantic score. Локальные кандидаты образуются операциями, а не перечислением всех слов. Используется **настоящий поставленный ReversibleUDAV**; numerical White Star и все75 supplied files побайтно прежние.

Для grammar из train извлекается конечная библиотека отношений равенства/лагов, счётчиков и префиксов; пороги и bounded decision tree обучаются на train, с support/counterexamples и ограничением15 узлов/правил. Это явно ограниченный класс гипотез, а не заранее встроенный parser конкретного скрытого языка. Неполный train предъявляет две разные согласованные модели и distinguishing word. Kernel/selection/scoring не вызывают LLM.

Добавлены `white_star_symbolic_explore`, `white_star_symbolic_inspect`, `white_star_symbolic_replay`; отдельные закрытые схемы опубликованы в `bridge_system_status.symbolic_v1`. Общая project/idempotency/journal/blob инфраструктура прежняя; новая SQLite не создавалась. Новый режим использует два отдельных изолированных supervisor и свежий fork для каждого job с5 CPU/6 wall секунд,512 MiB и bounded queue/result. Старые numerical supervisors и их профили не заменялись.

## Что выполнено фактически

| Проверка | Результат |
|---|---|
| Предоставленный standalone fixture oracle |6024 точных assertions PASS|
| Полный текущий pytest |252 PASS|
| Те же тесты из установленного wheel, вне checkout/import path |252 PASS|
| Legacy pytest из live_math_mcp_prod |1066 PASS,20 SKIP,0 FAIL|
| Реальный staging HTTP/OAuth/MCP |138 PASS|
| Действующий публичный HTTPS/OAuth/MCP |138 PASS|
| Data-only replay в `unshare -Urn`, без сети |REPLAY_MATCH|
| Numerical bundle, созданный до обновления |PASS,1 run действительно пересчитан|
| Исторические White Star source/application и frozen core |без изменений|

Property/metamorphic:30 seed×40 произвольных S/P-слов длиной0–40, включая ε; split/concat, q, идемпотентная редукция, обратная инверсия, обе вставки, rename, reverse и независимый rightmost-reduction oracle. Отдельно проверены границы, cross-record alpha, NFC, literal-token spans, typed negatives, request conflicts, project isolation, cancellation/recovery, ресурсный halt, крупные записи, пагинация и tamper rejection. Состояния одинакового слова и разных историй проверены с `history_identity=word|provenance`.

Непройденные первоначальные запуски сохранены и объяснены в [RCA](RCA_RU.md); проверки и квоты не ослаблялись. Hosted CI в этой задаче **NOT_RUN**; локальные проверки PASS.

## Конечный S/P-срез и реальный MCP

Проект `qa-symbolic-v1-prod`, `run_id=9b3ca97f6a977968df20444fc3d960931f9a3150b6b9c94ea9d3b4789437550b`. Точный запрос — [исходный валидный fixture](../LIVINGMATH_SYMBOLIC_V1/fixtures/mcp_request_example.json),256 шагов×4 кандидата. Получен COMPLETED,477 immutable nodes/observations,207 α-класса,18 точных сравнений. SSPP/SPSP/PPSS/PSPS различны буквально и имеют общий q=0; SP-свидетельства не называются literal/semantic equality. ABBA/BAAB совпадают в изолированном α-классе; AB|AB и AB|CD различаются глобально и совпадают в объявленном локальном quotient.

Structural result digest: `c25f92a0628f2321742b4dcdd8479a3cbff389c9b8f15b1cbc1494d92a5fa341`. Он одинаков на staging/production и при offline recomputation. Operations/kernel binding: `404d9d2612633ee1f673dfdfeaa22dc8365ec59efb3902e70470497c69093cc7`. Private bundle SHA: `e4e51523398d0992c9d960d003681c4b3ca7ee6cf62753ee4e4d0294cfc47811`.

Через MCP:

```json
{"project":"qa-symbolic-v1-prod","run_id":"9b3ca97f6a977968df20444fc3d960931f9a3150b6b9c94ea9d3b4789437550b","view":"claims"}
```

Передайте этот объект в white_star_symbolic_inspect; замените view на operations/observations/history/grammar/evaluation/report/export. Сохранённый ZIP — data-only, его код не исполняется. [Точная инструкция и полный цикл](QUICKSTART_RU.md).

## Слепые грамматики

Заранее зафиксированы20 seed,128 train/64 validation/128 sealed test на seed, отдельные диапазоны длин и opaque atom IDs. Test не передаётся fit. Все480 моделей заморожены до раскрытия labels; threshold0.5, общий upper budget256 train samples/64 features/15 rules/16 thresholds, одинаковые данные. Это общие верхние квоты, а не одинаковое фактическое CPU-время. Измеренные CPU/wall/shared RSS и длина сериализованной модели сохранены отдельно.

Train/test длины не пересекаются: G1 4–12/20–32, G2 6–12/20–32, G3 6–14/22–32. Положительные/отрицательные пары имеют одинаковые длину и token counts. У G1 test использует полностью новые bijective labels; сильный simple_context baseline тоже получает α-нормализацию. Повторы положительных периодических слов отражены train_unique_words. Validation используется для отчёта, не настройки на test. Два полных прогона дали побайтно одинаковые60 frozen model sets, данные и предсказания.

| Семейство | Structural BA | Лучший простой baseline | Прирост / paired95% bootstrap CI |
|---|---:|---:|---|
| G1 periodic |1.0000|0.9996 alpha-context|+0.0004 / [0.0000,0.0012]: NO_EVIDENCE_OF_GAIN|
| G2 matching endpoints |1.0000|0.9172 alpha-context|+0.0828 / [0.0684,0.0984]|
| G3 balanced prefixes |1.0000|0.8965 bigram|+0.1035 / [0.0914,0.1168]|

[Полная таблица всех baseline](RESULTS_TABLE.md), [machine results](RESULTS.json). В поставке есть7680 test predictions на каждый метод, FPR/logloss, next-token NLL, разброс по seed,3-seed sample-efficiency с16/32/64/128 train и все frozen trees с train witnesses. NLL structural — явно определённая нормировка membership(prefix+token), а не generative semantic likelihood. G4 возвращает UNDERDETERMINED с двумя train-compatible finite grammars и различающим словом.

Выигрыш подтверждён **в двух конечных synthetic задачах для данной библиотеки структурных наблюдений**. Это не доказательство автоматического открытия произвольной грамматики или смысла.

## Абляции и подлинные тексты

A q-only теряет четыре нулевые истории и даёт BA0.5 на всех трёх synthetic families. B adjacency-only и D without_alpha на дальних связях дают≈0.518 против1.0. C local/global различаются на AB|AB/AB|CD. F lossy2D(length,adjacency) слабее на G2/G3; отдельно через настоящее старое numerical ядро получена одинаковая trace для разных четырёхсловных корпусов с одинаковым position/length encoding. У старого numerical kernel нет membership-интерфейса, поэтому его trace не выдаётся за классификационный baseline. G одинаковое конечное ε сохраняет разные operation node IDs.

**E — отрицательный контроль:** Pareto и random-local на20 seed при32 шагах×4 кандидата имеют одинаковые траектории выбора, средние nodes76.8 и witnesses342.6. Преимущество исследовательского поиска над random не подтверждено. Обнаруженный предсказательный выигрыш относится к структурным отношениям/обучению, не к превосходству selector.

После G1–G4 выполнены короткие структурные опыты на восьми исходных французских строках [Mallarmé, Vers et Prose1893](https://fr.wikisource.org/w/index.php?title=Vers_et_Prose_(Mallarm%C3%A9)/Brise_marine&oldid=14106920) и [Nostradamus, редакция1867](https://fr.wikisource.org/w/index.php?title=Page:Nostradamus_-_Les_oracles_-1867.djvu/30&oldid=13566813). Оригинальная орфография и варианты сохранены; footnote markers отделены, inline drop cap соединён как Estant. Выбраны первые8 строк, source hashes/spans сохранены; page geometry отсутствует, layout=UNAVAILABLE. Train строки1–4, heldout5–8. Без размеченной истинной grammar membership accuracy не заявляется: оба результата UNDERDETERMINED; реальные continuation NLL и структурные артефакты сохранены. LLM-интерпретация не выполнялась.

## Production и сохранность

Online backup и отдельный quiescent backup четырёх SQLite перед переключением. Canonical2058 events, typed2072 events; все прежние research/typed/DAV строки сравнены полностью, пути и inode всех четырёх БД прежние. OAuth меняет только штатные сессии входа, исходные backup сохранены privately. Все1105 файлов на cutover остались побайтно прежними,17 journal hash-chains валидны. Canonical audit:4817 записей, head `c9c0048be5cc2e782cb2f2377da524e5ad04303d86b65792ef1d503b8c1c3d50` — без изменений. Активных/незавершённых QA runs и execution grants нет.

Перезапущен только HTTP, прежний tunnel PID1801300 и origin сохранены. Rollback — возврат старого drop-in/config и restart HTTP, без восстановления БД поверх новых записей. Старый слой сохранён. R3 external replays=PENDING, native SUTI=NOT_EXECUTED; mathematical verified не присваивается.

## Артефакты и команды

[RESULTS.json](RESULTS.json), [RCA_RU.md](RCA_RU.md), [INTEGRITY.json](INTEGRITY.json), [INVENTORY.json](INVENTORY.json), [REQUEST_SCHEMA.json](REQUEST_SCHEMA.json), [QUICKSTART_RU.md](QUICKSTART_RU.md). Полная поставка: `exports/LIVINGMATH_SYMBOLIC_V1_DELIVERY_20261105.zip`: frozen datasets/models/predictions, A–G controls, источник/хеши, wheel, tests, full MCP requests/responses/wire, data-only run ZIP и manifest. OAuth tokens, passwords, private config и SQLite backup в поставку не включены.

```bash
python docs/LIVINGMATH_SYMBOLIC_V1/checks/check_fixtures.py
python -m pytest -q tests
(cd live_math_mcp_prod && python -m pytest -q .)
python tools/symbolic_v1_experiments.py --output /tmp/symbolic-experiments-new
```

Для live MCP acceptance используйте tools/symbolic_v1_mcp_qa.py с --origin, --endpoint, --baseline, --output и новым --tag; скрипт регистрирует только собственные QA-проекты и пишет приватный OAuth token отдельно. Полный список изменённых файлов — FILES_CHANGED.json.
