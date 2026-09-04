---
type: article
slug: setup-codex
locale: ru
title: "Codex"
description: "Coding-agent с AGENTS.md, config.toml, subagents, hooks и plugin-проекцией"
published_at: 2026-09-04
tags: [setup, codex, harness]
draft: false
---

# Codex

![Профиль Codex](/content/illustrations/setup-codex.jpg)

Codex — локальный coding-agent OpenAI, который работает в терминале и встраивается в project workflow. Главный договорённый файл — `AGENTS.md`: из него агент получает правила проекта. Остальные части setup лежат в `config.toml`, `prompts`, subagents и hooks; plugin — это упаковка, но она не отменяет нативные правила Codex.

## Нативная поверхность

| Область | Что читает Codex | Как это отражается в ai-stp |
| --- | --- | --- |
| Пользователь | `$CODEX_HOME/AGENTS.md`, `prompts/`, `config.toml`, `agents/*.toml` | Global instruction, command, setting, MCP и agent |
| Проект | `.codex/config.toml`, `.codex/agents/*.toml`, `.codex/hooks.json` | Проектные setting, agent и hook |
| Plugin | `.codex-plugin/plugin.json` и объявленные ресурсы пакета | Plugin projection без выдуманного `agents/` subtree |
| Shared skills | `.agents/skills/` | Portable skills, доступные нескольким harness |

Для subagent Codex важен именно формат `agents/<name>.toml` с обязательными полями роли. Нельзя переносить туда markdown-файл только потому, что другой harness хранит agents в `.md`. Аналогично, MCP распознаётся по ключу `mcp_servers` внутри `config.toml`, а не по одному факту наличия файла.

## Как собирается setup

1. `ai-stp` находит `AGENTS.md`, настройки, команды, subagents и объявленные MCP только в их нативных местах.
2. Passport фиксирует harness, scope, component kind, версию и источник. Auth-файлы, cache и session history исключаются.
3. Setup assembler проверяет, что выбранные компоненты совместимы с Codex и с выбранной областью проекта.
4. Публичный `codex-setup-system` получает exact plan и применяет его в `$CODEX_HOME` или project target. Веб-каталог не пишет в рабочий Codex напрямую.

Так `AGENTS.md` остаётся always-on instruction, skill — переносимым workflow, subagent — отдельной ролью, hook — реакцией на событие, а MCP — конфигурацией внешнего сервиса.

## Когда выбирать Codex

Codex удобен для репозиториев, где правила хочется хранить рядом с кодом в `AGENTS.md`, а параметры и integrations — в `config.toml`. Для переносимой команды используйте shared `.agents/skills/`; для специализированной роли оформляйте именно нативный TOML subagent.

## Ссылки

- [Официальная документация Codex](https://developers.openai.com/codex)
- [Руководство по AGENTS.md](https://developers.openai.com/codex/guides/agents-md)
- [Исходный код Codex CLI](https://github.com/openai/codex)
- [Публичный codex-setup-system NDDev OpenNetwork](https://github.com/NDDev-OpenNetwork/codex-setup-system)

## Граница доверия

Поддержка Codex в каталоге означает поддержку declared surfaces, а не автоматическое одобрение любого `AGENTS.md`, plugin или команды. Проверяйте содержимое, exact version, permissions и rollback.

> Наблюдение → passport → проверка графа → exact plan → запись через provider. Это защищает project rules от случайного смешения с состоянием Codex.
