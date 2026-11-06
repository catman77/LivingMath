# DYCK006: ролевые ветвящиеся программы

Установлен **v0.4.8-developer-preview**, deployment `dyck006-20261106T214503Z`.
Адрес сохранён: https://fares-september-rebel-board.trycloudflare.com/mcp. Архив задания сохранён без изменений в docs;
SHA256 `78c9f721a5178cde4808ef542e9d1a4c878c694be8c118f9f975cfb1da2205fd`. На стенде и на публичном HTTPS/OAuth MCP
**10780 проверок PASS на каждом endpoint**, по **1552 фактических tools/call**.
Это включает333 role,41 edge,8547 continuation,943 prior regression и916 generator
проверок. В943 находятся320 явно локальных supplied-AST controls, не MCP discovery.
Все31 прежний A/B gate PASS. Полные запросы/ответы, wire, frozen inputs и
оригинальные неуспешные попытки входят в единый ZIP релиза.

## Что изменено и почему

На настоящем0.4.7 заново получены49 baseline PASS/34 MCP calls,18 исходных runs
пересчитаны с точными result_digest. Equality-only catalog не различает SP и PS
при биекции алфавита: менять бюджет бесполезно. На84 train/256 query исходный
predictor дал TP0,TN242,FP0,FN14, balanced accuracy50%.

Добавлен конечный typed catalog: два направленных ATOM_ROLE,0/1/2 RECURSE,
EPS/NONE и все допустимые перемежения. Binary train даёт40 кандидатов;
роли связываются с атомами только из train. Нет готового Dyck AST, is_dyck,
высотного recognizer, скрытых labels или LLM. Генерация, typing/termination,
full-train compatibility и независимая admission разделены.

На84 train совместимы две программы, обе сохраняются. Structural tie-break
выбирает OPEN; recurse b0; CLOSE; recurse b1 с EPS base.
AST SHA `d7614e8d77a8e3a41cce43109bb406be1c0982bba5005d134162c5e0b7afc4cc`.
Feature `derived_b0bae4245d3417323658`. Это не доказательство уникальности грамматики.
На минимальных SP=True/PS=False данных ориентированные rivals также сохранены.

`role_ast.py` даёт finite interval DP и constructive Word tree с реальными
SPLIT/CONCAT; `role_checker.py` независимо повторяет source parsing, каждое
уравнение/возможное распределение длин, обе children и буквальную реконструкцию.
Отрицательный ответ проверяется полной таблицей, не отсутствием найденного proof.
`features.py` доверяет decision checker, а не scalar producer.

## Конечный heldout результат

| Вариант | TP | TN | FP | FN | UNKNOWN | BA |
|---|---:|---:|---:|---:|---:|---:|
| Исходный0.4.7 |0|242|0|14|0|50%|
| Role, seed137 |14|242|0|0|0|100%|
| Role, seed42 |14|242|0|0|0|100%|
| Unicode binding transfer |14|242|0|0|0|100%|
| derive_relations=false |0|242|0|14|0|50%|

Train84: все слова длин2/4/6,8 positive/76 negative. Heldout256: длина8,
14 positive/242 negative. Always-negative accuracy94.53125%, BA50%.
Поставленные dataset refs воспроизведены точно:
train `596fa9621ae7cd197ce0c999a6d03ac406b313ffa351a1107f9807d709f3434e`,
query `e956883b11ac2b73162fb9f55874f2918f7d6aa8d5755dadbe5bcf58e3bb1073`.
Gold прочитан после inference. Оба seed, stage/public models и result_digest
совпадают. Полный результат: [SCORES.json](SCORES.json), [run IDs](RUN_REGISTRY.json).

SSPPSP имеет два **непустых** independently checked child SP/SP.
[Положительный сертификат](TWO_BRANCH_PROOF.json) и
[отрицательный полный DP](NEGATIVE_PROOF.json) содержат источники/spans/шаги.
Rehashed wrong-role/SPLIT/span/source SHA/потеря ветви/NF-only/negative-cell/
ложная область/claim отвергаются. Лимиты дают UNKNOWN без сертифицированного bit.
Проверены реальные parent/derived ablations, Unicode, конфликтный и пустой train,
идемпотентность, project isolation, export и offline REPLAY_MATCH без сети.

## P1: измеренные множества продолжений

На том же84 train, без дополнительных labels, заморожена программа с явным
role_max_tokens12. Все8191 слов длины0…12 оценены сервером в32 bounded batches;
hypothesis_digest одинаков, UNKNOWN0, каждый query имеет independent CHECKED_INSTANCE.
Затем построены **настоящие множества принимаемых суффиксов** для каждого prefix,
а классы сгруппированы по содержимому этих множеств. Высота не используется.

| N | Число измеренных классов |
|---:|---:|
|1|3|
|2|4|
|3|5|
|4|6|
|5|7|
|6|8|

Полные membership matrices, suffix sets и настоящие различающие witnesses:
[CONTINUATION_CLASSES.json](CONTINUATION_CLASSES.json).8191 source/proof SHA и
run IDs — OBSERVATIONS.json в delivery evidence/production-continuations-qa.
Это проверка N≤6; формула N+2 вне этого горизонта не утверждается.
EPS уже поддерживался текущим ingress как tokens=[],text="" с настоящим SHA;
placeholder или новая схема для него не вводились.

## Проверки, интерфейс и эксплуатация

**409 source PASS,409 installed-wheel PASS**,1066 legacy PASS/20 прежних SKIP,
24 supplied reference PASS. Независимый review:22 targeted PASS, открытых findings нет.
[Матрица](acceptance_matrix.json), [схемы и точные вызовы](QUICKSTART_RU.md).
83 инструмента сохранены; additive mode/role bounds и optional query_id в existing
observer_verify. Синтаксические JSON Schemas проверены на1650 фактических
program/certificate outputs, включая UNKNOWN; это не замена semantic checker.
Подключённый LivingMath plugin выполнил auto fallback и проверил84 train witnesses:
run `088107944ec34553f0b0db0fa4192aee530a56fe043b447e9b2af72e5403a89a`.

CPU5s/wall6s/RAM512MiB, shared2active/16queued и HTTP caps сохранены.
Role scope8 по умолчанию, явно≤12 tokens,≤91 cells,≤512 split trials,32 AST nodes,
depth/recursion8; equality scope8 прежний. P1 pilot256 queries длины12:
CPU0.834s/wall0.870s/RSS62580KiB,UNKNOWN0,LLM0. Это не performance обещание.
Первый параллельный QA вызвал018_RESOURCE_BUSY/429; исходные traces сохранены.
Повтор выполнен последовательно, с клиентским backoff только этого pre-execution
кода и тем же request key. Ограничения сервера не ослаблялись.

## Сохранность и пределы вывода

Два backup:4 SQLite и все workspaces, второй при остановленном HTTP перед cutover.
Сохранены42598 initial/42808 cutover файлов; допускаются только byte-identical
объекты или append-only расширение journal с неизменным префиксом.
4/4 integrity_check OK, прежние строки всех трёх исследовательских SQLite неизменны,
paths/inodes сохранены; OAuth — штатно истекающее состояние авторизации.
Все55 journal chains корректны,47 исходных runs неизменны,124 новых QA runs
имеют ровно start/finish. Численное75-file ядро и132 protected source files
побайтно сохранены, включая Symbolic V1 worker whitelist, старые evaluator/checker,
SP, frozen core/workspace/source bridge. Перезапущен только HTTP, tunnel PID1801300
и адрес сохранены. [Integrity receipts](integrity_results.json).

`UNIVERSAL_INVARIANT=false`. `CHECKED_INSTANCE` — конечное вычислительное
свидетельство, `CHECKED_FINITE_INSTANCE` — проверка feature на заданных данных.
Family остаётся UNDERDETERMINED; mathematical verified/execution grant не выдаются.
Роли буквальны; covariance требует совместного переименования токенов И bindings.
Coordinate/equality инвариантность или NF-factorization из этого не следуют.
Native SUTI не исполнялся, R3 approval PENDING. Физическая интерпретация,
универсальный язык и смысл Нострадамуса не установлены; дальнейшая иерархия
токенов/alpha grounding требует отдельной проверяемой постановки.

[README полного пакета](README.md), [RCA](RCA.md), [изменения](CHANGELOG_RU.md).
