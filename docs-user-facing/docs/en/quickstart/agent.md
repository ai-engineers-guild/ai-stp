---
title: "Quickstart for agents"
description: "Start every ai-stp session from task intents; run the CLI yourself; execute continuation argv only when the JSON field actor is cli; never reconstruct flags from memory."
---

# Quickstart for agents

Start from the live task registry. Choose author or install only when that intent
matches the goal; inspect scoped help for account, sync, publication and other
services. Do not invent an intent from an old example.

```bash
ai-stp task intents --json
ai-stp task input-schema --intent install --json
```

For authoring, gather the absolute source directory, harness, component kind,
name and license. For installation, gather every field of the returned schema,
including exact setup/provider/source pins and scope roots. Save the bounded
input JSON to a local file, then start the task with a unique idempotency key.
Read continuations and execute argv only when actor is cli. Keep the durable task
id distinct from the execution tool's process handle. Resume the current revision.

Never install or update a harness executable. Setup-system providers are ai-stp
installation components. On Linux they own final target writes. Active-agent
changes require a staged handoff and restart; macOS and Windows refuse provider
execution in this release. Do not claim installation from a plan or copied prompt.

The [canonical control skill](https://github.com/ai-engineers-guild/ai-stp/blob/main/skills/canonical/ai-stp/SKILL.md)
owns the detailed procedure. The executable registry owns fields and commands.
