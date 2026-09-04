---
type: article
slug: setup-claude-code
locale: ru
title: "Claude Code"
description: "Терминальный coding-agent: CLAUDE.md, skills, agents, hooks, MCP и versioned plugins"
published_at: 2026-09-04
tags: [setup, claude-code, harness]
draft: false
---

# Claude Code

![Профиль Claude Code](/content/illustrations/setup-claude-code.jpg)

Claude Code — терминальный coding-agent Anthropic. Его базовый слой — `CLAUDE.md`: файл с постоянным контекстом и правилами проекта. Поверх него подключаются skills, subagents, hooks, MCP и plugins. Поэтому setup здесь — это согласованный набор правил, процессов, ролей и интеграций, а не просто коллекция prompt-файлов.

## Нативная поверхность

| Область | Что читает Claude Code | Как это отражается в ai-stp |
| --- | --- | --- |
| Пользователь | `~/.claude/CLAUDE.md`, `rules/`, `skills/`, `agents/`, `commands/`, `settings.json` | Общие instruction, skill, agent, command, hook и setting |
| Проект | `CLAUDE.md`, `.claude/CLAUDE.md`, `.claude/rules/`, `.claude/skills/`, `.claude/agents/`, `.claude/commands/`, `.claude/settings.json`, `.mcp.json` | Проектные компоненты с более узкой областью действия |
| Plugin | `.claude-plugin/plugin.json` в корне plugin; рядом `skills/`, `agents/`, `hooks/`, `.mcp.json`, `settings.json` | Versioned packaging surface для повторного использования |

Важно не путать `.claude-plugin/` с содержимым plugin: в этой папке находится манифест, а каталоги компонентов лежат в корне пакета. `CLAUDE.md` внутри plugin не становится project-инструкцией; для поставляемого контекста используют skill.

## Как собирается setup

1. `ai-stp` обнаруживает только заявленные нативные поверхности и не принимает cache, sessions или auth за компоненты.
2. Для каждого объекта создаётся passport с типом, версией, источником и trust line.
3. Ассемблер проверяет совместимость графа: например, MCP остаётся MCP, а не произвольным текстом в `CLAUDE.md`.
4. Публичный `claude-setup-system` получает exact plan и сам пишет целевой harness. Сайт только хранит и показывает результат.

Так сохраняется разница между instruction, которая загружается постоянно, skill, который подключается по задаче, agent с изолированным контекстом, hook на событие и MCP для внешнего сервиса.

## Когда выбирать Claude Code

Claude Code подходит, если workflow живёт в терминале и команде нужны одновременно проектные правила, переиспользуемые skills и versioned plugins. Для локального эксперимента достаточно `.claude/skills/`; для распространения между проектами лучше собрать plugin с манифестом и exact version.

## Ссылки

- [Обзор расширений Claude Code](https://code.claude.com/docs/en/features-overview)
- [CLAUDE.md и память проекта](https://code.claude.com/docs/en/memory)
- [Создание plugins](https://code.claude.com/docs/en/plugins)
- [Публичный claude-setup-system NDDev OpenNetwork](https://github.com/NDDev-OpenNetwork/claude-setup-system)

## Граница доверия

Статус поддержки harness не означает, что каждая сторонняя skill или plugin безопасна. Перед установкой проверяйте содержимое, точную версию, разрешения и rollback.

> Наблюдение → passport → проверка совместимости → exact plan → установка provider. Такая последовательность важнее красивого UI и громкого имени системы.
