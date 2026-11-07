# Установка и откат

Соберите wheel из текущего checkout через `python -m pip wheel --no-deps .`;
используйте закреплённые зависимости `pyproject.toml` и существующую полную
production-конфигурацию. Подготовьте native через `lm-suti white-star prepare`;
проверяйте SHA собранного бинарника и исходных vendor-файлов. Для HTTP
используйте существующий `tools/release_v01_entry.py`, exact owner authorization
и SHA-manifest immutable runtime. Подмена manifest без обновления авторизации
блокирует запуск. Не запускайте новый tunnel при обновлении HTTP-сервиса.

До переключения сохраните все SQLite через SQLite Backup API и проверьте
`PRAGMA integrity_check`. Сохраните workspace CAS, все журналы и их hash-prefix,
старые release JSON/drop-in и URL. При ограниченном диске CAS staging может
ссылаться hardlink на неизменяемые объекты; журналы должны быть независимыми
копиями. Резервная ZIP-копия содержит самостоятельные байты, не hardlinks.

Откат кода: остановите только `livingmath-http.service`, восстановите прежний
systemd drop-in, выполните `systemctl --user daemon-reload` и запустите HTTP.
Данные и новые QA-записи не удаляйте: предыдущая версия не использует `nl.*`,
но хранит append-only историю. Базы восстанавливают только при подтверждённом
повреждении, после отдельного сохранения всех новых событий. Проверьте прежний
endpoint, health, четыре базы, старые записи и hash-chain; tunnel не трогайте.

Точные приватные пути, runtime manifest и deployment receipt хранятся у
оператора в `~/.local/state/livingmath/nl002/`; credentials, базы и пользовательские
workspace не входят в публичный пакет. Полный воспроизводимый QA использует
`tools/nl002_mcp_qa.py`, `nl002_controls_qa.py`, независимый
`nl002_independent_checker.py`, опубликованные fixtures и frozen receipts.

Фактическая cutover-копия workspace использует полный
`backup-before/assurance-workspaces.zip` плюс наложение
`backup-cutover/delta-workspaces.zip`. Для восстановления нужны **оба** архива:
сначала base, затем delta; полный SHA-инвентарь cutover проверяет результат.
SQLite cutover snapshots самостоятельны. Delta не является полной копией.
