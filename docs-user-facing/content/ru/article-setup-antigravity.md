---
type: article
slug: setup-antigravity
locale: ru
title: "Antigravity CLI"
description: "Gemini-based harness: skills, agents, plugins, hooks, MCP и project resources"
published_at: 2026-09-04
tags: [setup, antigravity, harness]
draft: false
---

# Antigravity CLI

![Профиль Antigravity CLI](/content/illustrations/setup-antigravity.jpg)

Antigravity CLI — Gemini-based harness для агентской разработки. Его особенность — конфигурация живёт в общем Gemini-доме: собственные настройки и plugins находятся в `antigravity-cli`, а skills и agents — в shared `config`. В проекте используется отдельная `.agents/`-поверхность.

## Нативная поверхность

| Область | Что читает Antigravity CLI | Как это отражается в ai-stp |
| --- | --- | --- |
| Общий Gemini home | `~/.gemini/config/skills/`, `agents/`, `plugins/`, `hooks.json`, `mcp_config.json`, `global_workflows/` | Global skill, agent, plugin, hook, MCP и command |
| Собственная часть CLI | `~/.gemini/antigravity-cli/settings.json`, `keybindings.json`, `plugins/` | Setting и отдельная plugin-поверхность CLI |
| Проект | `.agents/plugins/`, `.agents/skills/`, `.agents/agents/`, `.agents/hooks.json`, `.agents/mcp_config.json` | Project-scoped resources |

Общий home нельзя переносить целиком: в нём могут находиться данные Gemini и состояние, не относящиеся к setup. `ai-stp` переносит только declared surfaces и не смешивает `config` с `antigravity-cli`.

## Как собирается setup

1. Discovery проверяет нативные каталоги и отделяет authored components от runtime state.
2. Passport фиксирует scope, компонент, источник и точную версию plugin или resource.
3. Ассемблер выбирает project или global projection и не маршрутизирует инструкцию в неподдержанную папку.
4. Публичный `antigravity-setup-system` получает exact plan и применяет его в нужной части Gemini home или проекта.

Для Antigravity CLI skill — повторяемый workflow, agent — специализированная роль, plugin — deployable bundle, hook — событие, MCP — внешний сервис, command — workflow, а setting — JSON-профиль CLI. Каждый тип остаётся на своей native surface.

## Когда выбирать Antigravity CLI

Выбирайте его, если нужен Gemini-oriented workflow с shared skills и agents, но при этом важно отдельно контролировать project resources и plugin boundaries. Для безопасного переноса не копируйте весь `~/.gemini`: сначала проверьте discovery и составьте exact plan.

## Ссылки

- [Plugins и skills Antigravity CLI](https://antigravity.google/docs/cli/plugins/)
- [Настройки Antigravity CLI](https://antigravity.google/docs/cli/settings/)
- [Features и subagents](https://antigravity.google/docs/cli/features/)
- [Публичный antigravity-setup-system NDDev OpenNetwork](https://github.com/NDDev-OpenNetwork/antigravity-setup-system)

## Граница доверия

Общий Gemini home увеличивает цену ошибки: plugin или hook могут воздействовать на несколько проектов. Проверяйте манифесты, scripts, MCP endpoints, exact pin и rollback до применения.

> Наблюдение → разделение shared и project surface → passport → exact plan → запись через provider.
