# PATCH005 RCA

Root cause: min(available) от положительных длин ограничивает offsets, затем
len(guards)>=2 блокирует recursive constructor при коротком positive. Evaluator
и независимый checker не ошибались на epsilon/singleton и не менялись. Исправлен
opt-in generator: closures предлагаются до полного membership validation.

Доказательства:11 первоначальных regression RED, fresh real0.4.6 baseline61PASS
с exact7/0 и10/2, новый real MCP finite transfer и staged/public digest matches.
Один supplied PS run отсутствует: сохранён NOT_FOUND, новый control имеет новый
run/key и не изображается восстановленной историей. Полная таблица в
OLD_NEW_COMPARISON.json.

Обновлён один прежний resource test: расширенный generator теперь законно
предлагает full conjunction; для изоляции recursion bound добавлен max_ast_nodes10,
исключающий большие ANDs. Защиты не отключались. Устранён cross-test import для
самостоятельного installed-wheel запуска; setuptools отсутствовал в runtime venv,
wheel собран существующим build venv без изменения production dependencies.

Две ошибки harness сохранены с исходными FAIL: старый PATCH004 runner сравнивал
с0.4.5, удаляя уже существующее optional field из baseline0.4.6; условие теперь
зависит от настоящей baseline schema. Runtime failure выдаёт isError MCP envelope
и сохраняет FAILED row; новый runner сначала ожидал row напрямую. Проверяется
точный BUDGET_EXCEEDED и отдельно FAILED record без результата. Финальные полные
прогоны используют новые QA keys/projects и проходят.

Успех ограничен указанными finite test cases. Odd1/3 ambiguity и48FP сохранены;
нет скрытого выбора по holdout. Исторический Symbolic generator намеренно
сохранён для совместимости, новый catalog относится к opt-in observer path.
