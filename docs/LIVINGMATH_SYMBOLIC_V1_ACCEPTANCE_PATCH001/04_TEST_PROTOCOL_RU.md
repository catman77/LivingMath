# Протокол независимой регрессионной проверки PATCH-001

## Контроль 1. Три разных отношения

`SSPP`, `SPSP`, `PPSS`: literal equality false; `SSPP` vs `PPSS` alpha=true (local first-occurrence canonicalization), `SSPP` vs `SPSP` alpha=false; все имеют `q=0` и empty normal form. Exact certificates должны иметь оригинальные слова и трассы.

## Контроль 2. Порядок и состав

`a=SSPP`, `b=SPSP`, `c=SPPS`, `d=PSSP`. Проверить `ab != ba`, `cd != dc` буквально, но reduction-to-empty всех композиций. `history_identity=word` и `provenance` ведут себя по-разному; режим provenance не теряет разные paths.

## Контроль 3. Глобальное переименование

`ABBA\nBAAB\nABAB` vs `XYYX\nYXXY\nXYXY`: alpha/композиционные отношения сохраняются (при Free algebra, без лексической семантики); literal token names различны. Сводные метрики могут совпасть, однако проверить exact relation witnesses, а не только числа.

## Контроль 4. Перестановка

`ABAB\nBABA\nABBA\nBAAB` vs `ABBA\nBAAB\nABAB\nBABA`: при record_boundaries=lines и global identity порядок записей должен быть различим через `composition`.

## Контроль 5. Фиксированный слепой набор палиндромности

Training (только длина 4): positives `ABBA BAAB AAAA BBBB`, negatives `AABB BBAA ABAB BABA`. **Оценка на отдельных длинных тестах; эталонное правило известно лишь внешнему harness**. Длина 6/8:

| Слово | Истина | Старый прогноз |
|---|---:|---:|
| ABCCBA | 1 | 1 |
| ABCBCA | 0 | 1 |
| ABCABC | 0 | 0 |
| ABBAABBA | 1 | 1 |
| AABBAA | 1 | 1 |
| ABABBA | 0 | 1 |
| BAABAB | 0 | 1 |
| AAAAAA | 1 | 1 |
| ABABAB | 0 | 0 |

Уникальный heldout — 9 слов, результат старой модели 6/9. В первоначальном живом запросе `ABCCBA` продублировано: исходные 7/10. Нельзя засчитывать оба как независимые. Если генерализованная грамматика не определяется однозначно из данных, система должна вернуть `UNDERDETERMINED` + конкурирующие гипотезы и различающие запросы.

## Контроль 6. Изоляция

Train фиксирован. Меняем predict-набор на непересекающиеся слова. `hypothesis_digest` должен быть один и тот же (при одинаковых seed и остальных параметрах). Никакого доступа к sealed labels при выборе правил.

## Контроль 7. Replay

Два одинаковых запуска с разными request_key возвращают совпадающие result_digest. Экспортировать bundle, вызвать symbolic_replay, требовать `REPLAY_MATCH`, `journal_hash_chain=PASS`, `structural_recomputed=true`.

## Контроль 8. Source integrity и unicode

Неверный sha256 => `SOURCE_MISMATCH` c path `/source/sha256`. Кириллица через whitespace/lines, NFC. Byte offsets должны ссылаться на валидные границы UTF-8; неверные offsets отклонять (где применимо). Никаких arbitrary code execution, LLM calls, network worker.

## Контроль 9. Литературная интеграция

Фрагменты Малларме, источник с фиксированным sha256 `fa7e64241104d5b195e9542f568a329937d11eb6a590f3af12870db63172c91a`. Сохранить границы строк. Проверить, что строковая перестановка различима, а чистое переименование без изменения структуры — не подделывает новую грамматику. Это проверка символики, не литературной истины.

## Контроль 10. Регрессия режима Белой звезды

`white_star_status`: READY; profiles `base_v1`, `cj_v1`; old run `3004eb38670117d5a452b1a6afa439e009e3e2db72b6a980fb24e45a7c1f4f70` читается неизменно. Изолированные historical records read-only.

## Выпускной порог

- AC01–AC13 зелёные; AC14 закрыть улучшенным доказуемо выразительным механизмом *или* честной диагностикой underdetermination + active probe, подтверждённой контрольной оценкой;
- никаких ложно заявленных theorem-level гарантий, никаких silent fallbacks;
- replay exact, performance bounded, старые интерфейсы не сломаны;
- отчёты, хэши, версии и команды доступны независимому оператору.
