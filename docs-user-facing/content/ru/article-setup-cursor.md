---
type: article
slug: setup-cursor
locale: ru
title: "Cursor"
description: "IDE-harness с .cursor-plugin/plugin.json, rules, skills, agents, hooks, MCP и commands"
published_at: 2026-09-04
tags: [setup, cursor, harness]
draft: false
---

# Cursor

![Профиль Cursor](/content/illustrations/setup-cursor.jpg)

Cursor — IDE-harness, где plugin является основной единицей доставки. Манифест `.cursor-plugin/plugin.json` описывает правила, skills, agents, commands, hooks и MCP, а проект может хранить те же surfaces в `.cursor/`. Поэтому один setup Cursor — это manifest плюс ресурсы, на которые он ссылается.

## Нативная поверхность

| Область | Что читает Cursor | Как это отражается в ai-stp |
| --- | --- | --- |
| Пользователь | `~/.cursor/plugins/local/`, `skills/`, `skills-cursor/`, `rules/`, `commands/`, `hooks.json`, `mcp.json`, `cli-config.json` | Global plugin, skill, instruction, command, hook, MCP и setting |
| Проект | `.cursor/plugins/`, `.cursor/skills/`, `.cursor/rules/`, `.cursor/agents/`, `.cursor/commands/`, `.cursor/hooks.json`, `.cursor/mcp.json` | Project-scoped resources |
| Plugin | `.cursor-plugin/plugin.json` и пути `skills`, `rules`, `agents`, `commands`, `hooks`, `mcpServers` | Manifest-controlled package |

Нельзя считать любой каталог `plugins` готовым plugin: discovery проверяет нативный root и manifest. Для Cursor это особенно важно, потому что plugin может содержать несколько типов компонентов, а project agent и global agent имеют разные surfaces.

## Как собирается setup

1. Discovery находит plugin root, читает manifest и отдельно проверяет project `.cursor`-ресурсы.
2. Passport сохраняет component kind, manifest path, scope, источник и exact version.
3. Ассемблер не раскладывает plugin «по похожим папкам»: provider получает package как plugin и сохраняет относительные пути манифеста.
4. Публичный `cursor-setup-system` применяет exact plan к Cursor home или проекту; сайт не меняет IDE напрямую.

В Cursor rules — постоянные ограничения, skill — workflow, agent — роль, command — явный вызов, hook — событие, MCP — внешний сервис, plugin — упаковка всех этих поверхностей.

## Когда выбирать Cursor

Cursor подходит, если основной рабочий процесс идёт в IDE и setup должен быть виден команде как plugin package. Для project-specific правил храните `.cursor/` в репозитории; для общих ресурсов используйте user plugin и проверяйте manifest.

## Ссылки

- [Cursor Plugins](https://cursor.com/docs/plugins)
- [Reference plugins](https://cursor.com/docs/reference/plugins)
- [Настройка Cursor CLI](https://cursor.com/docs/cli/reference/configuration)
- [Публичный cursor-setup-system NDDev OpenNetwork](https://github.com/NDDev-OpenNetwork/cursor-setup-system)

## Граница доверия

Манифест описывает структуру, но не доказывает безопасность scripts и MCP. Проверяйте весь package, источники marketplace, exact pin и rollback перед установкой.

> Manifest → passport → проверка путей и scope → exact plan → запись через provider.
