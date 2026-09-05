---
type: article
slug: setup-grok-build
locale: en
title: "Grok Build"
description: "An xAI harness with AGENTS.md, skills, plugins, hooks, MCP, and config.toml"
published_at: 2026-09-04
tags: [setup, grok-build, harness]
draft: false
---

# Grok Build

![(Grok Build) profile](/content/illustrations/setup-grok-build.jpg)

Grok Build is xAI's harness for agentic development. Its setup is centered on `.grok/` and `config.toml`: skills provide repeatable workflows, plugins package extensions, hooks react to events, and MCP is declared structurally inside configuration. `AGENTS.md` supplies user and project rules.

## Native surface

| Area | What Grok Build reads | ai-stp projection |
| --- | --- | --- |
| User | `~/.grok/AGENTS.md`, `skills/`, `plugins/`, `hooks/`, `config.toml` | Global instruction, skill, plugin, hook, MCP, and setting |
| Project | `.grok/skills/`, `.grok/plugins/`, `.grok/hooks/`, `.grok/config.toml` | Project resources, permissions, and MCP |
| Marketplace | `~/.grok/plugins/marketplaces/` | External source requiring separate provenance review |

The current ai-stp catalog does not invent a separate filesystem `agent` surface for Grok Build: runtime may support subagents, but the provider accepts only a declared projection. Agent roles should therefore arrive through a proven plugin or another capability explicitly declared by the setup-system.

## How the setup is assembled

1. Discovery checks `.grok/`, the user root, and the `mcp_servers` key in `config.toml`.
2. The passport separates authored setup from logs, sessions, downloads, bundled runtime, and auth state.
3. The assembler records marketplace provenance and does not call an unknown source verified.
4. The public `grok-setup-system` receives the exact plan and writes only the selected user or project root.

The type mapping is direct: instruction is persistent rules, skill is workflow, plugin is a package, hook is event automation, MCP is an external service, and setting is `config.toml`. A marketplace is a delivery source for plugins, not a component kind.

## When to choose Grok Build

Choose Grok Build for an xAI-oriented workflow with one extension layer. Keep only the required `.grok` resources in a project and do not copy the entire `~/.grok`, because runtime state lives beside the setup.

## Links

- [Grok Build skills, plugins, and marketplaces](https://docs.x.ai/build/features/skills-plugins-marketplaces)
- [Grok Build settings and scopes](https://docs.x.ai/build/settings)
- [Public NDDev OpenNetwork grok-setup-system](https://github.com/NDDev-OpenNetwork/grok-setup-system)

## Trust boundary

Grok Build support does not make a marketplace package safe automatically. Review provenance, manifest, scripts, MCP endpoints, exact version, and rollback.

> Observe → provenance → passport → scope check → exact plan → provider write.
