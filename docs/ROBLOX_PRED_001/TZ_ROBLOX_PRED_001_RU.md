# ROBLOX-PRED-001 — Техническое задание

**Версия:** 1.0  
**Дата:** 2026-11-01  
**Статус:** к реализации, исследовательский пилот  
**Цель:** воспроизводимо оценить предсказательную ценность классического ML, смыслово-структурной системы SOMA/DAVE/SUTI (включая потенциальный LevinMass/SRT) и их гибрида на Roblox.

## 0. Принципы и запреты

1. Результат `структурная модель не дала преимущества` — полноценный результат. Запрещены изменения тестовой выборки/метрик по итогам просмотра результатов без отдельной маркировки **exploratory**.
2. Никаких утверждений о денежной выручке на основании visits, CCU, favorites или других прокси. До получения верифицируемой выручки целевой показатель — устойчивое внимание аудитории, а не прибыль.
3. Никаких фиктивных исторических snapshots, восстановления исторического текста из текущего описания или обучения на данных, сформированных после точки прогноза.
4. Никакого самостоятельного нового DSL «вместо» SOMA/DAVE/SUTI. Семантический интерфейс адаптерный, фактические операции системы устанавливаются инспекцией MCP/документации. Новые эвристики — только отдельные явно обозначенные baselines.
5. Никакого неограниченного scraping, обхода аутентификации, CAPTCHA, ограничений API или условий сервисов. Соблюдать лицензии и права на коммерческое использование каждого источника.
6. **Задача пилота — не доказать заранее выбранную теорию, а получить информативное, воспроизводимое столкновение с действительностью.**

## 1. Исследовательские вопросы

- RQ1: можно ли по признакам, доступным в момент `t0`, предсказать устойчивый интерес к Roblox-игре на горизонте 90 дней?
- RQ2: что дают структурно-смысловые признаки сверх обычных метаданных, жанра, создателя и текстовых embeddings?
- RQ3: переносится ли выигрыш между жанрами, создателями и календарными периодами?
- RQ4: каков характер ошибок: информационная недостаточность, недостаток выразительности представления, ошибка сопоставления структуры с целевой метрикой, смена режима рынка, смещение выборки?
- RQ5: возможна ли экономическая ценность ранжирования проектов при реалистичных издержках на разработку и дополнительных данных, **без выдуманной ROI**?

## 2. Сценарии предсказания (не смешивать)

- **P0 / idea-stage:** признаки, существующие до публичного выпуска игры: описание концепции, механики, план экономики и социальной игры, данные студии, известные к этому моменту. При отсутствии реальных до-релизных артефактов **P0 не оценивается исторически**. Для новых предложенных идей — только перспективный протокол.
- **P7:** информация не позднее конца седьмого дня после доступного подтверждённого релиза; история показателей до t0 включительно.
- **P30:** аналогично конец дня 30.
- **Pfirst:** опциональная прагматическая задача — первый зафиксированный снимок при наличии информации о его смещении относительно даты релиза. **Не называть Pfirst прогнозом P0/P7.**

Для каждого примера обязательны `universe_id`, `creator_id`, `release_date` (или `unknown`), `as_of`, `horizon_end`, `source_provenance`, `data_available_at`, `source_license`. Если точность даты неизвестна, сохранять степень неопределённости и не допускать запись в строгие P7/P30.

## 3. Outcome и знаменатель

**Primary outcome (если есть ежедневная история):** средний дневной `concurrent_players` за дни 61–90 после `t0` либо другой заранее зафиксированный, реально измеряемый, устойчивый показатель аудитории. Для t0 P7/P30 целевой интервал строго после t0; день отсчёта определяется в UTC и сохраняется.

Метка `success=1`: проект попадает в верхние 10% по primary outcome **среди заранее определённой eligible cohort** с общим периодом старта/наблюдения. Порог выбирается **только по обучающей части** каждой оценки; оценка test делается на неизменённом train-defined пороге. Если ежедневного CCU нет, зарегистрировать fallback (`daily visits deltas`, подтверждённый иной показатель), но не смешивать его с CCU и не использовать накопленные visits как ежедневные посещения.

Eligible cohort определяется до обучения: период выхода/входа, документированная схема отбора, минимальная история, достаточный последующий горизонт; учитывать left truncation, right censoring, исчезнувшие и закрытые игры. Удаление неуспешных/исчезнувших проектов без явного анализа недопустимо. Не делаем выводов о всей экосистеме Roblox, если видим лишь top charts.

**Secondary outcomes:** прирост аудитории, удержание высоких позиций во времени, непрерывные log1p-метрики, и (только при правомерно полученном доступе) verified revenue, D1/D7 retention. Прокси никогда не переименовывать в revenue.

## 4. Аудит источников данных — обязательный Stage 0

В начале построить реестр источников: официальные публичные Roblox endpoints, официальные авторизованные Open Cloud endpoints, лицензируемые провайдеры исторических снимков, доступные CSV/публичные архивы. Для каждого источника указать:

`name | URL | public/auth | coverage | first_known_date | cadence | historical_time_travel | sampling_frame | license | commercial_allowed | rate_limits | verified_test_result | decision`.

Особенности:
- Roblox Creator Analytics / Analytics Query API и Benchmarks API требуют разрешений на конкретный universe; не использовать как публичную статистику всех игр.
- Не доверять заявлениям агрегаторов, пока не проверены реальные даты срезов, полнота выборки, права и воспроизводимость.
- Если коммерческое применение данных запрещено или неизвестно, маркировать их research-only / pending-legal; продуктовые функции на таких данных не строить.
- Требуется отрицательная выборка. Top-only источники допустимы лишь для biased diagnostic, а не для оценки общего вероятностного риска.
- Не собирать персональные данные игроков; только необходимая агрегированная статистика и публичные свойства игр.

**Датасет пригоден для строгого ретроспективного бенчмарка, только если** реально подтверждены исторические признаки до t0, устойчиво измеряемые цели после t0, документированный sampling frame и достаточное число отрицательных примеров. Размер 3–5 тыс. — ориентир, НЕ формальное требование и НЕ повод синтезировать «реальные» данные.

**Если данных нет:** немедленно создать протокол перспективного наблюдения новых игр с ежедневным журналом и запустить непрерывный сбор. При этом Stage 1 baseline делать только на допустимой исторической подвыборке и честно маркировать ограничения. Не объявлять полноценную валидацию.

## 5. Хранилище / схема

Рекомендуемый стек: Python 3.11+, uv/pip, DuckDB + Parquet, pandas/polars, scikit-learn, CatBoost, sentence-transformers (опционально), pytest. Никакого тяжёлого сервера и GPU как обязательного условия.

Таблицы:
- `games`: universe_id, creator_id, creation/release dates (с evidence), жанр, основные неизменяемые идентификаторы.
- `snapshots`: universe_id, observed_at, ingested_at, source, title, description, thumbnail_ref, visits_total, current_players, favorites, likes/dislikes (при наличии), status. Поля могут быть NULL; источник каждого snapshot обязателен.
- `concept_artifacts`: только реально датированные концепции, документы, картинки, игровые механики; ссылка на исходник и known_at.
- `outcomes`: universe_id, t0, outcome_window, raw_measure, success, eligibility_flags, censoring_flags, provenance.
- `semantic_features`: sample_id, extractor_version, mcp_version, feature_schema, relations/evidence, quality_flags, known_at.
- `predictions`: experiment_id, model_id, fold, sample_id, score, calibrated_probability, as_of.
- `runs`: git commit, config hash, random seed, dataset manifest hash, model version, timings.

**Temporal contract:** every feature has `known_at <= as_of`. Text is versioned. Если нынешняя страница показывает старые даты создания, это НЕ означает, что нынешнее содержание было известно тогда. Screenshots/thumbnail меняются: тот же запрет.

## 6. Модели

**M0 — sanity:** random-score benchmark; base-rate; простая логистическая регрессия по разрешённым признакам.

**M1 — tabular:** CatBoost с жанром, возрастом, creator history *только до t0*, разрешённой историей активности и метаданными. Missingness как отдельная информация.

**M2 — text:** TF-IDF + linear classifier и/или небольшой pretrained text embedding + CatBoost/logreg. Предобучение в общем корпусе допустимо, но если оно использует сведения об игре после t0, это должно быть обнаружено/задокументировано; на строгом historical benchmark при сомнении убрать такие признаки.

**S1 — SOMA/DAVE/SUTI native:** операции определить через capability discovery; вход — те же as-of концептуальные материалы, выход — структурные отношения, ограничения, маршруты/связи и uncertainty по фактически доступной схеме. Если реальная реализация не поддерживает задачу — возвращать `unsupported`, а не подменять её искусственным extractor.

**H1 — hybrid:** M1/M2 + фактические признаки S1. Обучение одинаковой сложности с контрольными ограничениями, один train/val/test.

**Negative controls:** переставленные по sample-id structural features внутри train (test permutation по зафиксированному правилу), случайные признаки той же размерности; ablation по группам отношений. Извлечение признаков не должно читать outcome, label и будущую историю. Отдельно зафиксировать расход токенов и вычислительного времени.

Предусмотреть, но не требовать для пилота, SRT/LevinMass interval prediction: если формализм даёт множество согласованных вероятностных моделей `Q(d)`, оценка события `E`: `P_low = inf_{Q in Q(d)} Q(E)`, `P_high = sup_{Q in Q(d)} Q(E)`; отсутствие работающего отображения от структуры к исходам → `unsupported/not_identified`, а не выдуманные интервалы. Численные вероятности требуют отдельной проверки калибровки.

## 7. Экспериментальный протокол

1. До испытания зафиксировать `protocol.yaml`: базовый outcome, eligible cohort, horizon, temporal embargo, train/validation/test временные интервалы, random seeds, минимальный размер test, допустимые гиперпараметры, критерии качества.
2. Хронологическое деление: train ранее validation ранее test. Embargo по максимальному horizon; группы по creator/клонам; оценить отдельный creator-disjoint и genre-shift holdout, если хватает данных. Не смешивать leakage с evaluation.
3. Порог top-decile строится на train; calibrator обучается только validation или out-of-fold train; test недоступен на этапе настройки.
4. Оценка: Precision@10% и Lift@10% над эмпирической базовой частотой на test; PR-AUC, ROC-AUC (secondary), log loss, Brier, калибровка, доверительные интервалы bootstrap с кластеризацией по creator, при необходимости time blocks.
5. Для сравнений M2 vs H1: paired bootstrap по тем же объектам, размер эффекта и 95% CI. Заранее обозначить primary comparison; множественные exploratory comparisons отдельно.
6. Анализ устойчивости на жанрах, календарных режимах, малых/больших создателях и датасетах разных поставщиков. Не объявлять «универсальность» без transfer holdout.
7. Экономическая оценка — только сценарная: модель выбора top-k проектов при заданных стоимости прототипа и бюджетах, sensitivity analysis; реальный доход не заявлять.
8. Если данных недостаточно — результат `INCONCLUSIVE`, не `NEGATIVE` и не `POSITIVE`.

## 8. RCA и научная интерпретация

Если S1/H1 не улучшает baseline, обязательно классифицировать причины через проверяемые контроли:
- покрытие концептуальных входов (нет ранних описаний);
- нестабильность/неполнота структурного extractor;
- отсутствие новых признаков (correlation/conditional permutation);
- неверная трансляция смысловой структуры в измеримые features;
- ошибка связки structure → observed behavior;
- sampling/censoring/leakage;
- распределительный сдвиг;
- объективно непредсказуемая компонента результата;
- статистическая неопределённость/слишком мало наблюдений.

Критически: нельзя автоматически считать проигрыш всей теории опровержением смысла или выигрыш доказательством правильности её онтологии. Вывод относится к конкретному предиктору, данным и protocol.

## 9. Этапы с остановками

**Stage 0 — Data feasibility, первый исполняемый шаг**
- Проверить источники, лицензии, анонимный доступ, охват, snapshots, отрицательные примеры.
- Построить `DATA_AUDIT_RU.md`, data dictionary, минимальную выборку реальных объектов и диаграмму доступности time travel.
- Решение: `GO_RETROSPECTIVE`, `GO_PROSPECTIVE`, `GO_BOTH`, `BLOCKED` с причинами.

**Stage 1 — минимальный воспроизводимый baseline**
- Реальный dataset manifest + temporal validation + M0/M1; один короткий smoke-test (<5 мин на небольшой локальной подвыборке, не обещать для любого железа).
- Если нет легитимных данных для строгого прогноза — инфраструктура и тесты, но не фальшивые accuracy.

**Stage 2 — текстовый baseline и capability audit**
- M2; проверить MCP инструменты, собрать `SUTI_CAPABILITY_REPORT_RU.md`; интерфейс, fixtures и ошибки.

**Stage 3 — native S1 + hybrid H1**
- Только после capabilities; inference budget; абляции, negative controls.

**Stage 4 — независимая оценка и коммерческое решение**
- Запечатанный test; метрики, CI, RCA, scenario-based economics, `GO/NO-GO`.

Не создавать месячную инфраструктуру до Stage 0. Ограничить Stage 0 сетевые обращения и время по конфигу; при исчерпании — отчёт с блокерами. Любой сбор с правовыми ограничениями требует явного решения пользователя.

## 10. Репозиторий и поставка

```text
roblox-pred-001/
  README_RU.md
  pyproject.toml
  .env.example
  configs/protocol.yaml
  docs/DATA_AUDIT_RU.md
  docs/DATA_DICTIONARY_RU.md
  docs/SUTI_CAPABILITY_REPORT_RU.md
  docs/RCA_RU.md
  src/roblox_pred/{sources,storage,features,semantic,models,evaluation,reporting}/
  tests/{test_temporal_leakage.py,test_splits.py,test_metrics.py,test_semantic_adapter.py}
  scripts/{audit_sources.py,collect_snapshots.py,build_dataset.py,run_baseline.py,run_semantic.py,run_eval.py}
  reports/
  data/{raw,processed}/  # excluded from git
```

CLI contract:

```bash
python scripts/audit_sources.py --config configs/protocol.yaml
python scripts/build_dataset.py --config configs/protocol.yaml
python scripts/run_baseline.py --config configs/protocol.yaml --smoke
python scripts/run_semantic.py --config configs/protocol.yaml --dry-run
python scripts/run_eval.py --config configs/protocol.yaml
pytest -q
```

Commands must either run with genuine supplied data or exit nonzero with intelligible diagnostics; `--smoke` may use clearly tagged **synthetic fixtures solely to test plumbing**, never as evidence of predictive performance.

## 11. Acceptance criteria

- [ ] Stage 0 завершён и задокументирован реальными проверками источников.
- [ ] Подписаны все временные ограничения, нет future leakage.
- [ ] Нет утверждений о доходах из просмотров/visits.
- [ ] Есть воспроизводимый baseline и корректный baseline при отсутствии данных.
- [ ] Есть тесты, намеренно подсунутые future-only признаки отбрасываются.
- [ ] SUTI adapter не маскирует заглушку под реальную систему.
- [ ] Отчёт сравнивает модели на одинаковых тестовых объектах; нет post-hoc побед.
- [ ] При недоступности данных/инструментов дан конкретный список препятствий и ближайший минимальный эксперимент.

## 12. Источники для проверки Codex

- Roblox Discovery (сигналы рекомендаций, не исходы нашего прогноза): https://create.roblox.com/docs/discovery
- Roblox Discovery FAQ: https://create.roblox.com/docs/discovery-faq
- Roblox Analytics / Open Cloud: https://create.roblox.com/docs/cloud/guides/analytics
- Roblox Benchmarks (experimental, access-restricted): https://create.roblox.com/docs/cloud/guides/analytics/benchmarks
- Roblox API reference: https://create.roblox.com/docs/cloud/reference/domains/games

Все ссылки — starting points, не гарантированные API-контракты. Проверить актуальность и правила применения при реализации.
