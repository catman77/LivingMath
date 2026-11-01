# Словарь данных

Все времена timezone-aware, хранятся в UTC. Наивные timestamps отклоняются.
`known_at` — когда конкретная версия стала доступна исследователю;
`source_observed_at` — время исходной фиксации. Creation/update/release — другие
поля; они не заменяют время получения текста. NULL означает неизвестность, 0 —
реально измеренный ноль. Денежных целевых переменных в этой итерации нет.

## Семь таблиц

| Таблица | Основные поля и смысл |
|---|---|
| games | universe/creator ID, creation_date, release_date/precision/evidence, genre, known_at, source/license/provenance |
| snapshots | observed_at/ingested_at, версия title/description, thumbnail_ref, visits_total/current_players/favorites/likes/dislikes, status, source_sha256 |
| concept_artifacts | исходный текст/концепт, universe_id, known_at/source_observed_at, source_sha256, artifact_kind и лицензия |
| outcomes | as_of, окно [start,end), metric, raw_measure, success=NULL до train-defined threshold, eligibility/censoring_flags, provenance |
| semantic_features | sample_id, extractor/schema/MCP версии, relations/features либо NULL, quality_flags, status и known_at |
| predictions | experiment/model/fold/sample IDs, ranking score, calibrated_probability=NULL без отдельной калибровки, as_of |
| runs | experiment ID, Git/config/dataset hashes, seed, model_versions, timings и status |

Каждая запись имеет `record_id`; полная модель сохраняется в `payload_json`,
скалярные поля — также типизированными Arrow/DuckDB колонками. Данные пишутся
неизменяемыми Parquet parts. Точный повтор — no-op; другой payload под прежним ID
отклоняется. DuckDB транзакционен; авария между записью part и COMMIT может оставить
неиндексированный part. Это не распределённая атомарная файловая транзакция.
Пилот рассчитан на одного пишущего оператора; внешнее редактирование файлов вне
его API не предотвращается. Манифест содержит хеши для обнаружения изменений.

## Выборка и признаки

`Sample` связывает universe, creator, известную clone group, as_of, сценарий,
cohort_frame, источник/лицензию, FeatureValue и целевое окно. Каждый FeatureValue
имеет hash версии и два времени. Разрешён фиксированный список признаков;
`final_rank`, будущие visits и произвольные outcome-derived поля не допускаются.

Импорт реализован для Pfirst. P0/P7/P30 — отдельные сценарии: валидатор требует
реальное основание release и точный cutoff; готового импортера для них пока нет.
Создание game в API не удостоверяет запуск проекта. Кластеризация клонов из текста
не реализована: проверяются предоставленные группы и время их доступности.
Неизвестные скрытые клоны остаются ограничением исследования.

## Цель и оценка

Зафиксирована `mean_daily_sampled_current_players_d61_90`: среднее 30 ежедневных
**точечных** наблюдений около 18:00 UTC (±30 минут), дни 61–90 после UTC-даты as_of.
Это не средний дневной CCU. Включительно день 90 заканчивается границей +91 день.
Выбирается первая фиксация за день без просмотра значения; повтор не закрывает
пропущенный день. Недоступный статус, NULL или неполный горизонт дают outcome=NULL.
Даже для закрытой игры ноль автоматически не выдумывается.

Train threshold — linear quantile 0.9, успех при `outcome >= threshold`. При связках
доля успехов может отличаться от 10%; это показывается в отчёте. Precision/Lift@10%
используют ceil(n×0.1), при ties — sample_id. PR-AUC/ROC-AUC без контраста классов
не интерпретируются. Log-loss/Brier не удостоверяют калибровку. Revenue, ROI и
математический статус verified не выводятся.
