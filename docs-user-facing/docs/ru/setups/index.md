---
title: "Сетапы"
description: "Как ai_stp собирает полный сетап из точных версий компонентов."
---

# Сетапы

Сетап — итоговая конфигурация одного харнесса. Он закрепляет точные версии
компонентов и применяется только через public provider этого харнесса.

Опубликованная версия сетапа неизменяема и имеет вид `X.Y`, а не SemVer.
Патч-номера нет. Замена одного компонента, отключение hook или изменение
setting создают новый `X.Y`.

## Сборка из каталога и внешних источников

`setup compose` собирает один точный setup из каталожных компонентов и
embedded-компонентов из GitHub, package registry или локального пути. Внешнему
компоненту не обязательно иметь собственную карточку в каталоге. Проверенные
метаданные и источники кладутся в JSON-манифест:

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

Сначала план, затем в apply передаются возвращённые идентификатор сетапа,
метка времени и digest плана:

```text
ai-stp setup compose plan --manifest setup.json --root . --json
ai-stp setup compose apply --manifest setup.json --root . --id <setup_id> --created-at <created_at> --expected-plan-digest <digest> --confirm --json
ai-stp setup publish plan --id <setup_id> --version 1.0 --json
```

Git ref замораживается в commit, package требует точную версию, а локальный путь
ограничен `--root`. `apply` повторно получает источники и откажется, если байты
изменились. Embedded-компоненты публикуются внутри setup, а каталожные сохраняют
своего publisher и идентичность.

## Обновление сетапа

Compose замораживает граф. Update заменяет **один embedded-участник** более
новым точным снимком и создаёт новую неизменяемую версию сетапа. Команда не
выбирает за вас тег «latest».

```bash
ai-stp setup update plan \
  --id <setup_id> \
  --version 1.0 \
  --component-id <component_id> \
  --harness codex \
  --source git:https://github.com/example/context7 \
  --commit <40-char-sha> \
  --json

ai-stp setup update apply \
  --id <setup_id> \
  --version 1.0 \
  --component-id <component_id> \
  --harness codex \
  --source git:https://github.com/example/context7 \
  --commit <40-char-sha> \
  --expected-plan-digest <digest> \
  --confirm \
  --json
```

`--component-id` — точный embedded-идентификатор, никогда не отображаемое имя.
`--source` — `git:…`, `package:ecosystem:name@version` или `path:relative`.
Для Git можно добавить `--commit` и `--subpath`. Каталожные pins эта команда
не переписывает: их меняют новым compose или новым подтверждением select.

Текущая версия сетапа остаётся выбранной, пока вы не подтвердите новую. Apply
создаёт новый `X.Y`; он не пишет target харнесса.

## Как собирается сетап

Упрощённый путь:

```text
кандидаты из каталога и локального реестра
→ механические фильтры
→ вопросы агента
→ подтверждение пользователя
→ setup graph
→ deterministic compiler
→ provider plan
```

Агент помогает выбрать состав, но не обходит проверки совместимости, доступа и
безопасности. Сборщик проверяет граф и строит нативный пакет. Provider —
единственный, кто пишет target. См. [понятия](../concepts/index.md).

| Этап | Кто отвечает | Что должно быть видно |
| --- | --- | --- |
| Поиск кандидатов | CLI и каталог | источник, версия, харнесс, trust line |
| Выбор состава | пользователь и agent | почему выбран каждый компонент |
| Проверка графа | сборщик сетапа | конфликты, несовместимости, missing pieces |
| План применения | provider | target diff, backup, digest |
| Применение | provider | журнал операции и status |

## Установка

Перед изменением target provider строит план, создаёт резервную копию и только
после подтверждения применяет изменения. Команды живут на странице
[Установка](../cli/install.md): `install plan`, `install approve`,
`install apply`. Ежедневное состояние пары — [Target](../cli/target.md).

Работающий агент не изменяет собственный активный target по месту. Новый сетап
проверяется отдельно, а переключение выполняется после проверки.

## Резервная копия и rollback

Если применение не удалось, восстановление идёт через provider и журнал
операций. Не удаляйте резервные копии вручную до завершения восстановления.

Путь команд принадлежит страницам CLI, а не этой:

- снять копию, восстановить из копии, подтвердить и применить:
  [Установка](../cli/install.md);
- перечислить копии, назвать предыдущую подтверждённую версию, прочитать
  status и diff: [Target](../cli/target.md).

Три отличия, которые стоит держать в голове:

- `target rollback` **называет** предыдущую подтверждённую версию и ничего не
  восстанавливает. Это ответ на «куда откатываться», а не «откатись»;
- повторная установка прошлой версии через `action=update` — не то же самое,
  что восстановление: bundle не содержит файлов, которые вы не устанавливали, а
  копия их сохраняет;
- восстановление возвращает цель **целиком**. Восстановить один компонент
  нельзя, и такой запрос отклоняется.

```bash
ai-stp target backups --project <id> --harness <id> --json
ai-stp target rollback --project <id> --harness <id> --json
ai-stp install status --json
ai-stp install recover --operation <id> --json
```

??? tip "Как думать о версии сетапа"
    Сетап — не папка с текущими файлами, а закреплённый состав. Если вы
    обновили один `skill`, отключили `hook` или поменяли `setting`, это уже
    новая версия сетапа.

Смежные страницы: [Публикация](../publishing/index.md),
[Команды сетапа](../cli/setup.md).

## Связанные страницы

- [Понятия](../concepts/index.md) — сетап принадлежит одному харнессу.
- [Компоненты](../components/index.md) — что сетап закрепляет.
- [Выбор](../cli/select.md) — eligibility и proposal.
- [Установка](../cli/install.md) — план, approve, apply.
- [Каталог](../catalog/index.md) — как читать публичную карточку сетапа.
- [Доверие и безопасность](../trust-and-safety/index.md) — согласие до
  experimental pins.
