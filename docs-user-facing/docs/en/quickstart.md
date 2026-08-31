---
title: "Quickstart"
description: "First run of the ai_stp CLI and the shortest path to a checked environment."
---

# Quickstart

## Install the CLI

The CLI installs as an ordinary `uv` tool:

```bash
uv tool install ai-stp-cli
```

Then check that the command is available:

```bash
ai-stp version
ai-stp doctor --json
```

`doctor` reports the state of the environment, what this installation can do,
and anything that has to be fixed before assembling a setup.

## Prepare the device

For local work without an account, create a developer passport and a device:

```bash
ai-stp passport developer init --json
ai-stp device init --json
```

The device gets a `device_id` and a key. The private key is held in the
operating system's secret store; where that is unavailable, the CLI says
plainly that it fell back to file storage.

## Look at the catalog

Anonymous reading of the public catalog needs no sign-in:

```bash
ai-stp registry search --json
```

For one exact object, use `show`. With no network, the CLI may answer from the
last confirmed local copy and will say when the platform last confirmed it.

## What comes next

After the first `doctor`, the agent reads the machine help:

```bash
ai-stp help --agent --json
```

That help is the source of commands for the Agent Skill. An agent should not
invent commands from memory when the CLI already answers with them.

=== "I am choosing a published setup"
    Open the [catalog](catalog/index.md) and check the trust line, the
    compatibility with your [harness](harnesses.md), and what the setup is made
    of.

=== "I am assembling my own setup"
    Start with [components](components/index.md): it helps decide what belongs
    in a `skill`, what in an `mcp`, and what stays a `setting` or an
    `instruction`.

=== "I am publishing a component"
    See [publishing](publishing/index.md) and the trust rules. A published
    version is immutable, so it is worth checking the passport before the first
    release.
