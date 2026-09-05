---
title: "Команды сетапа"
description: "Собрать, импортировать, обновить и опубликовать полный сетап."
---

# Команды сетапа

Сетап — это полная конфигурация одного харнеса. Он фиксирует точные
версии компонентов. Эти команды компонуют смешанный сетап из каталога и
внешних источников, импортируют уже имеющуюся нативную конфигурацию, заменяют
один встроенный элемент и планируют публикацию всего графа.

Они не записывают таргет харнеса. Установка по-прежнему идёт через
[Install](install.md) и публичного провайдера.

## Таблица команд

| Команда | Мутабельность | Подтверждение | Когда |
| --- | --- | --- | --- |
| `ai-stp setup compose plan` | `plan` | `none` | разрешить и зафиксировать новый сетап из каталога, Git, пакетов и path-источников |
| `ai-stp setup compose apply` | `apply` | `plan_digest` | записать точный, по-прежнему актуальный смешанный сетап как одну неизменяемую локальную версию |
| `ai-stp setup import inspect` | `read` | `none` | прочитать одну нативную конфигурацию; ничего не записывать |
| `ai-stp setup import plan` | `plan` | `none` | спланировать точные черновики компонентов и сетапа из одной нативной конфигурации |
| `ai-stp setup import register` | `apply` | `plan_digest` | зарегистрировать проинспектированную конфигурацию как свой сетап |
| `ai-stp setup update plan` | `plan` | `none` | предпросмотр замены одного встроенного компонента более новым точным снапшотом |
| `ai-stp setup update apply` | `apply` | `plan_digest` | применить одно точное встроенное обновление и создать новую версию сетапа |
| `ai-stp setup publish plan` | `plan` | `none` | спланировать публикацию одного выпущенного сетапа со всеми компонентами, которые он фиксирует |
| `ai-stp setup publish confirm` | `apply` | `explicit_flag` | подтвердить один точный отрецензированный набор публикации |

`--json` — глобальный флаг. Всегда передавайте его.

`compose apply` и `update apply` требуют `--expected-plan-digest`. Этот
дайджест и есть решение. `import register` требует `--plan-digest` (это
декларированное имя). `publish confirm` требует `--set-digest` и `--confirm`,
потому что меняет видимость существующего объекта.

## Compose plan и apply

Поместите отрецензированные метаданные и источники в JSON-манифест. Внешние
компоненты не требуют записи в каталоге.

```json
{
  "schema_version": 1,
  "name": "Frontend developer",
  "description": "Playwright automation with local project checks.",
  "harness_id": "codex",
  "components": [
    {
      "source": {
        "kind": "catalog",
        "stable_id": "component_...",
        "version": "1.0",
        "passport_digest": "sha256:..."
      }
    },
    {
      "source": {
        "kind": "git",
        "repository_url": "https://github.com/example/context7",
        "tracked_ref": "main",
        "subpath": "."
      },
      "component_type": "mcp",
      "name": "Context7 MCP",
      "description": "Upstream Context7 MCP snapshot.",
      "license_spdx": "MIT",
      "redistribution_allowed": true,
      "upstream_project": "Context7"
    },
    {
      "source": {"kind": "path", "relative_path": "hooks/check"},
      "component_type": "hook",
      "name": "Project check",
      "description": "Locally authored project check.",
      "license_spdx": "LicenseRef-Proprietary",
      "redistribution_allowed": true
    }
  ]
}
```

```bash
ai-stp setup compose plan --manifest setup.json --root . --json
```

`--manifest` обязателен. `--root` ограничивает источники `path:`. `--id` — это
идентификатор сетапа, возвращённый предыдущим планом, когда вы перепроверяете ту же
идентичность.

Ответ плана несёт `setup_id`, `version`, `harness_id`, `created_at`,
`definition_digest`, `plan_digest`, `members`. У каждого элемента есть `stable_id`,
`version`, `source`, `embedded`.

Apply повторяет разрешение и отклоняет изменённые байты. Передайте возвращённый
идентификатор сетапа, временную метку и дайджест плана:

```bash
ai-stp setup compose apply \
  --manifest setup.json \
  --root . \
  --id <setup_id> \
  --created-at <created_at> \
  --expected-plan-digest sha256:... \
  --json
```

Git-ссылки разрешаются в коммиты, источники-пакеты требуют точных версий,
а локальные пути остаются в пределах `--root`. Встроенные элементы публикуются
только внутри сетапа; элементы каталога сохраняют своего существующего издателя.

Поля успеха: `setup_id`, `version`, `created_at`, `passport_digest`,
`definition_digest`, `plan_digest`, `created`.

## Import inspect, plan, register

Import вносит нативную конфигурацию харнеса в локальный реестр как
ваш собственный сетап. Значения секретов не сохраняются. Таргет не
затрагивается: провайдер уже сделал бэкап; register лишь записывает, где он.

```bash
ai-stp setup import inspect --root <native-dir> --harness codex --json
ai-stp setup import plan --root <native-dir> --harness codex --json
ai-stp setup import register \
  --root <native-dir> \
  --harness codex \
  --backup-ref <ref> \
  --plan-digest sha256:... \
  --json
```

`--root` и `--harness` обязательны для всех трёх. Register также требует
`--backup-ref` и `--plan-digest`. `--target` указывает, с какого таргета
был сделан бэкап. `--partial` регистрирует даже если некоторые файлы были
пропущены; паспорт записывает режим и точные пути.

Поля успеха inspect: `root`, `harness_id`, `detection_rule`, `files`,
`redacted_keys`, `oversized`, `unreadable`. Поля plan: `plan_digest`,
`inspection_digest`, `components`, `effects`, `excluded`, `blocked_by`.
Поля register: `stable_id`, `revision_id`, `backup_id`, `component_ids`,
`plan_digest`, `redacted_keys`.

## Update plan и apply

Замена одного **встроенного** компонента более новым точным снапшотом. Фиксации
каталога таким образом не обновляются.

```bash
ai-stp setup update plan \
  --id <setup_id> \
  --version 1.0 \
  --component-id <embedded_id> \
  --source git:https://github.com/example/context7 \
  --commit abcdef0123456789abcdef0123456789abcdef01 \
  --subpath . \
  --harness codex \
  --project . \
  --json
```

`--id`, `--version`, `--component-id`, `--source` и `--harness`
обязательны. `--source` — это точная координата `git`, `package:ecosystem:name@version`
или `path:relative`. `--commit` — точный lowercase
40-символьный Git SHA. `--project` — корень проекта, чей выбранный сетап
проверяется.

Apply повторяет те же опции и добавляет `--expected-plan-digest`:

```bash
ai-stp setup update apply \
  --id <setup_id> \
  --version 1.0 \
  --component-id <embedded_id> \
  --source git:https://github.com/example/context7 \
  --commit abcdef0123456789abcdef0123456789abcdef01 \
  --harness codex \
  --expected-plan-digest sha256:... \
  --json
```

Поля plan включают `plan_digest`, `setup_id`, `component_id`,
`from_version`, `to_version`, `snapshot_coordinate`, `snapshot_identity`,
`suggested_catalog_stable_id`, `suggested_catalog_version`,
`suggested_catalog_dismissible`. Поля apply: `created`, `setup_id`,
`from_version`, `to_version`, `selected_stable_id`, `selected_version`,
`plan_digest`. Результат — **новая** версия сетапа.

## Publish plan и confirm

Спланируйте публикацию одного выпущенного сетапа вместе со всеми компонентами,
которые он фиксирует. Подтверждение делает этот точный граф публичным: сначала
фиксированные компоненты, затем сетап.

```bash
ai-stp setup publish plan --id <setup_id> --version 1.0 --json
ai-stp setup publish confirm \
  --set-digest sha256:... \
  --confirm \
  --json
```

Plan требует `--id` и `--version`. Confirm требует `--set-digest` (дайджест,
который вернул plan) и `--confirm`.

Поля успеха: `set_digest`, `setup_stable_id`, `setup_version`, `state`,
`expires_at`, `members`. У каждого элемента есть `plan_id`, `plan_hash`, `role`,
`object_kind`, `stable_id`, `version`, `state`, `already_published`.

## Счастливый путь

Compose:

```text
setup compose plan --manifest setup.json --root .
→ setup compose apply --manifest setup.json --root . --id … --created-at … --expected-plan-digest …
→ select session / install plan
```

Import:

```text
setup import inspect --root <dir> --harness <id>
→ setup import plan --root <dir> --harness <id>
→ setup import register --root <dir> --harness <id> --backup-ref … --plan-digest …
```

Публикация графа:

```text
setup publish plan --id <setup_id> --version <X.Y>
→ setup publish confirm --set-digest … --confirm
```

## Именованные поля успеха

| Команда | Поля для чтения |
| --- | --- |
| `compose plan` | `setup_id`, `created_at`, `plan_digest`, `members` |
| `compose apply` | `setup_id`, `version`, `passport_digest`, `created` |
| `import inspect` | `files`, `redacted_keys`, `unreadable` |
| `import plan` | `plan_digest`, `components`, `blocked_by` |
| `import register` | `stable_id`, `backup_id`, `component_ids` |
| `update plan` | `plan_digest`, `from_version`, `to_version` |
| `update apply` | `created`, `to_version`, `selected_version` |
| `publish plan` / `confirm` | `set_digest`, `members`, `state` |

## Отказы

| Что вы видите | Что это значит | Что делать |
| --- | --- | --- |
| `AI_STP_USER_DECISION_REQUIRED` | `--confirm` был пропущен при publish confirm | передайте `--confirm` после ревью набора публикации |
| `AI_STP_VALIDATION_ERROR` | отсутствует `--expected-plan-digest`, `--plan-digest` или `--set-digest` | скопируйте дайджест, который вернул plan |
| `AI_STP_PLAN_STALE` | байты Git, байты пакетов или локальные пути изменились | спланируйте заново; apply отклоняет изменённые байты |
| `AI_STP_PRECONDITION_FAILED` | import register без бэкапа провайдера или несвязанный элемент | сделайте бэкап через install; исправьте манифест |
| `AI_STP_AUTH_REQUIRED` | publish требует выполненного входа | `auth login` |
| `AI_STP_PERMISSION_DENIED` | эта учётная запись не может публиковать этот сетап | проверьте владельца и гранты |
| путь за пределами `--root` | локальные источники ограничены | переместите файлы или измените `--root` |
| плавающая версия пакета | источники-пакеты требуют точную версию | зафиксируйте `name@version` |
| выдумывание `--expected-plan-digest` для import register | эта команда декларирует `--plan-digest` | используйте декларированное имя |

Секреты, удалённые при inspect, остаются удалёнными. Не вставляйте их обратно
в паспорт, чтобы «завершить» импорт.

## Связанные ссылки

- [Сетапы](../setups/index.md)
- [Select](select.md)
- [Install](install.md)
- [Источник компонента](component-source.md)
- [Публикация компонента](component-publish.md)
- [Publication](publication.md)
- [Publishing](../publishing/index.md)
- [Карта команд](commands.md)

## Machine help — это парсер

```bash
ai-stp help --agent --json
```

Эта страница группирует команды сетапа, чтобы человек мог их найти. Установленный
CLI — источник флагов, схем и `next_actions`. Если эта страница и
CLI расходятся, следуйте CLI.
