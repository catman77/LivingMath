# Acceptance Matrix — SEMANTIC-BRIDGE-001

Каждая строка — отдельный воспроизводимый тест. Не подменять проверку source, assurance или structural equality интерпретационным одобрением LLM.

| ID | Вход/ситуация | Ожидаемый исход | Уровень |
|---|---|---|---|
| S01 | Пин редакции Блока; SHA совпадает | ACCEPT_SOURCE | source |
| S02 | Пин обеих редакций Пушкина | ACCEPT_SOURCE | source |
| S03 | Ровно исходный UTF-8 с длинным тире/ё | SHA и byte-span равны | source |
| S04 | SourceAnchor на 1 байт сдвинут | SOURCE_ANCHOR_MISMATCH | source |
| S05 | Цитата из другой редакции | REJECTED / явно новый snapshot | source |
| S06 | Источниковое утверждение с верной цитатой | SOURCE_ATTESTED | assurance |
| S07 | Противоположная выдуманная строка | REJECTED | assurance |
| S08 | LLM ссылается на несуществующий source ref | REJECTED | binder |
| S09 | Модель присылает fake source sha | REJECTED, trusted sha не меняется | binder |
| S10 | Нет прав на встраивание source bytes | экспорт не включает байты | rights |
| S11 | Не вложен зависимый источник | replay MISSING_SOURCE_DEPENDENCY | offline |
| I01 | Первое чтение Блока | typed initial frame + raw receipt | model |
| I02 | Второе чтение Блока | revised frame + parent edge | model |
| I03 | Первое/второе чтения «Анчара» | 2 frames + parent edge | model |
| I04 | Первое/второе чтения «Я вас любил» | 2 frames + parent edge | model |
| I05 | Наличие альтернативы к каждому тексту | 3 явных альтернативы | epistemic |
| I06 | Свободная трактовка «абсолютно тот же мир» | UNKNOWN/HOLD, без PROVED | epistemic |
| I07 | «Анчар» как реальная физическая токсикология | UNKNOWN/HOLD, нет научного VERIFIED | epistemic |
| I08 | Литературная модель переписана задним числом | DENY/immutable lineage | lineage |
| I09 | Несуществующий родитель/цикл в lineage | REJECTED | lineage |
| I10 | Отсутствует model backend | MODEL_UNAVAILABLE, manual не засчитывать | model |
| L01 | Равный `image_set`, разный порядок у Блока | LOSS_DETECTED + q witness | structural |
| L02 | Заявлено PRESERVED для той же проекции | REJECTED false preservation | structural |
| L03 | Полная relevant проекция, одинаковые записи | нет ложного LOSS | structural |
| L04 | Q не задано или не исчерпано | UNDETERMINED/NOT_CHECKED | structural |
| L05 | Различие слов → утверждение о различии мира | HYPOTHESIZED/UNKNOWN, не CERTIFIED | epistemic |
| R01 | Полный приватный ZIP + direct replay | PASS | offline |
| R02 | Тот же ZIP + compiled replay | PASS, digest тот же | offline |
| R03 | Подмена одного frame/source/edge byte | MANIFEST/OBJECT_DIGEST_MISMATCH | integrity |
| R04 | Изменение только model metadata | прежний assurance verdict/witness digest | reproducibility |
| R05 | Исторический ложный ENTAILED 23/24 | REJECTED, 2 контрмодели | regression |
| R06 | Наличие OAuth/API secrets внутри ZIP | FAIL BUILD / NO RELEASE | security |
| R07 | Попытка execution grant/PROVED_FORMAL | REJECTED | policy |
| R08 | Параллельные ревизии и request key reuse | idempotent либо явный CONFLICT | ledger |
| R09 | Старые 55 MCP tools и frozen hashes | unchanged в QA; no stealth deployment | regression |
| R10 | Нет двух внешних human reports | R3=PENDING | release |

**Go:** S01–S11, I01–I10, L01–L05, R01–R10 соответствуют фактическому объёму. Невыполнение I01–I04 из-за backend availability даёт `BLOCKED_MODEL_UNAVAILABLE`, но детерминированная часть может быть доставлена как `PARTIAL`, не как успешные 6 чтений. Дополнительные метрики не заменяют обязательные gates.
