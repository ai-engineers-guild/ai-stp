---
title: "Quickstart for people"
description: "Install the ai_stp CLI, check the environment, and reach the first catalog read."
---

# Quickstart for people

The shortest path that actually prepares a machine: install the CLI, see what
is missing, create the local identities, then read the public catalog.
Selecting and applying a setup is the next chapter, not this one.

If you are an agent driving this CLI, use
[Quickstart for agents](agent.md) instead.

The executable is `ai-stp`. The PyPI distribution is `ai-stp-cli`. Copying
`uv tool install ai-stp` installs a package this project does not publish.

## Install the CLI

```bash
uv tool install ai-stp-cli
ai-stp version --json
```

If the shell cannot find `ai-stp`, the `uv` tools directory is not on `PATH`.
See [Troubleshooting](../troubleshooting/index.md).

## Ask the installation what it can do

```bash
ai-stp doctor --json
ai-stp capabilities --json
```

`doctor` is a read. It does not create a device, a passport, or a project. It
reports the CLI, the local registry, the device, the toolchain, the Agent Skill,
and the harnesses this machine already has.

`capabilities` answers a narrower question: which surfaces this build can talk
to right now. Do not infer harness support from a version string.

## Create the local identities

Local work does not need an account. It does need a device and a developer
passport:

```bash
ai-stp device init --json
ai-stp device show --json
ai-stp passport developer init --json
ai-stp passport device refresh --json
```

`device init` is idempotent: a second run returns the identity the first one
made. The private key lives in the operating system's secret store; if that
store is unavailable the CLI says it fell back to a file and does not hide the
fact.

`device reset` is a different command. It is destructive, needs `--confirm`, and
is not a way to retry `doctor`.

## Follow what doctor asked for

Read the doctor report before inventing the next step.

=== "Toolchain missing"
    The first-run toolset is a pinned profile, not a random `pip install`:

    ```bash
    ai-stp toolchain profile --json
    ai-stp toolchain install --tool <id> --json
    ```

    `<id>` is a tool the profile pins. Exact names come from
    `ai-stp help --agent --json`. `toolchain install` writes into the managed
    directory and runs nothing from the tool it just placed.

    More: [Toolchain](../cli/toolchain.md).

=== "Agent Skill missing"
    This is the CLI's own Agent Skill, not a `skill` component in a setup.
    Install it so the agent has a procedure to follow:

    ```bash
    ai-stp skill status --target <dir> --json
    ai-stp skill install --target <dir> --json
    ```

    `--target` is the directory the harness reads its native skill from.

    After it is present, the agent still starts every session with `doctor` and
    `help --agent`. See [Agent Skill CLI](../cli/skill.md) and
    [Quickstart for agents](agent.md).

=== "Harness program missing"
    Installing a setup is not the same as installing the harness program.
    The program itself is `harness install`. The provider that later writes
    native state is a separate binary. See [Harness program](../cli/harness.md)
    and [Provider](../cli/provider.md).

## Look at the public catalog

Anonymous reads need no sign-in. `--kind` is required: `component` or `setup`.

```bash
ai-stp registry search --kind component --json
ai-stp registry show --kind component --id <stable_id> --json
```

A result is a candidate, not permission to install. Check the harness, the
exact `X.Y` version, the trust line, and the two independent verification
axes before you select anything. How to read a card: [Catalog](../catalog/index.md).
The same objects are on the website: [Web catalog](../web/catalog.md).

If the network is down, the CLI may answer from cache and will say when the
platform last confirmed the bytes.

## What this quickstart does not do

It does not sign you in, compose a setup, or write a harness target. Those
are separate, digest-bound paths:

| Next job | Page |
| --- | --- |
| Choose a composition | [Select](../cli/select.md) |
| Apply it through the provider | [Install](../cli/install.md) |
| Import an existing native config | [Setup commands](../cli/setup.md) |
| Sign in and sync | [Sign-in](../cli/auth.md) |
| Publish a component | [Publish a component](../cli/component-publish.md) |
| Drive the CLI as an agent | [Quickstart for agents](agent.md) |

## Typical refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `ai-stp` not found | the tool is missing or not on `PATH` | reinstall with `uv tool install ai-stp-cli`, then check `uv tool list` |
| doctor reports no device | identity was never created | `ai-stp device init --json` |
| search returns cache | the platform was not reached | read `checked_at`; do not treat it as a live catalog |
| capabilities omit a harness | this build cannot drive that target | stay on a primary harness, or read [Harnesses](../harnesses.md) |

## Related pages

- [Quickstart](index.md) — choose the human path or the agent path.
- [Quickstart for agents](agent.md) — session ritual and machine help.
- [CLI](../cli/index.md) — envelopes, mutability, confirmation.
- [Web](../web/index.md) — catalog cards and the account.
- [Concepts](../concepts/index.md) — one word, one object.
- [Trust and safety](../trust-and-safety/index.md) — what “verified” does not mean.

!!! note "Commands here are a map, not a parser"
    If `help --agent` disagrees with a flag on this page, the CLI wins.
