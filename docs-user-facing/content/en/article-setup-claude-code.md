---
type: article
slug: setup-claude-code
locale: en
title: "Claude Code"
description: "A terminal coding agent with CLAUDE.md, skills, agents, hooks, MCP, and versioned plugins"
published_at: 2026-09-04
tags: [setup, claude-code, harness]
draft: false
---

# Claude Code

![(Claude Code) profile](/content/illustrations/setup-claude-code.jpg)

Claude Code is Anthropic's terminal coding agent. Its base layer is `CLAUDE.md`, a file for persistent project context and rules. Skills, subagents, hooks, MCP, and plugins sit on top of it. A setup is therefore a coordinated set of rules, workflows, roles, and integrations, not merely a collection of prompt files.

## Native surface

| Area | What Claude Code reads | ai-stp projection |
| --- | --- | --- |
| User | `~/.claude/CLAUDE.md`, `rules/`, `skills/`, `agents/`, `commands/`, `settings.json` | Shared instruction, skill, agent, command, hook, and setting |
| Project | `CLAUDE.md`, `.claude/CLAUDE.md`, `.claude/rules/`, `.claude/skills/`, `.claude/agents/`, `.claude/commands/`, `.claude/settings.json`, `.mcp.json` | Project-scoped components |
| Plugin | `.claude-plugin/plugin.json` at plugin root; `skills/`, `agents/`, `hooks/`, `.mcp.json`, `settings.json` beside it | Versioned packaging surface |

Do not confuse `.claude-plugin/` with the plugin contents: that directory contains the manifest, while component directories live at the package root. A `CLAUDE.md` inside a plugin does not become project context; shipped context belongs in a skill.

## How the setup is assembled

1. `ai-stp` discovers declared native surfaces and excludes cache, sessions, and auth state.
2. Each object receives a passport with its kind, version, source, and trust line.
3. The assembler checks the graph: MCP remains MCP, rather than becoming arbitrary text inside `CLAUDE.md`.
4. The public `claude-setup-system` receives the exact plan and writes the target harness. The website only stores and displays the result.

This preserves the difference between always-loaded instruction, task-triggered skill, isolated-context agent, event hook, and external-service MCP.

## When to choose Claude Code

Choose Claude Code when the workflow lives in the terminal and the team needs project rules, reusable skills, and versioned plugins together. For a local experiment, `.claude/skills/` is enough; for distribution across repositories, use a manifest-backed plugin with an exact version.

## Links

- [Claude Code extensions overview](https://code.claude.com/docs/en/features-overview)
- [CLAUDE.md and project memory](https://code.claude.com/docs/en/memory)
- [Creating plugins](https://code.claude.com/docs/en/plugins)
- [Public NDDev OpenNetwork claude-setup-system](https://github.com/NDDev-OpenNetwork/claude-setup-system)

## Trust boundary

Harness support does not mean that every third-party skill or plugin is safe. Review contents, exact version, permissions, and rollback before installation.

> Observe → passport → compatibility check → exact plan → provider installation. That sequence matters more than a polished UI or a famous system name.
