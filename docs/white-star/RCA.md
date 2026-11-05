# RCA и пределы вывода

## Исправленные интеграционные причины

- Из JSON-конфига root приходит str, а тесты первоначально передавали Path. Startup recovery обратился к str.exists и staging не поднялся (OAuth502). Root нормализуется вPath; отдельный regression проверяет реальную строку конфига. Production до исправления не изменялся.
- Worker read allowlist первоначально пытался получать passwd home после запрета чтения. NSS lookup перенесён до Landlock; malformed startup handshake теперь становится ENGINE_UNAVAILABLE. Реальные probes подтверждают запрет credentials и файловой записи. SHA supplied kernel не менялись.
- Отмена MCP-сессии могла оставить принятый run RUNNING до restart. Отдельная shielded задача завершает durable job независимо от отмены клиента; actual cancellation regression и staging SIGKILL recovery прошли.
- Countermodel к усилению утверждения должен проверяться отдельно от основного примера. Generic wrapper разделяет эти обязательства; проверены positive/negative observation/control/cyclic cases. Исходные rational operations переиспользуются без изменения.
- Strict JSON не допускает bool/float вместо integer,NaN,неизвестные keys,deep input,фальшивые SHA/UTF8 spans. Wrapper добавляет проверки, не чинит смысл за LLM. Missing/unsupported модели не становятся формальным успехом.
- Первый операторский запуск staging произошёл до публикации адреса quick tunnel; его частичная подготовка сохранена отдельно и повторена. При намеренном SIGKILL SDK TaskGroup прервал соединение сHTTP502: это ожидаемый результат fault injection; переданная команда и RUNNING-prefix сохранены, после restart получен INTERRUPTED.
- В6 timing-run profile supervisor readiness не был сохранён до close. Raw cold import измерен там; настоящие cold worker observations отдельно находятся в MCP white-star-status.json. Samples не повторялись ради лучшего времени. Воспроизводимый profiler исправлен на сохранение readiness до close.

## Что не доказано

- Encoder fixtures и координаты не универсальный semantic basis и не gold truth. Фиксированный k-кандидатный поиск не перебирает смыслы и не ранжирует художественную ценность.52 режима относятся только к конкретному readout/atlas.
- MATCHED_INPUT означает одинаковый frozen semantic payload. Разные координатные/Bridge projection assumptions всё равно остаются; их вклад не отделён как универсальный причинный эффект.
- Ветка suti в этом опыте реально выполняет текущий source-assurance Bridge facade, без нового extraction. Её frame selection — first-K declared concepts. Не выполнялись native SUTI,весь DAV pipeline или универсальное построение теории смысла. Source-field attestation не превращает labels/relations в истину стихотворения.
-22 прочтения получены4 реальными вызовами одной модели, evaluator — ещё1. Повторное использование этих receipts в production не является новыми генерациями. Automated evaluator субъективен; внешней human экспертизы нет. На двух источниках он предпочёл разные ветви; общий победитель и accuracy не установлены.
- Matrix exemplars объявлены QA-клиентом по поставленному коду. Успешные3 экземпляра не доказывают верность литературного переноса или физики. Реальные отрицательные результаты сохранены; unsupported language возвращает UNSUPPORTED_MODEL.
- Source rights — декларация владельца, не юридическое удостоверение; White Star exports private-only. Raw source SHA,common snapshot digest иencoding digest различаются и не взаимозаменяемы.
- Legacy/base assurance release строкиv0.1,semantic contractv0.2 иmain servicev0.3 описывают разные совместимые слои. SDK1.30.0 сохранён. White Star profile проверен наPython3.13/Linux x86_64/Landlock ABI≥3; остальные платформы не заявлены.
- R3=PENDING,external human reports0; physical execution=false. Действующий quick-tunnel URL сохранён при HTTP-only restart, но сам quick tunnel не является постоянным доменом.

Все29 инженерных пунктов имеют доказательства иPASS; отсутствие научных/человеческих свидетельств не скрыто и не объявленоverified.
