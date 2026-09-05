---
type: article
slug: setup-mimocode
locale: en
title: "MiMoCode"
description: "A system from the NDDev OpenNetwork line; ai-stp does not currently claim it as a separate supported harness."
published_at: 2026-09-04
tags: [setup, mimocode, harness]
draft: false
---

# MiMoCode

![(MiMoCode) profile](/content/illustrations/nddev-builder.jpg)

MiMoCode is a system from the open NDDev OpenNetwork line. In the current ai-stp contract it is not declared as a separate harness: the closed supported set contains seven setup-systems — Claude Code, Codex, Pi, OpenCode, Grok Build, Cursor, and Antigravity. This article therefore describes the support boundary and does not promise automatic MiMoCode installation.

## What can be stated about its setup

MiMoCode may have its own native structure, but this repository has no approved discovery catalog, provider surface, or public `mimocode-setup-system` for it. It would be unsafe to guess where instruction, skill, agent, plugin, MCP, or settings belong just because another harness uses similarly named directories.

| Layer | Status | Required before support |
| --- | --- | --- |
| Harness identity | Outside the closed supported set | Define the detector and exact product contract |
| Native surfaces | Not declared | Confirm global/project layout and component kinds |
| Setup assembler | Not declared | Add compatible projection rules and checks |
| Provider | Not declared | Publish a versioned provider with protocol and rollback |

## How it relates to ai-stp

ai-stp can store a description and a link to an external project, but it must not present MiMoCode as a verified setup. For the seven supported harnesses, the CLI discovers components, creates passports, checks the graph, assembles an exact plan, and delegates writes to the matching NDDev provider. For MiMoCode, only a safe read-only overview is available for now.

## What would be needed to add it

1. Describe MiMoCode's native layout and scopes.
2. Confirm which component kinds the product actually reads.
3. Release `mimocode-setup-system` with versioned protocol, manifest, and rollback.
4. Add evidence, projection rules, docs, and checks, then extend the closed set through a separate decision.

Until then, do not copy the whole user home into MiMoCode or install a discovered package automatically: a similar directory name is not compatibility evidence.

## Links

- [NDDev OpenNetwork organization](https://github.com/NDDev-OpenNetwork)
- [ai-stp public setup-system contract](https://github.com/NDDev-OpenNetwork/ai-stp/blob/main/specs/active/SPEC-008-provider-installation.md)

## Trust boundary

This article deliberately separates an external project from verified support. Without a declared surface, exact provider, and evidence, MiMoCode cannot enter automatic selection or installation flows.

> Upstream contract and native-surface measurement first; passport and provider second. Until then, overview and manual review only.
