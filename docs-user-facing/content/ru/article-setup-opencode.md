---
type: article
slug: setup-opencode
locale: ru
title: "OpenCode"
description: "Открытый harness с нативными skills, plugins, agents, commands, MCP и JSON-конфигом"
published_at: 2026-09-04
tags: [setup, opencode, harness]
draft: false
---

# OpenCode

![Профиль OpenCode](/content/illustrations/setup-opencode.jpg)

OpenCode — открытый harness с нативными skills, agents, commands, plugins и JSON-конфигурацией. В отличие от систем, где всё складывается в один control file, здесь роли разложены по каталогам: reusable workflow, специализированная роль, slash command и plugin имеют разные surfaces.

## Нативная поверхность

| Область | Что читает OpenCode | Как это отражается в ai-stp |
| --- | --- | --- |
| Пользователь | `~/.config/opencode/skills/`, `agents/`, `commands/`, `plugins/`, `AGENTS.md`, `opencode.json/jsonc`, `tui.json/jsonc` | Global skill, agent, command, plugin, instruction, MCP и settings |
| Проект | `.opencode/skills/`, `.opencode/agents/`, `.opencode/commands/`, `.opencode/plugins/`, `opencode.json/jsonc`, `tui.json/jsonc` | Project-specific компоненты |
| MCP | `mcp` внутри `opencode.json` или `opencode.jsonc` | MCP только при структурном объявлении ключа |

`json` и `jsonc` — два формата одной конфигурационной поверхности. Наличие файла само по себе не превращает его в MCP: `ai-stp` проверяет объявленный ключ и сохраняет setting отдельно от MCP.

## Как собирается setup

1. Discovery ищет только native directories и JSON-файлы OpenCode в выбранном scope.
2. Passport различает skill, agent, command, plugin, instruction, MCP и setting, даже когда они лежат рядом.
3. Ассемблер проверяет конфликт имён и совместимость scope; проектная версия не смешивается с пользовательской без явного плана.
4. Публичный `opencode-setup-system` применяет exact plan в конфигурационный root OpenCode. Сайт остаётся каталогом и control plane.

Нативная модель OpenCode хорошо подходит для одного setup, который собирается из небольших независимых частей: skill даёт знания и workflow, agent — специализацию, command — явный вызов, plugin — пакет расширений, MCP — внешний сервис, setting — режим работы.

## Когда выбирать OpenCode

OpenCode подходит, если нужны открытый runtime и явная файловая структура без скрытого импорта. Проектные компоненты удобно коммитить в `.opencode/`, а глобальные — держать в пользовательском конфигурационном каталоге.

## Ссылки

- [Skills OpenCode](https://opencode.ai/docs/skills)
- [Agents OpenCode](https://opencode.ai/docs/agents)
- [Plugins OpenCode](https://opencode.ai/docs/plugins)
- [Configuration OpenCode](https://opencode.ai/docs/config)
- [Публичный opencode-setup-system NDDev OpenNetwork](https://github.com/NDDev-OpenNetwork/opencode-setup-system)

## Граница доверия

Открытый runtime не делает сторонние plugins безопасными автоматически. Проверяйте manifest, scripts, MCP endpoints, exact version и возможность отката перед установкой.

> Наблюдение → passport → проверка структуры → exact plan → запись через provider.
