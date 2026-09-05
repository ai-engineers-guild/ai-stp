---
type: article
slug: setup-opencode
locale: en
title: "OpenCode"
description: "An open harness with native skills, plugins, agents, commands, MCP, and JSON configuration"
published_at: 2026-09-04
tags: [setup, opencode, harness]
draft: false
---

# OpenCode

![(OpenCode) profile](/content/illustrations/setup-opencode.jpg)

OpenCode is an open harness with native skills, agents, commands, plugins, and JSON configuration. Unlike systems that place everything in one control file, it separates reusable workflows, specialized roles, slash commands, and plugins into distinct surfaces.

## Native surface

| Area | What OpenCode reads | ai-stp projection |
| --- | --- | --- |
| User | `~/.config/opencode/skills/`, `agents/`, `commands/`, `plugins/`, `AGENTS.md`, `opencode.json/jsonc`, `tui.json/jsonc` | Global skill, agent, command, plugin, instruction, MCP, and settings |
| Project | `.opencode/skills/`, `.opencode/agents/`, `.opencode/commands/`, `.opencode/plugins/`, `opencode.json/jsonc`, `tui.json/jsonc` | Project-specific components |
| MCP | `mcp` inside `opencode.json` or `opencode.jsonc` | MCP only when the key is structurally declared |

`json` and `jsonc` are two formats for the same configuration surface. A file's presence alone does not make it MCP: `ai-stp` checks the declared key and keeps settings separate from MCP.

## How the setup is assembled

1. Discovery searches only OpenCode native directories and JSON files in the chosen scope.
2. The passport distinguishes skill, agent, command, plugin, instruction, MCP, and setting even when they sit next to one another.
3. The assembler checks name conflicts and scope compatibility; project and user versions are not mixed without an explicit plan.
4. The public `opencode-setup-system` applies the exact plan to the OpenCode configuration root. The website remains the catalog and control plane.

OpenCode's native model works well for a setup made of small independent parts: skill provides knowledge and workflow, agent provides specialization, command provides explicit invocation, plugin provides a package, MCP connects an external service, and setting selects runtime behaviour.

## When to choose OpenCode

Choose OpenCode when you want an open runtime and an explicit file structure without hidden import rules. Commit project components under `.opencode/` and keep user-wide components in the user configuration directory.

## Links

- [OpenCode skills](https://opencode.ai/docs/skills)
- [OpenCode agents](https://opencode.ai/docs/agents)
- [OpenCode plugins](https://opencode.ai/docs/plugins)
- [OpenCode configuration](https://opencode.ai/docs/config)
- [Public NDDev OpenNetwork opencode-setup-system](https://github.com/NDDev-OpenNetwork/opencode-setup-system)

## Trust boundary

An open runtime does not make third-party plugins safe automatically. Review manifests, scripts, MCP endpoints, exact version, and rollback before installation.

> Observe → passport → structure check → exact plan → provider write.
