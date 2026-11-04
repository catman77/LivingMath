# v0.1 assurance CLI

For the independent finite assurance package use [README_QUICKSTART_RU.md](../README_QUICKSTART_RU.md). The following installation instructions cover the retained legacy system.

# Установка SUTI–Bridge–LivingMath

## Поддерживаемое окружение

Проверяемая конфигурация: Linux x86_64, Python 3.13; lock-файл также подготовлен
для Python 3.12. Объединённый HTTP-сервер использует Linux Landlock и `resource`.
На Windows/macOS используйте Linux VM. Не отключайте изоляцию ради запуска.
Для установки нужны Git, Python с модулем `venv`, интернет и свободный локальный порт.

Репозиторий может требовать авторизации GitHub: используйте свою штатную
авторизацию Git, не вставляйте токен в URL клонирования.

## 1. Зависимости

```bash
git clone https://github.com/catman77/LivingMath.git
cd LivingMath/live_math_mcp_prod
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes -r requirements-019.lock
```

Нет отдельной сборки, npm или платного inference API. `requirements-019.lock`
фиксирует зависимости runtime и pytest с хешами. Дополнительные средства
разработки описаны в [TESTING.md](TESTING.md).

## 2. Новый приватный экземпляр

```bash
python -m unified_system.local prepare --instance development --port 18766
```

Команда использует существующие миграции и TLS/OAuth-механизм. Она создаёт
отдельные новые SQLite ledger/typed/DAV/OAuth хранилища, копирует проверенные
публичные assets и один раз загружает словарь `o200k_base` через tiktoken.
Работающий сервер и его базы не читаются и не обновляются.

Данные и конфигурация: `~/.local/state/livingmath/checkouts/development/`.
Конфигурация `data-config.json` содержит пути, не значения секретов;
`data/tls/owner-password` содержит пароль владельца. Каталоги приватные,
секретные файлы доступны только владельцу. Не копируйте этот каталог в Git.

Повторная `prepare` с тем же именем отклоняется, сохраняя данные. При неудачной
подготовке частичный каталог остаётся для диагностики; для повторной проверки
выберите другое имя. `--port 0` выбирает свободный порт и записывает его в конфиг.
Установщик не является командой миграции существующей production-базы.

## 3. Запуск и реальная проверка MCP

```bash
python -m unified_system.local serve --instance development
```

В другом терминале из `live_math_mcp_prod`, активировав то же окружение:

```bash
python -m unified_system.local smoke --instance development
```

Ожидается `status=PASS`, `tool_count=44`, `transport=REAL_HTTPS_OAUTH`.
Клиент выполняет OAuth/PKCE, MCP initialize, tools/list и три read-only вызова.
Проверка не запускает LLM и не выводит токены/пароль. Для остановки сервера — Ctrl+C;
повторный `serve` использует те же базы. Первоначальный сертификат localhost
действует два дня: это сертификат локального эксперимента, не постоянного домена.

Без LLM backend доступны Bridge, ledger и конечные проверки. Для произвольного
текста модельная формализация требует следующего шага; успешная проверка MCP
сама по себе не подтверждает качество интерпретаций.

## 4. Формализация через существующий Codex backend

Установите Codex CLI по [официальной инструкции OpenAI](https://learn.chatgpt.com/docs/cli)
и выполните от имени владельца сервера:

```bash
codex login
codex login status
python -m unified_system.local serve --instance development --with-codex
```

Используйте вход через ChatGPT. Codex поддерживает подписочный вход отдельно
от API-ключа; это описано в [официальной документации по авторизации](https://learn.chatgpt.com/docs/auth).
LivingMath использует существующую локальную сессию и не требует `OPENAI_API_KEY`.
Доступность модели и ограничения определяются вашим аккаунтом. По умолчанию
backend использует `gpt-6.1-sol`; владелец может явно задать `--model`.

Backend запускается отдельным процессом до ограничения чтения HTTP-сервера.
Текст передаётся модели для аннотации; не отправляйте туда материалы, которые
нельзя передавать выбранному провайдеру. Receipts остаются в приватном
`inference-spool/`. Если `codex` отсутствует или модель не отвечает, причина
сохраняется; система не выдумывает успешный ответ.

## 5. Подключение из ChatGPT

ChatGPT должен достигать вашего `/mcp` по доверенному публичному HTTPS URL.
`https://localhost:18766/mcp` доступен только локальному клиенту.
Предоставьте домен или HTTPS-туннель к локальному listener. При использовании
внешнего TLS-прокси его upstream — `https://localhost:18766`; локальный
сертификат нужно явно доверить этому прокси. Прокси должен передавать исходный
`Host`, `Origin`, Authorization и OAuth-маршруты без изменения.

Перезапустите локальный listener с **точным публичным origin без `/mcp`**:

```bash
python -m unified_system.local serve --instance development \
  --origin https://livingmath.example.org --with-codex
```

`livingmath.example.org` — пример, замените его своим действительным адресом.
Публичный issuer должен совпадать с адресом соединения, иначе OAuth или
проверка Origin отклонят запрос. Локальная команда `smoke` предназначена для
предыдущего localhost-этапа, до такого переключения origin.

По [актуальной инструкции OpenAI](https://developers.openai.com/api/docs/guides/custom-mcp-server):
в ChatGPT откройте Plugins → плюс → Add custom MCP server, укажите
`https://ваш-домен/mcp`, выберите OAuth и создайте подключение. Для нашего
сервера используется динамическая регистрация клиента; собственные client ID/secret
не требуются. На странице LivingMath введите приватный пароль владельца.
Доступность подключения зависит от разрешений аккаунта/workspace.

Первый запрос в чате: «Вызови bridge_system_status и покажи версию и возможности».
После изменения набора инструментов обновите подключение; при смене домена
туннеля измените URL или создайте подключение заново. URL работающей установки
в исходниках не зашит. Эта инструкция не меняет уже подключённый production.

## 6. Обновление и резервные копии

Перед изменением существующих данных сделайте согласованные SQLite BackupAPI
копии всех четырёх хранилищ и проверьте цепочки. Не копируйте открытый `.sqlite3`
без WAL/BackupAPI. Для ledger доступна команда:

```bash
python admin.py --db /absolute/private/research.sqlite3 backup /absolute/backups/research.sqlite3
```

Для первого знакомства безопаснее создать другое имя экземпляра и проверить
новый checkout отдельно. Production promotion и восстановление существующих
данных — отдельные операторские процедуры; `prepare` их не подменяет.
