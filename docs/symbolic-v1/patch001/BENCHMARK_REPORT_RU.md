# BENCHMARK_REPORT_RU — PATCH001

## Независимая проверка

Обучение получает только8 слов длины4:4 positive и4 negative из ТЗ. Выбор кандидатов/различающих запросов не получает predict, тестовые слова или метки. Frozen models записаны до внешнего оценивания. Бывший endpoint-only baseline взят из действительного historical run `209907950b828417079e023acaa23e4c8bacf5397c4f7c36439e69bcac825be6`, а не переизобретён.

| Набор | Прежний endpoint | Новый выбранный кандидат |
|---|---:|---:|
|9 уникальных слов из протокола |6/9|9/9|
|False positive rate на этих9 |0.6|0.0|
|1200 дополнительных случаев, длины6/8/10,20 seed |0.5000 accuracy|1.0000 accuracy|

На дополнительных данных unigram:0.5000, bigram:0.4858, simple-context:0.5292. Это20 randomized holdout seeds **одного заданного train-корпуса**, не20 независимых открытий грамматик. Negative имеют те же края, длину и token counts, что соответствующие positive. Тест на чётные длины не устанавливает результат для любой бесконечной области.

## Что именно выведено

На positive обнаружены одинаковые отношения равенства между краями и краями внутреннего фрагмента. Из этих наблюдений строятся одношаговые, конечные составные и рекурсивно повторяемый кандидат через SPLIT/REVERSE/equality. Последний выбран по покрытию наблюдаемых отношений и описанной сложности:8 operation nodes, depth4. В kernel нет готового типа языка или проверки по имени палиндрома; внешний reverse-oracle находится только в test harness.

Сохраняются5 train-compatible operational candidates, две дополнительные finite-language countermodels и активные membership-запросы. Поэтому семейство **UNDERDETERMINED**, выбранный кандидат — **EMPIRICAL**. На9 исходных запросах5 дают consensus внутри сохранённого operational набора,4 — INCONCLUSIVE. Все3 прежних ложноположительных попадают в INCONCLUSIVE;9/9 — accuracy выбранного кандидата, а не доказательство однозначности семейства. Consensus также не означает UNIQUE.

A↔X/B↔Y и локальные независимые переименования сохраняют выбранный relational AST и решения. Отдельные запросы с разными predict-масками дают одинаковый frozen hypothesis_digest. Два активных цикла: сервер предлагает зонд, внешний holder вычисляет synthetic label, последующее обучение добавляет её как новое свидетельство; предыдущий snapshot неизменён, family остаётся UNDERDETERMINED.

## Поиск и реальные тексты

Для исторического ab запроса новый selector выдаёт точно прежний trace-prefix до остановки:18 шагов/72 кандидата вместо128/512;9 nodes,8 literal words. Выявлен повтор actual clock-state без новых путей. INSERT_CANCEL_PAIR разрешён, но не предложен в обследованном цикле. Certificate имеет bounded/local scope, global_exhaustion_proved=false; это **не** замкнутость всей алгебры. Алгоритм выбора Удава не изменён.

Для Малларме использован фактический source snapshot с SHA `fa7e64241104d5b195e9542f568a329937d11eb6a590f3af12870db63172c91a`. Перестановка строк различается по literal/composition. Биекция двух равночастотных ASCII-букв сохраняет полный frequency histogram, byte-width/границы и global alpha; literal меняется. Layout отмечен как UNAVAILABLE, если не передан. Семантическая истинность не оценивалась. Нострадамус согласно ТЗ не блокирует этот patch и заново не заявляется проверенным.

## Воспроизведение

```bash
python tools/symbolic_patch001_benchmark.py --output /tmp/patch001-new --old-model replay/old-grammar.json --mallarme replay/mallarme-historical-request.json
```

Оба входа, frozen models,1200 words/labels, метрики, active-cycle и Mallarme artifacts входят в delivery. Сервер не принимает heldout labels как аргумент evaluate; оценивание выполняется внешним holder. LLM_calls=0, execution_permission=false. Универсальность/семантика/физические выводы не заявляются.
