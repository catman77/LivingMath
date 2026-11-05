# Запуск, обновление и откат установленного MCP

Установлен `whitestar001-20261105T032516Z`, release `v0.3.0-developer-preview`. Manifest: `a495e5265bca6885fbd7e01891516cb26c3ce75e0ed120f810fdf4ebd8be403d`. Использован тот же SDK1.30.0; отдельное окружение сохраняет прежние библиотеки и добавляет NumPy2.3.5/pandas2.2.3. Старое окружение и старый release layer сохранены.

## Установленный запуск

Рабочий HTTP контролирует user systemd:

```bash
systemctl --user restart livingmath-http.service
systemctl --user is-active livingmath-http.service
```

Эквивалентный foreground запуск (после остановки HTTP во избежание занятого18765):

```bash
task_state="$HOME/.local/state/livingmath/whitestar-mcp-001"
deployment="$task_state/deployments/whitestar001-20261105T032516Z"
"$task_state/production-venv/bin/python" -B "$deployment/layer/release_v01_entry.py" --config "$deployment/release.json"
```

Конфигурация0600 содержит существующие legacy approvals/DB paths+inodes, owner authorization для точного нового manifest, white_star.enabled=true, прежний semantic proposer, R3=PENDING и0 внешних human reports. Пароли, SQLite и конфиги в ZIP не включены.

## Порядок следующего обновления

1. В отдельном layer установите исходники; выполните `white-star prepare` до запроса. Сверьте75 исходных SHA и frozen assurance hashes. Не компилируйте из обработчика.
2. Соберите новый release manifest, точное owner authorization и0600 config по существующему release entry. Используйте прежние DB paths/inodes и URL; не заменяйте действующие базы.
3. Пройдите локальные тесты и реальный HTTPS/OAuth smoke на копиях данных. Зафиксируйте64 прежние input schemas и8 новых, outputSchema/error contracts.
4. Сделайте BackupAPI-копии4 SQLite и всех Workspace файлов; перед переключением остановите только HTTP и снимите quiescent backup. Добавляйте только новые QA-проекты.
5. Переключите `zz-release-v01.conf` на проверенный layer/config, выполните daemon-reload и start HTTP. Проверьте tools/list/tools/call, источник, replay, все прежние строки/истории/hash-prefix и файлы.

## Точный откат к v0.2

```bash
task_state="$HOME/.local/state/livingmath/whitestar-mcp-001"
cp "$task_state/backup-cutover/drop-in.conf" "$HOME/.config/systemd/user/livingmath-http.service.d/zz-release-v01.conf"
cp "$task_state/OLD_INSTALL.private.json" "$HOME/.local/state/livingmath/release-v01/production-install.private.json"
systemctl --user daemon-reload
systemctl --user restart livingmath-http.service
systemctl --user is-active livingmath-http.service
```

SQLite и Workspace не откатываются: вся новая история сохраняется; старый сервер не интерпретирует White Star journals. Резервные копии используются для проверки/аварийного восстановления только после отдельного решения, не автоматически поверх живых баз.

**Не перезапускайте `livingmath-https.service` ради обновления HTTP.** Действующий quick-tunnel адрес сохранён вместе с tunnel PID1801300. Перезапуск самого туннеля или компьютера может изменить временный URL.

Фактически проверено: rollback v0.3/72 →v0.2/64 →v0.3/72 на этом хосте через временный HTTPS/OAuth endpoint с копиями баз; production обновлён и проверен отдельно на прежнем URL. Обратное переключение самого production ради демонстрации не выполнялось. Аварийное завершение staging посреди реального запроса отдельно подтвердило RUNNING→INTERRUPTED и сохранность completed. Доказательства — mcp/staging/restart/ и rollback-test/ приватной поставки.
