# RCA до реализации

Baseline:e65b1a1, production0.4.12/98 tools. Архив — спецификация, не код.

`nl_proposal.decoder.build_move` переставляет внешний quantifier spine по source byte order и проверяет типы. Источник связывает байты и происхождение, но не доказывает смысл или оправданность перестановки. Старые source_licensed=false и matched_ablation сохраняются.

`fol.countermodels` ищет конечное различие, не синтаксическое доказательство равенства. H0/H2 совпадают на16 одноэлементных моделях; при двух элементах каждого сорта имеется20 relation cells, больше старого cap16, поэтому возвращается UNKNOWN_BOUND/RELATION_CELL_BOUND. Нельзя превращать этот halt в equivalence. Новый alpha checker должен завершить такую пару до enumerator.

Коллизия путей ТЗ: `semantic_bridge/` уже существует и публикует9 методов. Поэтому новый изолированный слой размещается в `semantic_bridge/contextual/`; старые service.py/mcp.py и их схемы не заменяются. FormalService используется для проверки фактической выдачи source/model refs в текущем проекте.

Новый слой не решает авторский смысл и не вызывает LLM. Формальные assumptions — явные предложения; языковые presuppositions, anaphora, temporality остаются OPEN. При formula TRUE/assumption FALSE применимость CONTEXT_INCOMPATIBLE, без изменения formula truth.


## Найдено и исправлено до production

1. Python equality принимала False вместо binder index0 в сертификате. Независимый
checker теперь сравнивает canonical JSON, сохраняя строгие типы; bool/float
forgery regression PASS.
2. fol.evaluate при UNKNOWN_BOUND не выдаёт evaluated_nodes. Оболочка раньше
учитывала его как1step и могла повторять уже исчерпанные проверки. Теперь первый
такой halt завершает анализ FORMULA_EVALUATION_BOUND с консервативным списанием
оставшейся allocation. OPEN_WORLD UNKNOWN не блокирует дальнейшие проверки.
3. Автоматически добавленный obligation мог дублировать ID и превысить8.
Входные obligations теперь сохраняются дословно, generated language_gap отдельно.
4. Черновые bounds15pairs/16models приведены к точным10/8 из раздела3 ТЗ.
5. Первый MCP harness ошибочно требовал0 completed pairs при max_steps1.
α-пара успевает получить корректный сертификат перед halt следующей пары;
исправлен только тест: частичный результат обязан сохранять эту работу.
Первая неуспешная трасса оставлена отдельно, финальная приёмка65 PASS.
6. Первая сборка использовала runtime-venv без setuptools.build_meta и не
создала wheel. Сборка выполнена существующим отдельным build окружением;
production зависимости не менялись. Финальный installed wheel511 PASS.

Все исходные отрицательные результаты/логи сохранены в delivery. Старые kernels,
формальные определения, source rights и защитные правила не ослаблялись.
