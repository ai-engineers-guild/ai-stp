---
type: article
slug: setup-cursor
locale: en
title: "Cursor"
description: "An IDE harness with .cursor-plugin/plugin.json, rules, skills, agents, hooks, MCP, and commands"
published_at: 2026-09-04
tags: [setup, cursor, harness]
draft: false
---

# Cursor

![(Cursor) profile](/content/illustrations/setup-cursor.jpg)

Cursor is an IDE harness where a plugin is the primary delivery unit. The `.cursor-plugin/plugin.json` manifest describes rules, skills, agents, commands, hooks, and MCP, while a project can keep the same surfaces under `.cursor/`. A Cursor setup is therefore the manifest plus the resources it references.

## Native surface

| Area | What Cursor reads | ai-stp projection |
| --- | --- | --- |
| User | `~/.cursor/plugins/local/`, `skills/`, `skills-cursor/`, `rules/`, `commands/`, `hooks.json`, `mcp.json`, `cli-config.json` | Global plugin, skill, instruction, command, hook, MCP, and setting |
| Project | `.cursor/plugins/`, `.cursor/skills/`, `.cursor/rules/`, `.cursor/agents/`, `.cursor/commands/`, `.cursor/hooks.json`, `.cursor/mcp.json` | Project-scoped resources |
| Plugin | `.cursor-plugin/plugin.json` and `skills`, `rules`, `agents`, `commands`, `hooks`, `mcpServers` paths | Manifest-controlled package |

Do not treat any directory named `plugins` as a ready plugin: discovery checks the native root and manifest. This matters because a plugin can contain many component kinds, while project and user surfaces have different scopes.

## How the setup is assembled

1. Discovery finds the plugin root, reads its manifest, and checks project `.cursor` resources separately.
2. The passport records component kind, manifest path, scope, source, and exact version.
3. The assembler does not scatter a plugin into “similar” folders: the provider receives it as a plugin and preserves manifest-relative paths.
4. The public `cursor-setup-system` applies the exact plan to the Cursor home or project; the website does not change the IDE directly.

In Cursor, rules are persistent constraints, skill is workflow, agent is a role, command is explicit invocation, hook is an event, MCP is an external service, and plugin packages these surfaces.

## When to choose Cursor

Choose Cursor when the main workflow happens in an IDE and the setup should be visible to the team as a plugin package. Keep project-specific rules under `.cursor/` in the repository, use a user plugin for shared resources, and review its manifest.

## Links

- [Cursor plugins](https://cursor.com/docs/plugins)
- [Cursor plugin reference](https://cursor.com/docs/reference/plugins)
- [Cursor CLI configuration](https://cursor.com/docs/cli/reference/configuration)
- [Public NDDev OpenNetwork cursor-setup-system](https://github.com/NDDev-OpenNetwork/cursor-setup-system)

## Trust boundary

A manifest describes structure, not the safety of scripts or MCP. Review the complete package, marketplace sources, exact pin, and rollback before installation.

> Manifest → passport → path and scope check → exact plan → provider write.
