# Игорю: межфайловые условия двух прежних пар

Дата: 2026-10-29. Ответ автора: **NO_REVIEW**. Работа по USER_SESSION с предоставленными авторскими архивами; это не подпись или согласование автора. Материалы не отправлялись. Ниже четыре полные контрфактические записи по реальным исходным схемам, не реальные действия или учебные данные.

## P1-001

Исходная схема: `SUTI.uni/templates/learning-crystal.v1.schema.json`; SHA256 `8038431a0c13868dfb0427256f5ee9b32929635d5414c7f2db41652036045ba3`. Скалярный наблюдатель `visibility` одинаков, но `transfer_status` различается. Оба полных состояния проходят исходную схему.

### Состояние 0

```json
{
  "schema": "suti.learning-crystal.v1",
  "id": "",
  "title": "",
  "question": "",
  "author": "",
  "audience": "",
  "visibility": "public",
  "maturity": "seed",
  "version": "",
  "claims": [],
  "sources": [],
  "unknowns": [],
  "limitations": [],
  "chosen_next_step": "",
  "rights_and_reuse": "",
  "transfer_status": "HOLD",
  "publication_status": "HOLD"
}
```

### Состояние 1

```json
{
  "schema": "suti.learning-crystal.v1",
  "id": "",
  "title": "",
  "question": "",
  "author": "",
  "audience": "",
  "visibility": "public",
  "maturity": "seed",
  "version": "",
  "claims": [],
  "sources": [],
  "unknowns": [],
  "limitations": [],
  "chosen_next_step": "",
  "rights_and_reuse": "",
  "transfer_status": "transferred-by-explicit-choice",
  "publication_status": "HOLD"
}
```

### Найденное текстовое основание

`SUTI.uni.zip` / `SUTI.uni/README.md`, source SHA256 `0746636236669970d19972645fc1f871beb9d585637f20e075675b4fc0601dec`, UTF-8 bytes `[2386,2606)`, chars `[1377,1495)`:

> Сначала фиксируются источник и права, затем создаётся объяснение для читателя; публикация остаётся отдельным решением.

Это документированное указание, не исполнимое условие JSON Schema. Привязка к точному полю, версии и этапу остаётся UNKNOWN. Новое применимое исполнимое ограничение в измеренном поиске не найдено; это не отсутствие связи во всём SUTI. Старая пара сохранена относительно исходной схемы. Скалярная модель по-прежнему имеет LOST, совместное наблюдение сохраняет выбранные значения.

**Вопрос:** Допускается ли для `suti.learning-crystal.v1` сочетание `visibility=public, transfer_status=HOLD`, или его исключает конкретное правило в рабочих файлах SUTI?

## P1-002

Исходная схема: `SUTI.uni/SUTI.studium/schemas/study-session.v1.schema.json`; SHA256 `fda1ee197c3a740f274b6142aae981b8dc4f59c867ff0e8dfbf49ef3dcbf8b74`. Скалярный наблюдатель `external_transfer` одинаков, но `decision` различается. Оба полных состояния проходят исходную схему.

### Состояние 0

```json
{
  "id": "a",
  "version": 1,
  "status": "example-template",
  "subject": "",
  "setting": "",
  "learning_goal": "",
  "starting_task": "",
  "source": {
    "title": "",
    "url": "",
    "checked_on": "",
    "rights_status": "PASS"
  },
  "practice_step": "",
  "feedback_criterion": "",
  "transfer_task": "",
  "access_options": [],
  "minimum_data_needed": [],
  "data_not_needed": [],
  "permissions_review": "PASS",
  "safeguarding_review": "PASS",
  "responsible_role": "",
  "learner_can_pause": false,
  "alternative_path": "",
  "record": {
    "enabled": false,
    "owner_role": "",
    "access_roles": [],
    "retention_or_deletion_rule": "",
    "correction_path": "",
    "export_path": "",
    "deletion_path": ""
  },
  "external_transfer": "HOLD",
  "evidence_status": "PASS",
  "decision": "COMMIT"
}
```

### Состояние 1

```json
{
  "id": "a",
  "version": 1,
  "status": "example-template",
  "subject": "",
  "setting": "",
  "learning_goal": "",
  "starting_task": "",
  "source": {
    "title": "",
    "url": "",
    "checked_on": "",
    "rights_status": "PASS"
  },
  "practice_step": "",
  "feedback_criterion": "",
  "transfer_task": "",
  "access_options": [],
  "minimum_data_needed": [],
  "data_not_needed": [],
  "permissions_review": "PASS",
  "safeguarding_review": "PASS",
  "responsible_role": "",
  "learner_can_pause": false,
  "alternative_path": "",
  "record": {
    "enabled": false,
    "owner_role": "",
    "access_roles": [],
    "retention_or_deletion_rule": "",
    "correction_path": "",
    "export_path": "",
    "deletion_path": ""
  },
  "external_transfer": "HOLD",
  "evidence_status": "PASS",
  "decision": "ROLLBACK"
}
```

### Найденное текстовое основание

`SUTI.uni.zip` / `SUTI.uni/SUTI.studium/README.md`, source SHA256 `37756b77cb6ca208e7de97dd290b1e76da74a897fc66cfbee5dc9a03f93eaab8`, UTF-8 bytes `[24899,25100)`, chars `[14037,14146)`:

> Решение о расширении, закупке, интеграции ПО или передаче данных является отдельным от удачной учебной пробы.

Это документированное указание, не исполнимое условие JSON Schema. Привязка к точному полю, версии и этапу остаётся UNKNOWN. Новое применимое исполнимое ограничение в измеренном поиске не найдено; это не отсутствие связи во всём SUTI. Старая пара сохранена относительно исходной схемы. Скалярная модель по-прежнему имеет LOST, совместное наблюдение сохраняет выбранные значения.

**Вопрос:** Относится ли `decision=COMMIT/ROLLBACK` к учебной пробе при отдельно остающемся `external_transfer=HOLD`, как предполагает эта пара записей?

## Варианты продолжения

Сохранить отдельные поля и неизвестную связь — текущий проверенный вариант. Если автор укажет действительное условие, сохранить его точный источник и область, затем повторить валидацию полных записей. Новое правило не придумывать; документированное сужение пометить NARROWED и версионировать. Runtime SUTI и native LivingMath не запускались; proof_status=unverified, execution_permission=false.
