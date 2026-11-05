# Происхождение внешних материалов

## automata-lib

`live_math_mcp_prod/external019/` содержит зафиксированные материалы automata-lib
9.2.0, commit `04dc1947315f322825991b5dc637604567703c9c`.
Автор Caleb Evans, лицензия MIT. Полный текст лицензии сохранён в
[external019/LICENSE.txt](live_math_mcp_prod/external019/LICENSE.txt),
адреса и SHA исходных файлов — в
[registration.json](live_math_mcp_prod/external019/registration.json).

## SUTI и ALCH

`assets/unified/bridge.json` содержит выбранные исходные схемы/адреса из рабочих
архивов SUTI, предоставленных пользователем со слов автора. Хеши исходных
архивов и отдельных members сохранены в bundle. Полные рабочие архивы в Git
не включены. Это исследовательское использование предоставленных материалов;
LivingMath не объявляет себя официальным SUTI runtime или согласованной автором
редакцией проекта. Новая лицензия исходным SUTI материалам здесь не присваивается.

`assets/unified/alch006.json` — сохранённая публичная исследовательская модель
ALCH006 с собственным source/provenance, неизвестными свойствами и условными
выводами. Она не заменяет исторический первоисточник или физический эксперимент.

## Исходники015

`live_math_mcp_prod/testdata/xi015_source/` содержит четыре точных файла из
предоставленного `RH_XI_ROUTES_EXPORT_001.zip`, нужных существующим015/016 тестам.
Исходный SHA архива и SHA файлов находятся в `manifest.json`; определения
не заменены синтетической реализацией.

## Зависимости Python

Устанавливаются отдельно из `requirements-019.lock` и сохраняют свои лицензии.
Словарь `o200k_base` получает установленный tiktoken при подготовке экземпляра;
личные credentials для этого не используются. В Git нет окружения Python
или закрытых ключей. Общая новая open-source лицензия всему проекту этим
публикационным коммитом не назначается.

## Пилот ROBLOX-PRED-001

`docs/ROBLOX_PRED_001_STARTER.zip` и извлечённые два Markdown-файла предоставлены
пользователем как задание; оригинальные bytes и SHA сохранены. Пилот использует
отдельный `roblox-pred-001/requirements-test.lock`. Сырые Roblox responses и
соседние исходники SOMA не включены: опубликованы только аудиторские метаданные,
ссылки и хеши. Публичная доступность API не объявлена лицензией на ML-использование;
текущая source policy блокирует дальнейший сбор. Синтетические fixtures явно
отделены от Roblox-данных.

## White Star MCP001 supplied source

The repository owner supplied `LevinMAS_WhiteStar.zip` (SHA256 `c41df9a56a1c1879b790c932714bd2dbd44d2f70d88dea8671279892cc3576b3`). Its75 code files are preserved byte-for-byte under `src/lm_suti_assurance/white_star/vendor/code/`; the complete original request/archive is retained in docs. Upstream manifests and historical001/002/003 results retain their original provenance. New integration wrappers, MCP receipts and QA results are identified separately in docs/white-star. This integration does not claim execution of a native SUTI runtime or convert declared source rights into legal certification.
