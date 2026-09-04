---
type: article
slug: setup-pi
locale: en
title: "Pi"
description: "A minimal harness with package resources, skills, extensions, prompts, and target settings"
published_at: 2026-09-04
tags: [setup, pi, harness]
draft: false
---

# Pi

![(Pi) profile](/content/illustrations/setup-pi.jpg)

Pi is a minimal local coding agent. Its strength is a transparent resources layer: skills and prompt templates come from directories or packages, while settings explicitly decide which extensions and models are available. That keeps a setup small and inspectable, but it also means Pi must not be assigned capabilities belonging to another harness.

## Native surface

| Area | What Pi reads | ai-stp projection |
| --- | --- | --- |
| User | `~/.pi/agent/AGENTS.md`, `skills/`, `extensions/`, `prompts/`, `settings.json`, `models.json` | Global instruction, skill, plugin, command, and setting |
| Project | `.pi/skills/`, `.pi/extensions/`, `.pi/prompts/`, `.pi/settings.json` | Project resources after project trust |
| Package | npm/git package with resources | Portable skills and extensions |
| MCP | No separately documented native MCP configuration | Integration belongs in an extension/package, not an invented MCP file |

Pi uses `AGENTS.md` as instruction, while a project override can change loading order. Project resources also depend on the trust decision: the presence of `.pi/settings.json` does not mean Pi will automatically permit its contents.

## How the setup is assembled

1. `ai-stp` separates authored resources from `auth.json`, model store, cache, and session state.
2. The passport records the exact package or local source, scope, and role of each component.
3. The assembler checks that skills, prompts, extensions, and settings land on supported Pi surfaces.
4. The public `pi-setup-system` receives the exact plan and writes only the target Pi directory. The website does not start Pi or change its active session.

In catalog terms, Pi uses skill for on-demand workflow, plugin for extension/package, command for prompt template, setting for the JSON profile, and no separate native MCP kind.

## When to choose Pi

Pi fits a compact local setup where package resources, skills, and manual settings control matter. For a team, keep `.pi/` beside the project and check trust before enabling extensions.

## Links

- [Pi settings](https://pi.dev/docs/latest/settings)
- [Pi skills](https://pi.dev/docs/latest/skills)
- [Pi security](https://pi.dev/docs/latest/security)
- [Public NDDev OpenNetwork pi-setup-system](https://github.com/NDDev-OpenNetwork/pi-setup-system)

## Trust boundary

Pi is a local agent without a built-in sandbox, so read skills, packages, and extensions before enabling them. The ai-stp support tier does not replace content review, version pinning, or rollback.

> Observe → passport → project trust → resource check → exact plan → provider installation.
