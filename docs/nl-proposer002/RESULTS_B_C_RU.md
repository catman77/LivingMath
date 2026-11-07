# Результаты A/B/C/D

Эталон независимый синтетический; человеческая смысловая точность не измерена.

A: source_only. B: реальные численные кадры с positional-token-order encoding.
C: те же реальные кадры и source, но порядок source spans переставлен (control).
D: другой реальный прогон с отражением второй координаты того же encoder.

Всего47 синтетических reference readings; сравнимы40. Семь исключены как
UNKNOWN_BOUND из finite-vector scoring (более10 relation cells при domain size2).
40/40 относится только к40 сравнимым эталонам; это не47/47 и не semantic accuracy.

| Плечо | Источники | Typed | Trace-linked | Abstain | Finite contrast | Synthetic coverage | Non-reference vector matches | Model calls |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 50 | 49 | 0 | 9 | 6 | 40/40 | 1 | 9 |
| B | 50 | 70 | 20 | 9 | 15 | 40/40 | 6 | 9 |
| C | 50 | 63 | 0 | 10 | 14 | 39/40 | 6 | 9 |
| D | 50 | 65 | 17 | 9 | 15 | 40/40 | 7 | 9 |

Совпадение конечных truth vectors не доказывает логическую эквивалентность.
`WHITE_STAR_INCREMENTAL_BENEFIT_NOT_ESTABLISHED`.
`PARTIAL; semantic generalization NOT_EVALUATED; EXTERNAL_ADJUDICATION_NOT_EXECUTED`.

Non-reference vector matches: совпадения с синтетическими контрольными неэталонными чтениями в том же конечном классе; это не человеческая оценка ошибок смысла.
