---
title: Components
description: Instructions, skills, MCP servers, hooks, commands, agents, plugins, and settings.
---

## Component kinds

- **instruction** — durable rules or memory.
- **skill** — a reusable agent workflow.
- **mcp** — an MCP server configuration and transport contract.
- **hook** — lifecycle automation.
- **command** — a user-invoked command.
- **agent** — a specialized agent definition.
- **plugin** — a harness-native extension package.
- **setting** — configuration not covered by another kind.

Each version is immutable and identified by its passport digest. A setup pins an exact version.

## instruction

Project rules, context, and durable memory. Never include secrets or local absolute paths.

## skill

A repeatable workflow. Define triggers, inputs, expected output, and a safe fallback.

## mcp

An MCP server, transport, and required environment variable names — never token values.

## hook

Lifecycle automation. Document the event, timeout, retry behavior, and failure mode.

## command

A user-facing command: arguments, an invocation example, and any changed state.

## agent

A specialized role with narrow responsibility and an explicit tool set.

## plugin

A harness-native extension. State compatible versions and the removal path.

## setting

Other configuration. State the default and safe value range.
