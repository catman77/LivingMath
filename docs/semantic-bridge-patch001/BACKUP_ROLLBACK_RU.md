# Backup и rollback Semantic Bridge PATCH001

Перед реализацией сохранён полный архив106566 исходных Workspace файлов и4 SQLite online backups; до cutover делается дополнительный snapshot при остановленном HTTP и delta-overlay Workspace. Сохраняются inode/path существующих баз и все исходные bytes/journal prefixes. Старый manifest/config/production pointer/drop-in сохраняются приватно. Базы в публичный ZIP не входят.

При откате кода восстановить HTTP drop-in из backup-cutover/drop-in.conf и production pointer из backup-cutover/production-install-before.private.json. Выполнить systemctl --user daemon-reload и restart livingmath-http.service. Не перезапускать livingmath-https.service: сохранится существующий адрес/процесс туннеля. Старый deployment udav-core001-20261108T170545Z использует неизменённые старые модули.

Не заменять базу и не удалять новые semantic_bridge.start/finish записи при rollback кода. Они append-only; старые методы их не интерпретируют. Восстановление данных — отдельная операция только при действительной порче; для точного состояния cutover нужны base ZIP +delta-overlay и4 quiescent SQLite. Приватный операторский каталог: /home/catman/.local/state/livingmath/semantic-bridge-patch001.
