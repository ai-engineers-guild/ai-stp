---
type: article
slug: setup-codex
locale: en
title: "Codex"
description: "A coding agent with AGENTS.md, config.toml, subagents, hooks, and plugin projection"
published_at: 2026-09-04
tags: [setup, codex, harness]
draft: false
---

# Codex

![(Codex) profile](/content/illustrations/setup-codex.jpg)

Codex is OpenAI's local coding agent for terminal and project workflows. Its primary contract file is `AGENTS.md`, which supplies project rules. The rest of the setup lives in `config.toml`, prompts, subagents, and hooks; a plugin is packaging, but it does not replace Codex's native rules.

## Native surface

| Area | What Codex reads | ai-stp projection |
| --- | --- | --- |
| User | `$CODEX_HOME/AGENTS.md`, `prompts/`, `config.toml`, `agents/*.toml` | Global instruction, command, setting, MCP, and agent |
| Project | `.codex/config.toml`, `.codex/agents/*.toml`, `.codex/hooks.json` | Project setting, agent, and hook |
| Plugin | `.codex-plugin/plugin.json` and declared package resources | Plugin projection without inventing an `agents/` subtree |
| Shared skills | `.agents/skills/` | Portable skills shared by multiple harnesses |

Codex subagents use the native `agents/<name>.toml` format with role fields. Do not move a Markdown file there just because another harness stores agents as `.md`. MCP is likewise recognized from the `mcp_servers` key inside `config.toml`, not merely from the file's presence.

## How the setup is assembled

1. `ai-stp` finds `AGENTS.md`, settings, commands, subagents, and declared MCP only in native locations.
2. The passport records harness, scope, component kind, version, and source while excluding auth files, cache, and session history.
3. The setup assembler checks that the selected components are compatible with Codex and the chosen project scope.
4. The public `codex-setup-system` receives the exact plan and applies it to `$CODEX_HOME` or the project target. The web catalog never writes into a working Codex directly.

This keeps `AGENTS.md` as always-on instruction, a skill as portable workflow, a subagent as a named role, a hook as an event reaction, and MCP as external-service configuration.

## When to choose Codex

Codex fits repositories where rules should live beside code in `AGENTS.md`, while parameters and integrations stay in `config.toml`. Use shared `.agents/skills/` for portable workflows and the native TOML subagent format for specialized roles.

## Links

- [Official Codex documentation](https://developers.openai.com/codex)
- [AGENTS.md guide](https://developers.openai.com/codex/guides/agents-md)
- [Codex CLI source](https://github.com/openai/codex)
- [Public NDDev OpenNetwork codex-setup-system](https://github.com/NDDev-OpenNetwork/codex-setup-system)

## Trust boundary

Codex support in the catalog means support for declared surfaces, not automatic approval of any `AGENTS.md`, plugin, or command. Review contents, exact version, permissions, and rollback.

> Observe → passport → graph check → exact plan → provider write. This prevents project rules from being mixed accidentally with Codex state.
