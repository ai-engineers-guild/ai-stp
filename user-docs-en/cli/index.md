---
description: "How a user and an agent work with the ai_stp CLI."
---

# CLI

The CLI is the main user interface of `ai_stp` for assembling, checking and
installing setups. The web shows the catalog and the account; it does not apply
configuration to a harness.

## Commands that observe

Observing commands create nothing and change nothing:

```bash
ai-stp version
ai-stp doctor --json
ai-stp capabilities --json
ai-stp help --agent --json
ai-stp config show --json
ai-stp auth status --json
ai-stp device show --json
```

On a fresh installation they return a typed state rather than quietly
initialising a device.

## Commands that change

Changing commands say what they do:

```bash
ai-stp device init --json
ai-stp passport developer init --json
ai-stp passport developer update --json
ai-stp passport device refresh --json
```

Dangerous actions ask for confirmation. Resetting a device, for one, must not
happen as a side effect of a diagnostic.

## Install telemetry

Off by default. After explicit consent the CLI sends one anonymous request per
component actually installed — what it carries and why is in
[Install telemetry](telemetry.md).

```bash
ai-stp telemetry show --json
```

## Agent Skill

The Agent Skill starts with:

```bash
ai-stp doctor --json
ai-stp help --agent --json
```

After that the agent uses the machine list of commands from the CLI itself.
That is what protects against stale instructions and hallucinated flags.

| Stage | Command | Why |
| --- | --- | --- |
| Check the environment | `ai-stp doctor --json` | see what is available and what is broken |
| Learn the capabilities | `ai-stp capabilities --json` | do not assume harness support |
| Get the machine help | `ai-stp help --agent --json` | use the commands that exist now |
| Find an object | `ai-stp registry search --json` | choose a setup or a component |
| Read an object | `ai-stp registry show <stable_id> --json` | check the passport before deciding |

!!! note "Commands here are a guide for people"
    If the CLI answers with newer machine help, the agent follows that. This
    documentation explains the model; it does not replace the CLI's executable
    help.
