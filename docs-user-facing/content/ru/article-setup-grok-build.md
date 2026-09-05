---
type: article
slug: setup-grok-build
locale: ru
title: "Grok Build"
description: "Harness xAI с AGENTS.md, skills, plugins, hooks, MCP и config.toml"
published_at: 2026-09-04
tags: [setup, grok-build, harness]
draft: false
---

# Grok Build

![Профиль Grok Build](/content/illustrations/setup-grok-build.jpg)

Grok Build — harness xAI для агентской разработки. Его setup собран вокруг `.grok/` и `config.toml`: skills дают повторяемые workflow, plugins упаковывают расширения, hooks реагируют на события, а MCP объявляется структурно внутри конфигурации. `AGENTS.md` задаёт правила проекта и пользователя.

## Нативная поверхность

| Область | Что читает Grok Build | Как это отражается в ai-stp |
| --- | --- | --- |
| Пользователь | `~/.grok/AGENTS.md`, `skills/`, `plugins/`, `hooks/`, `config.toml` | Global instruction, skill, plugin, hook, MCP и setting |
| Проект | `.grok/skills/`, `.grok/plugins/`, `.grok/hooks/`, `.grok/config.toml` | Project resources, permissions и MCP |
| Marketplace | `~/.grok/plugins/marketplaces/` | Внешний источник, который требует отдельной provenance-проверки |

Текущий каталог ai-stp не выдумывает отдельную filesystem-поверхность для `agent`: runtime может поддерживать subagents, но provider принимает только declared projection. Поэтому агентские роли следует поставлять через подтверждённый plugin или другую capability, которую объявляет setup-system.

## Как собирается setup

1. Discovery проверяет `.grok/`, user root и ключи `mcp_servers` в `config.toml`.
2. Passport отделяет authored setup от logs, sessions, downloads, bundled runtime и auth state.
3. Ассемблер фиксирует scope и provenance marketplace, не выдавая неизвестный источник за verified component.
4. Публичный `grok-setup-system` получает exact plan и пишет только целевой user или project root.

Выбор типа простой: instruction — постоянные правила, skill — workflow, plugin — пакет, hook — автоматизация событий, MCP — внешний сервис, setting — `config.toml`. Marketplace — способ доставки plugin, а не самостоятельный тип компонента.

## Когда выбирать Grok Build

Grok Build подходит для xAI-oriented workflow с единым extension layer. Для проекта храните только нужные `.grok`-ресурсы, а пользовательский `~/.grok` не переносите целиком: рядом с setup находится много runtime state.

## Ссылки

- [Skills, plugins и marketplaces Grok Build](https://docs.x.ai/build/features/skills-plugins-marketplaces)
- [Настройки и scope](https://docs.x.ai/build/settings)
- [Публичный grok-setup-system NDDev OpenNetwork](https://github.com/NDDev-OpenNetwork/grok-setup-system)

## Граница доверия

Поддержка Grok Build не делает marketplace-пакет безопасным автоматически. Проверяйте provenance, manifest, scripts, MCP endpoints, exact version и rollback.

> Наблюдение → provenance → passport → проверка scope → exact plan → запись через provider.
