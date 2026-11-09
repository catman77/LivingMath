# PATCH002 — backup и откат к0.4.14

Текущий принятый deployment `semantic-bridge002-20261109T063739Z`. У оператора: `~/.local/state/livingmath/semantic-bridge-patch002/backup-before` (4 SQLite + Workspace ZIP + полный SHA inventory), `backup-cutover` (первый snapshot и auto rollback) и `backup-cutover-final` (успешный quiescent snapshot + delta overlay + старый drop-in/config/pointer). Исходные107297 файлов и все research rows сохранены. Это приватные резервные копии, не часть публичного пакета.

Для code rollback остановите **только** livingmath-http.service; восстановите точный drop-in.conf из backup-cutover-final и прежний production-install pointer из OLD_INSTALL.private.json атомарной заменой, сохранив owner-only0600. Выполните `systemctl --user daemon-reload` и `systemctl --user start livingmath-http.service`. Не перезапускайте livingmath-https.service и не меняйте origin. Старый v0.4.14 runtime/wheel/venv сохранены отдельно в semantic-bridge-patch001-final и предыдущем GitHub release.

Откат кода **не восстанавливает поверх живых баз старый SQLite/Workspace**: это уничтожило бы новые append-only записи. Сохраняйте все новые QA и исследовательские результаты. Новые записи inspect загружает как данные; replay требует соответствующий wheel/binding. Для нового PATCH002 используйте wheel0.4.15, для старого PATCH001 — сохранённый0.4.14. При mismatching binding ожидается KERNEL_BINDING_UNAVAILABLE/REJECTED_PROVENANCE.

После rollback проверьте через настоящий MCP service_health, bridge_system_status,102 tools/list records, SQLite integrity и chain prefixes. Первый автоматический rollback фактически проверен: старые drop-in и pointer восстановлены byte-exact, старый HTTP возобновился, URL/tunnel сохранены. После исправления режима0644→0600 preflight load_private выполняется **до** остановки старого HTTP; защитное правило сервера не менялось.

Для аварийного восстановления данных сначала отдельно архивируйте текущее состояние и сверяйте inventories/append-only delta; этот план не разрешает удаление новых журналов или подмену математической истории. Стандартный code rollback не требует data restore.
