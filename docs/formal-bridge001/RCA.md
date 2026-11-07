# RCA LM-FORMAL-001

Исходная роль только одной пары и обязательная EPS база не выражали общий ALT,
независимый nonnullable start и конечную память. anbn непустой тест выглядел
успешным, но ε выявил реальное различие гипотез. Исправлена выразимость конечного
поиска, а не увеличен бессмысленно бюджет/длина и не импортирован language oracle.

Независимые ревью обнаружили и воспроизвели до выпуска:

- Negative two-token pruning ошибочно исключал center/nonnullable программы;
  применяется теперь только к EPS/literal-pair семейству.
- Catalog materialization была вне Budget; теперь generation/sorting ограничены,
  необследованный recipe явен. Все UNKNOWN не объявляются NO_COMPATIBLE.
- DFA рекурсия по trie edges могла переполнить Python stack; заменена iterative
  constraint traversal,1534-edge контроль реально выучил1state.
- FOL countermodels игнорировали assumptions; теперь требуется истинность всех
  предпосылок и выдаются assumption truth vectors/scope.
- Candidate source_ref был fingerprint вместо issued storage ref; исправлен.
  Дубликаты proposals имеют отдельные candidate IDs; derivation hash охватывает
  определённое derivation payload, не циклические alternative ID links.
- Contrast fallback принимал несуществующий anchor; теперь anchor валиден и owned.
- Общий synthesis CPU bound теперь даёт UNKNOWN-предсказания, сохраняя валидацию
  всех query labels/source, вместо INTERNAL_SYMBOLIC_ERROR.

Неуспешные окружения/harness не скрыты: сначала отсутствовал legacy tiktoken,
восстановлены все48 прежних dependency versions; начальный request до READY
отклонён; harness требовал новый train даже при отсутствии аннотации — исправлен
критерий, исходная попытка сохранена. `(ab)+`2FP были реальной недоопределённостью:
сохранены, затем исправлены внешними ответами на actual contrast queries b/abbab,
новые train generations, без heldout labels и без ручного выбора удачного AST.

В протоколе SAPB/ASBP ошибочно названы позитивами при парахS/P,A/B. Собственный
reference отвергает их; правильные nestedSABP/ASPB включены. Исходники/метки не
переписаны. ε в enriched abplus —seen control, а не новый blind holdout.

Остатки: canary256UNKNOWN/no recovery; произвольный NL→FOL decoder не реализован
и не требуется для разрешённого v1 manual/provider контракта; human adjudication
NOT_EXECUTED, native SUTI NOT_EXECUTED, R3 PENDING. Ничто из finite checking не
становится universal grammar, author intent, mathematical verified или grant.
