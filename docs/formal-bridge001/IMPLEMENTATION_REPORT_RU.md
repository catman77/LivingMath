# LM-FORMAL-001: реализация и реальная приёмка

Установлен **v0.4.9-developer-preview**, deployment `formal001-20261107T032742Z`.
Адрес сохранён: `https://fares-september-rebel-board.trycloudflare.com/mcp`. **91 инструмент:83 прежних +8 formal_***.
Архив ТЗ сохранён без изменений в docs, SHA256 `06f76303c87510b43504f97662f1cff8a0528e6b8056031ac08e08e0186a7b00`.
Восемь suite на стенде: **12102 PASS /2465 MCP calls**;
на настоящем публичном HTTPS/OAuth: **12103 PASS /2466 MCP calls**.
Это программные проверки, не столько независимых математических инвариантов.
Разница счётчиков связана с фактической пагинацией bounded artifacts; все исходные
запросы/ответы/wire и результаты сохранены. В943 legacy checks входят320 явно
локальных supplied-AST controls, не серверное открытие. Все31 прежний A/B gate PASS.

## Фактическая исходная граница

До правок зафиксированы Git `5c756c038fa528bc933f03e99bab0cbc402a3606`, состояние working tree,
bridge_system_status, health и tools/list0.4.8.409 source tests и1066 legacy/20SKIP
прошли до модификации; supplied reference rerun:225 asserts/9450 membership checks.
Пять предоставленных live runs заново исполнены старой0.4.8 с точными result_digest,
включая ε false positive. [Baseline](BASELINE_REPLAY.json).
Недоступные исторические ID для прежней серии764 слов не выдумывались; новые
сравнения используют точные8 datasets из previous ZIP. Их исходные метки неизменны.

## Что реализовано

CFG IR: finite terminals/nonterminals, independent start, EPS/TERM/NT_REF,
упорядоченный RHS Seq и несколько productions одного LHS как Alt. Каталог
генерирует data-bound terminal relations и все заявленные sequence shuffles,
nullable/literal-pair/observed-center bases и independent starts; не все CFG.
Каждый рассмотренный AST, pruning counterexample, rival и untried recipe сохраняется.
Сортировка по construction size/terminal types/NT count/recursive arity/SHA.

Parser достигает least fixed point и сохраняет packed alternatives. Независимый
checker выполняет собственную global saturation и source reconstruction; не
импортирует producer/search. Проверяются start/rule/child order, terminal role,
UTF8 spans и source/grammar fingerprint. Для negative нужен complete chart.
В `S→SS|a`, `aaa` сохранены два различных дерева. Циклы/лимиты дают
UNKNOWN_CYCLE/UNKNOWN_BOUND, не ложное отрицание. [Forests](PARSE_FORESTS.json).

DFA — полный delta table и state trace; canonical BFS naming; train-prefix
constraint search с fixed state bound1…4. Остановка на первом совместимом уровне —
ресурсная политика, не теорема минимальности/уникальности. Ни production search,
ни evaluator не импортирует reference oracle, palindrome/parity/Dyck builtin.

Новые tools используют существующие FastMCP/HTTPS/OAuth/Workspace/isolated pool
через прежний worker action; numeric75, Symbolic V1/role/SP/frozen kernels,
worker whitelist и145 protected source files побайтно сохранены.
[Архитектура](../../ARCHITECTURE.md), [контракты](QUICKSTART_RU.md).

## Конечное сравнение

| Case | TP | TN | FP | FN | UNKNOWN | Seen controls |
|---|---:|---:|---:|---:|---:|---:|
|cfg_anbn|1|255|0|0|0|0|
|cfg_anbn-enriched|3|3|0|0|0|0|
|cfg_even_palindrome|16|240|0|0|0|0|
|cfg_dyck2_new_stratified|40|216|0|0|0|0|
|cfg_dyck2_new_stratified-enriched|40|40|0|0|0|0|
|cfg_marked_palindrome-enriched|16|16|0|0|0|0|
|regular_even_a-enriched|64|64|0|0|0|0|
|regular_ab_plus-enriched-pre-active|2|127|2|0|0|1|
|regular_ab_plus-enriched|2|129|0|0|0|1|
|noncfg_anbncn_canary|0|0|0|0|256|0|

В исходных одинаковых train/query режимы role_branching_ast и auto сравниваются
с новым cfg/dfa namespace. Dyck2: старые TP0/FN40, новый TP40/FN0 на тех же256;
на отдельно замороженных hard balanced negatives —40TP/40TN. Старый auto уже
решал обычные palindrome/marked cases; улучшение не приписывается там, где его нет.
Parity: старый role/auto дал all-positive128FP; новый явный двухсостоянийный DFA
дал128TP/128TN на тех же256. [Полная матрица](FORMAL_LANGUAGE_MATRIX.json).

Enriched: palindrome16+16, marked reverse16+16, typed pairs40+40, parity64+64.
Для anbn при scope≤12 после train длины2/4/6 доступны только3 новых положительных
слова; они не дублируются ради требования16. `(ab)+` enriched содержит130 новых
слов и1 уже размеченный ε-control; unseen метрики отделены. Данные query-only,
модель запечатана до predictions, gold прочитан после всех inference.
80 Unicode-renamed typed-pair queries также независимо проверены/совпали.

Canary a^n b^n c^n **не восстановлен**:256UNKNOWN в объявленном каталоге.
Это не невозможность всех CFG/наблюдателей и не положительный language recovery.
Отрицательный контроль PASS относится к честной границе claims, не accuracy.

## Активное уточнение вместо скрытой истины

На исходном anbn train сохраняются nullable/nonnullable кандидаты. Сервер сам
выдал ε как различитель без правильной метки. После отдельного внешнего ε=False
создан новый train/run. В aux-прогоне реально индуцирована двух-NT модель:
внутренний NT nullable, независимый start — нет; ε получает REJECT_COMPLETE и
independent CHECKED_INSTANCE. Исходный FP не переписан.

Parity even-length train допускает две разные машины; внешний ответ a=False
добавлен отдельным актом. Для `(ab)+` после начальных ε/a аннотаций оставались
3 совместимых автомата и2FP. Реальные contrast запросы `b` и `abbab` получили
внешние False; после двух НОВЫХ поколений ошибок0, итоговая машина имеет4 states.
Ни одна правильная метка не порождена из prediction/confidence. Short annotation
holder отдельный; его words≤6 не совпадают с новым odd-length holdout7.
[Трассы аннотаций](ACTIVE_ANNOTATIONS.json), ошибки pre-active сохранены в матрице.

## Формальные трактовки и модели

Три вручную предложенных чтения «Каждый исследователь проверил одну гипотезу»
сохранены под одним source_ref с отдельными AST/spans/provenance. Σ типизирована;
перепутанные сорта, свободные переменные и неизвестные predicates отклоняются.
Две closed конечные модели дают `[T,F,T]` и `[T,T,F]`; для каждой пары найден
countermodel. Учитываются assumptions: модель, нарушающая общие предпосылки,
не является допустимым различителем. [Формулы/модели](TYPECHECK_AND_MODEL_COUNTEREXAMPLES.json).

Дополнительно25 human-annotated controlled inputs,50 exact model evaluations и
две фразы с неоднозначным scope/negation. Их предложенные формулы дают различные
значения в предъявленных моделях. Разные источниковые derivations не схлопываются.
Это автоматическая проверка **ручных proposals**, не NLP extraction accuracy.
`PROPOSED` source alignment, `TYPED` representation и `FINITE_MODEL_CHECKED`
раздельны; author intent/human agreement не доказаны. Open-world input =>UNKNOWN.

## Проверки и эксплуатация

430 source PASS,430 installed-wheel PASS (вне checkout, pythonpath override),
1066 legacy PASS/20 existing SKIP,225 independent reference assertions.
Независимые math/service reviews: NO OPEN FINDINGS;21 targeted tests и отдельные
реальные concurrency/recovery/isolation probes. Шесть rehashed MCP tamper cases
отвергнуты, grant отсутствует. Same-key не создаёт job, смена payload конфликтует,
чужой source/anchor отвергается; четыре real replays и offline network-disabled
production bundle REPLAY_MATCH. Полные raw failed/success logs в delivery ZIP.

Оба backup:4SQLite + все workspaces, второй при quiescent HTTP.53616 initial и
53790 cutover файлов сохранены; только immutable bytes или append-only journal
prefix extensions.4DB integrity/inodes/прежние строки, все journal chains и52
исходных snapshot records проверены. OAuth нормально истекает, не считается
неизменяемой исследовательской записью. Runtime manifest215files, native SO
прежний. HTTP перезапущен отдельно; tunnelPID1801300/URL сохранены.
[Integrity](integrity_results.json), [ресурсы](RESOURCE_BUDGET.json).

[Изменённые файлы](CHANGED_FILES.json), [RCA](RCA.md),
[ограничения/следующие обязательства](LIMITATIONS_AND_NEXT_OBLIGATIONS.md).
UNIVERSAL_INVARIANT=false; native SUTI NOT_EXECUTED; R3 PENDING.
