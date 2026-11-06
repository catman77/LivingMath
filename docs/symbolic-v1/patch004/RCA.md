# RCA PATCH004

Пропуск0.4.5 находился между реально сгенерированным iterate_on_inner_fragment
и feature admission: старый promoter принимал лишь literal-context формы.
Для COPY отсутствовал генератор структурного разреза с полным равенством двух
фрагментов. source_run_id сохранялся как metadata без обязательного чтения
оригинального результата. Это были пробелы исполняемого контракта.

Исправление: четыре закрытые typed AST формы, существующие primitives и общий
structural-cut generator; отдельный checker повторяет source/primitive traces,
полный train и scope. Source bridge читает настоящие immutable artifacts.
Нет benchmark-name branch, scalar surrogate, LLM judge или синтетического run.
Дополнительные review-дефекты исправлены до wheel: AssuranceError(ValueError)
больше не проглатывается как отклонённый кандидат; canonical JSON сравнение
различает bool/int/float; provenance/witness fields закрыты; outer digest и
ложные вложенные proof claims проверяются. Исходные RED logs сохранены.

Первый MCP стенд остановлен на ошибке организации harness: численный export
охватывал весь смешанный QA project и возвращал193 chunks посторонних observer
objects. Все накопленные проверки были PASS; исходный partial transcript/log
сохранён. Численные тесты перенесены в отдельный QA namespace, запросы/лимиты/
checks не ослаблены, полный новый прогон и production прогон завершены.

P2 ограничен выразимостью: SP/PS дают одинаковые equality-pattern при разных
Dyck labels. Текущий генератор не выражает ориентацию этих атомов. Дополнительный
корпус не запускается согласно исходному roadmap. Для следующего исследования
потребуется отдельно обосновать source-grounded oriented relation; здесь оно не
добавляется ради успеха. Review/конечная проверка не являются refutation всей
исследовательской программы или доказательством математической истины.


Публикация: клиент загрузки GitHub не дождался HTTP-ответа, хотя154364857 bytes
уже были приняты. Повторная проверка существующего asset ID подтвердила status
uploaded, точный размер и SHA256; повторной загрузки/дубликата не создавалось.
Существующий draft опубликован после этой проверки, URL перечитан из release API.
