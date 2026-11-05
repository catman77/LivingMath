# Экспериментальная программа после PATCH-003

## 1. Два независимых полигона, никакой подгонки под Нострадамуса

**Полигон A — математический S/P.** Известны точные ответы, допустимые преобразования, различимые истории и клеточная структура. Цель — проверить способность нового MCP *самостоятельно строить и проверять* отношения между маршрутами.

**Полигон B — сложные смысловые структуры.** Французский Нострадамус с сохранёнными иерархиями, позднее Малларме. Цель — проверить перенос обнаруженных структурных отношений на неизвестные фрагменты. Гипотеза может проиграть punctuation baseline — это не инженерный провал, если предсказания честно заморожены и источник неопределённости указан.

## 2. SP-0 / SP-1: определить объект до поиска инварианта

`X_N` задан в `04_FORMAL_MODEL_RU.md`. P0: N=2,4,6,8,10. Строим позиционные 1-ребра, исходные слова и локальные peak witnesses; сравниваем `faces=none` vs `all_local_peaks`. Отдельно вычисляем H1(F2) и path-coherence certificate. Контроль: один конец ε — не повод схлопывать путь. Никакого вывода из «β1=0 после факторизации» без законных 2-клеток.

Три объекта нужно показывать рядом, но не отождествлять: `graph π1(F_beta)`, `H1(F2) after chosen faces`, `π1 proof status after explicit 2D witnesses`.

## 3. SP-2: метаморфизмы и независимость названий

Глобальное S↔P действует на множестве balanced words. Проверять строгий структурный изоморфизм `X_N→X_N`: вершины, positional edges, 2cells и joins должны переводиться биективно. Не ожидать буквального равенства content-addressed IDs. Разные истории одного слова допустимы и видны при provenance identity. Пример `SSPP` и `SPSP`: equal q=0, different word/reduction geometry. Сверить с previous live runs в `01_RCA_AND_DECISIONS_RU.md`.

## 4. SP-3: индукция на скрытой грамматике, самостоятельное порождение признаков

Train: все 28 balanced words длины 2,4,6 с метками Dyck. Test длина 8 (70, positive=14), длина 10 (252, positive=42) на независимом oracle. Базовая цель не «сделать 100% любой ценой», а выяснить, **из каких именно конструктивных операций получен предикат**. Если модель выбирает built-in `pair_0_max`, записывать это и показывать отдельно.

Валидация: (`feature_allowlist` без builtins) → попытка синтеза новых `AST` из разрешённых операций с доказательным trace → blind test; если синтез не найден, `NO_VERIFIABLE_NEW_OBSERVER`. Нельзя называть встроенный balance-minimum self-discovery.

## 5. Нострадамус: задача переноса отношения между строками

Источники: one French reading per quatrain, архив Sacred Texts `nos/mrg`, избежать перевода и apocryphal. Полный охват — 942 основных катрена: I–VI и VIII–X по 100, VII — 42. Источниковедческая оговорка: исходный merged archive автоматически коллатирован из неоднородных версий; записать оригинальные byte spans и аномалии I.51, II.32, II.38, не исправлять silently.

Hierarchy: `(century,quatrain,line,word,byte_span)`. Train I–VIII, holdout IX–X. Для теста оригинал против перестановки строк2↔3 **каждый вариант** кодировать α-канонически независимо, иначе утечка порядка через метки символов. `IDENTICAL_E` → `NOT_IDENTIFIABLE`. Для train II.5 и VII.2 ожидаются конфликты canonicalized labels; не прятать их, пометить как отдельный irreducible loss, затем альтернативный conditional-gate report (с явными исключениями).

### Базовые линии

- majority (50% на balanced original/swap парном наборе);
- punctuation-only: последний знак каждой средней строки (сравнить порядки);
- length-only: длины средних строк, без слов;
- global α + explicit line boundaries;
- local α per line;
- literal words (только диагностический baseline с явно сохранённой лексикой);
- newly synthesized context relation (не давать ready-made labels). 

Метрики: dataset hashes, exact label budget, pairwise wins/losses/ties, abstention coverage, accuracy on decided and all pairs, disaggregated by century/length/representation, false positives/negatives, source-bound witnesses. Сопоставлять только при одинаковых train/test scopes и compute budgets.

### Научное требование

Предпочтение оригинала `w` над `π(w)` объяснить операторным witness, например: у данного `line→quatrain` контекста композиция `u v` сохраняет проверенное отношение, а `v u` его разрушает; воспроизвести на новой центурии. Если найденные правила не превосходят пунктуацию и перестановку на равном тесте, итог: `NOT SUPPORTED`, без задним числом придуманных смыслов.

## 6. Эксперимент «смена наблюдателя»

Те же quatrains без изменения train/test и seed, каждый прогон использует **одну** строго объявленную трансформацию входа: пословная, построчная, α-global, α-local, punctuation-only, word-id/provenance-id; затем paired observer comparison с source-bound distinction witnesses. Запрещено сравнивать raw counts через разные resource caps без нормализации, выдавать рост уникальных состояний за глубокое содержание.

## 7. Расширение на другие тексты — не P0

После SP proofs и Nostradamus pairwise можно брать Малларме или синтетические nested grammars. Для Малларме нужно отдельно хранить типографский 2D-layout, иначе линейная транскрипция не сохраняет важную часть композиции. Проверять cross-text перенос only after frozen model, не использовать LLM interpretation для отбора features.

## 8. Stop rules

- Не заменять точный SP oracle более дорогим случайным генератором.
- Не запускать многочасовые прогоны: bounded worker 5–6 секунд; если сложная задача требует больше, batch sharding и explicit sample counts.
- Не обсуждать «новую фундаментальную группу нуля» без предъявленного cell policy.
- Не выдумывать победу на Нострадамусе. Если 50%, зафиксировать 50% и искать причину в representation, feature provenance и выборке.
