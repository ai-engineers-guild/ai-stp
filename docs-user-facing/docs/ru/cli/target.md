---
title: "Target"
description: "Ежедневный статус, diff, копии и именованная предыдущая версия. Сама ничего не восстанавливает."
---

# Target

Команды target — ежедневный вид одной пары проект–harness. Они читают.
Они никогда не обновляют target, не снимают backup и не восстанавливают его.

`target rollback` **называет** предыдущую подтверждённую версию.
Восстановление — это `install plan --action rollback`. Повторная установка
более ранней версии через `action=update` — не то же самое, что
восстановление из backup.

## Таблица команд

| Команда | Mutability | Confirmation | Когда |
| --- | --- | --- | --- |
| `ai-stp target status` | `read` | `none` | ежедневное состояние одного проекта и harness |
| `ai-stp target diff` | `read` | `none` | что изменила бы установка выбранной версии |
| `ai-stp target backups` | `read` | `none` | копии provider, из которых эта пара может восстановиться |
| `ai-stp target rollback` | `read` | `none` | назвать точную предыдущую verified-версию |

`--json` глобальный. Всегда передавайте его. Ни одна из этих команд не
берёт `--confirm` и не берёт digest плана.

## Status

```bash
ai-stp target status --project <project_id> --harness codex --json
```

`--project` — стабильный id паспорта проекта. `--harness` обязателен и
один из `antigravity`, `claude-code`, `codex`, `cursor`, `grok-build`,
`opencode`, `pi`.

Чтобы прочитать target как он есть сейчас, передайте provider:

```bash
ai-stp target status \
  --project <project_id> \
  --harness codex \
  --provider <exe> \
  --provider-manifest <path> \
  --protocol-version 3 \
  --target <dir> \
  --json
```

`--provider-manifest` необязателен: релиз, под которым эту пару последний
раз проверяли, читается из журнала, когда названный исполняемый файл — его
точные байты. Без подписанного релиза чтение спрашивает в v3.
`--unverified-provider` читает через исполняемый файл, который не покрыт
подписанным или attested-релизом. Изоляцию это не ослабляет.

`--requires-env` повторяемый. Каждое значение — дополнительная переменная
в верхнем регистре, которая нужна этому target сверх паспорта сетапа.
Никогда `NAME=value`. `--catalog-version` — новейшая известная версия,
чтобы сообщить catalog drift. `--target` обязателен для протокола v2 и v3.

`states` — список, потому что пара может одновременно ждать установки **и**
не хватать переменной. Значения: `not_selected`, `pending_install`,
`local_drift`, `catalog_drift`, `needs_configuration`, `installed`.

Поля успеха: `project_id`, `harness_id`, `states`, `selected_stable_id`,
`selected_version`, `installed_stable_id`, `installed_version`,
`observed_target_digest`, `verified_target_digest`, `missing_env`,
`pending_authorization`, `shadowed_by`, `catalog_version`.

## Diff

Diff отвечает, что изменила бы установка выбранной версии. Ничего не
меняет. Опции совпадают со `status`.

```bash
ai-stp target diff \
  --project <project_id> \
  --harness codex \
  --provider <exe> \
  --protocol-version 3 \
  --target <dir> \
  --json
```

Читайте изменения управляемых путей: `modified`, `added`, `deleted`, с
`expected_digest` и `observed_digest`. `unsafe` в observed digest значит,
что текущие байты не считаются content address.

## Backups

```bash
ai-stp target backups --project <project_id> --harness codex --json
```

Без `--provider` ответ — собственная запись журнала. С `--provider` те же
строки ещё говорят, какие копии всё ещё существуют и удерживаются — единственный
способ увидеть копию, которую журнал всё ещё предлагает, а provider уже
не имеет.

```bash
ai-stp target backups \
  --project <project_id> \
  --harness codex \
  --provider <exe> \
  --provider-manifest <path> \
  --protocol-version 3 \
  --target <dir> \
  --json
```

У каждой копии есть `backup_ref`, операция, которая её сняла, и версия
сетапа, установленная в тот момент. Эта команда ничего не восстанавливает.
Чтобы восстановить:

```bash
ai-stp install plan \
  --action rollback \
  --backup-ref <exact> \
  --provider <exe> \
  --provider-manifest <path> \
  --protocol-version 3 \
  --target <dir> \
  --json
ai-stp install approve --operation <id> --plan-digest sha256:... --json
ai-stp install apply --operation <id> --provider <exe> --json
```

## Rollback (только имя)

```bash
ai-stp target rollback --project <project_id> --harness codex --json
```

Только `--project` и `--harness`. Ответ называет `setup_stable_id`,
`setup_version`, `operation_id`, `verified_at`, `project_id`, `harness_id`.
Ничего не откатывает.

Три отличия, которые стоит держать в голове:

- `target rollback` называет предыдущую подтверждённую версию и ничего не
  восстанавливает. Это ответ на «куда откатываться», а не «откатись».
- Повторная установка более ранней версии через
  `install plan --action update` — не то же самое, что восстановление:
  bundle не содержит файлов, которые вы не устанавливали, а копия их
  сохраняет.
- Восстановление возвращает target **целиком**. Один компонент
  восстановить нельзя, и такой запрос отклоняется.

Сетап — закреплённый состав, не папка с текущими файлами. Обновить один
`skill`, отключить `hook` или поменять `setting` — уже новая версия сетапа.

## Happy path

Ежедневно:

```text
target status --project <id> --harness <id>
→ target diff --project <id> --harness <id>   # если states включает local_drift
→ install plan …                              # если решите менять
```

После успешного apply:

```text
target status --project <id> --harness <id>
→ states включает installed
```

Перед рискованным изменением:

```text
install plan --action backup … → approve --plan-digest → apply
→ target backups --project <id> --harness <id>
→ target rollback --project <id> --harness <id>   # имя, не restore
```

## Именованные поля успеха

| Команда | Какие поля читать |
| --- | --- |
| `status` | `states`, `selected_*`, `installed_*`, `missing_env`, `shadowed_by` |
| `diff` | у управляемого пути `code`, `expected_digest`, `observed_digest` |
| `backups` | `backup_ref`, флаг held, версия сетапа на копии |
| `rollback` | `setup_stable_id`, `setup_version`, `operation_id`, `verified_at` |

## Отказы

| Что видно | Что это значит | Что делать |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` | нет `--project` или `--harness`, или нет `--target` для v2/v3 | добавить объявленные опции |
| `AI_STP_NOT_FOUND` | у этой пары ещё нет журнала | сначала select и install; пустой status — типизированная пустота, когда пара есть, а установлено ничего |
| `AI_STP_UNSUPPORTED_APPLY` | этот harness id не из закрытого набора | использовать поддерживаемый harness |
| считать `target rollback` восстановлением | он только называет версию | `install plan --action rollback --backup-ref` |
| просить восстановить один компонент | восстановление — весь target | отказ; соберите новый сетап |
| `NAME=value` в `--requires-env` | опция берёт только имя | передать имя переменной в верхнем регистре |
| удалять backup руками | восстановлению они ещё нужны | ждать, пока recover/resume не закончится |

Работающий агент не меняет свой активный target на месте. Новый сетап
проверяется отдельно; переключение — после этой проверки.

## Связанные страницы

- [Установка](install.md)
- [Выбор](select.md)
- [Provider](provider.md)
- [Сетапы](../setups/index.md)
- [Диагностика](../troubleshooting/index.md)
- [Карта команд](commands.md)

## Machine help — это парсер

```bash
ai-stp help --agent --json
```

Эта страница группирует команды target, чтобы человек их нашёл.
Установленный CLI — источник флагов, схем и `next_actions`. Если страница
и CLI расходятся, следуйте CLI.
