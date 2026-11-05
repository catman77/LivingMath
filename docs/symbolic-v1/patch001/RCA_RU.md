# RCA — PATCH001

Исходный0.4.0 learner выбирал одиночный endpoint feature:8 train samples не различали его и вложенное правило. Это ограничение класса/выбора гипотез, не дефект S/P-математики. Добавлены только композиции реально наблюдаемых отношений; все retained candidates проверяются на train, а семья остаётся UNDERDETERMINED с внешними membership-пробами.9/9 выбранного кандидата не превращается в theorem/UNIQUE.

В search повторялся фактический proposal cycle без роста. INSERT_CANCEL_PAIR был разрешён, но не предложен. Теперь остановка отражает только обследованный local cycle/window с replayable certificate; менять Удава/притворяться global no-go не потребовалось.

Ошибки разработки и проверки сохранены:

- Первый relational rank ошибочно принимал offset внутренней позиции за число покрытых отношений. Red-test RELATIONAL_RED.log выявил выбор одиночного внутреннего guard. Ранжирование исправлено по реальному количеству наблюдённых отношений, без доступа к heldout labels.
- Comparison возвращала tuples: strict MCP JSON boundary отвергал ответ. Теперь read-only результат нормализован через canonical/strict_json; отдельный regression запускает настоящий ToolManager.
- Неподходящий NFC test использовал кириллическую е с acute: Unicode не обязан сворачивать такую последовательность. Применён реальный составной й (и+breve), без ослабления byte-map проверки.
- Первое подключение к staging пришло до завершения warm startup. Добавлена проверка listen, прежний connection-failure лог сохранён.
- Runtime venv не содержит setuptools для сборки wheel. Ошибка packaging и failed preinstall-test сохранены; сборка выполнена в существующем build venv, установленный wheel261 тест прошёл независимо. Production venv не получал лишние build dependencies.
- Метрика сложности дерева теперь считает узлы, а не выдаёт node budget за фактический размер. Source pointers относятся к frozen sorted train_samples и sample digest.

Старый symbolic code binding намеренно строгий: вычислять старые bundles новым learner и молча признавать совпадение было бы неверно. Реальный старый установленный worker выбирается по operator-approved manifest; старый и новый profiles разделяют прежнюю очередь/active quota. Unknown binding не запускает код из bundle.

Незакрытых инженерных FAIL в итоговой приёмке нет. Исследовательские границы: один train corpus, finite holdouts,5 operational candidate classes,4 inconclusive fixed cases, отсутствие уникальной grammar/литературной истины; full pentest, длительная нагрузочная сертификация и hosted CI не проводились. Эти ограничения не переименованы в PASS.
