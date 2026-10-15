---
title: "CLI"
description: "Discover native commands, configuration and operation recovery."
---

# Rust CLI

The executable registry owns commands and parameters:

```sh
ai-stp help --agent --json
ai-stp task intents --json
ai-stp task input-schema --intent install --json
```

Use `help --path <command> --json` for a smaller scope. Task intents cover authoring
and installation; account, sync, publication and other services have direct commands.
Do not reconstruct a command from old session notes.

Machine mode returns one JSON envelope. Inspect domain status and receipts: a plan
is not an applied effect, and cached account status does not prove a live session.
Mutations bind exact inputs and digest. Resume the original admitted operation after
interruption; read the current task revision before continuing.

Explicit YAML configuration supports `catalog.enabled`, `catalog.url` and
`sync.enabled`. Pass it through `--config`; sync is disabled by default. Credentials
stay in the chosen credential store. State is selected by `--state-dir`,
`AI_STP_STATE_DIR`, or the XDG data directory. Never treat this directory as cache.

The [native guide](https://github.com/ai-engineers-guild/ai-stp/blob/main/apps/cli-v2/README.md)
owns installation, migration, modules and platform limits. The
[agent workflow](../quickstart/agent.md) explains task execution.
