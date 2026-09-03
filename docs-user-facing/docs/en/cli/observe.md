---
title: "Observe"
description: "Read-only commands that report the running build, installation health, machine help, and current capabilities."
---

# Observe

These four commands look at this installation and print what they found.
They create no device, no passport, no configuration file, and no project.

The executable is `ai-stp`. The PyPI package is `ai-stp-cli`. Copy every
command from this page with `--json` so stdout holds exactly one envelope.

## Commands

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp version` | `read` | `none` | Report the running build and the contract versions it speaks. |
| `ai-stp doctor` | `read` | `none` | Report the setup state of this installation without changing it. |
| `ai-stp help` | `read` | `none` | Emit the full command registry for an agent. |
| `ai-stp capabilities` | `read` | `none` | Report what this installation can do right now. |

`mutability: read` means the command observes. A missing device, an empty
registry, or a configuration file that was never created is a typed answer,
not a reason to mint one.

## Typical path

On a fresh machine, or at the start of an agent session:

```bash
ai-stp version --json
ai-stp doctor --json
ai-stp capabilities --json
ai-stp help --agent --json
```

Read `doctor` before inventing the next step. If a check is
`needs_user_action`, follow that check, not a remembered ritual.
`capabilities` answers a narrower question than `version`: which surfaces
this *build* can talk to right now. Do not infer harness support from a
version string.

`help --agent` is the parser of *this* install. Documentation groups
commands so a person can find a page. An agent must not reconstruct flags
from memory when the CLI already answers with them.

## `version`

Report the running build and the contract versions it speaks.

```bash
ai-stp version --json
```

Use it to confirm that the shell is talking to the `ai-stp` you just
installed, not a different copy earlier on `PATH`. It does not check the
network, the device, or the catalog.

Successful `data` names:

| Field | What it is |
| --- | --- |
| `cli_version` | the running CLI version |
| `python_version` | the interpreter this process is using |
| `schema_version` | the local schema major this build speaks |
| `wire_schema_version` | the wire schema major this build speaks |

## `doctor`

Report the setup state of this installation without changing it.

```bash
ai-stp doctor --json
```

It is a report, not a verdict you have to “fix” in one shot. `state` is the
worst state among the checks, so a caller that reads one field still gets
the truth. Each check has `name`, `state`, and `detail`.

`state` on the report and on a check is one of `ready`, `needs_user_action`,
`partial`, or `failed`.

Checks this build currently names:

| `name` | What it looked at |
| --- | --- |
| `python_runtime` | whether the interpreter meets the floor |
| `configuration` | whether the configuration file, if present, can be honoured |
| `local_registry` | whether the local registry file is usable |
| `catalog` | whether the public catalog is enabled in configuration |
| `credential_store` | where secrets would be kept (`os_keyring` or `file`) |
| `device_identity` | whether this installation already has a device |
| `file_permissions` | whether private paths are owner-only |
| `interrupted_operations` | operations that stopped without a settled outcome |
| `component_layouts` | whether known component layouts still parse |
| `composition_passports` | whether recorded compositions still have a head |
| `addressable_objects` | whether every local object has a head revision |
| `provider_binding` | whether a remembered provider still resolves |

`doctor` does not create a device when `device_identity` is empty. It does
not install a toolchain, an Agent Skill, or a harness program. Those are
separate commands, reached after you have read the report.

!!! note "Absence is an answer"
    A read command on a fresh install returns typed emptiness. It does not
    silently run `device init`.

## `help`

Emit the full command registry for an agent.

```bash
ai-stp help --agent --json
```

`--agent` names the caller. The machine registry is the only answer this
command has, with or without that flag. Keep `--agent` in the invocation
anyway: every other page in this help center treats
`ai-stp help --agent --json` as the parser.

Successful `data` names:

| Field | What it is |
| --- | --- |
| `cli_version` | the running CLI version |
| `commands` | every declared command, with path, summary, mutability, confirmation, parameters, parameter rules, result schema, and `next_actions` |
| `error_codes` | the closed error registry this build can emit |
| `global_options` | options every command accepts, including `--json` |
| `schema_version` | the schema major of this envelope |

A command that this install cannot run is absent from `commands`, not
described as “not implemented”. If a page names a command that `help`
does not, stop. Do not substitute a similar path.

## `capabilities`

Report what this installation can do right now.

```bash
ai-stp capabilities --json
```

This is deliberately not a copy of the command registry. It carries the
few facts that decide whether a later call is even worth making.
`command_paths` is an index into `help --agent`, not a substitute for it.

Successful `data` names:

| Field | What it is |
| --- | --- |
| `cli_version` | the running CLI version |
| `command_paths` | the command paths this build declares |
| `supported_harnesses` | harness identifiers this build can name |
| `catalog_enabled` | whether configuration currently consults the public catalog |
| `sync_enabled` | whether cloud synchronisation is on |
| `schema_version` | the local schema major |
| `wire_schema_version` | the wire schema major |

`supported_harnesses` is the product set this build knows:
`claude-code`, `codex`, `pi`, `opencode`, `grok-build`, `cursor`,
`antigravity`. Presence in that list is not proof that the program is
installed on this machine. For that, use
[Toolchain](toolchain.md) (`toolchain harnesses`) and
[Harness program](harness.md) (`harness status`).

Do not treat `catalog_enabled: false` as a platform outage. It is a
configuration value. See [Configuration](config.md).

## What a successful envelope contains

With `ok: true` the result is in `data`. The envelope also carries
`warnings`, `next_actions`, `request_id`, `operation_id`, and
`schema_version`. `warnings` may still be worth showing. `next_actions`
names a sensible next command, not a permission.

With `ok: false`, `error.code` is a stable code from the closed registry;
`error.retryable` says whether a repeat is allowed. Do not guess the next
step from the process exit class alone.

## What these commands never do

- call a model API or ask for a model key;
- write a harness target — only the public provider does;
- create a device, a passport, or a configuration file;
- install a toolchain, an Agent Skill, or a harness program;
- treat `author_verified` as proof that a component version is safe.

## Typical refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `ai-stp` not found | the tool is missing or not on `PATH` | reinstall with `uv tool install ai-stp-cli`, then check `uv tool list` |
| doctor `device_identity` is not `ready` | identity was never created, or the store cannot read it | `ai-stp device init --json` if it was never created; otherwise read `detail` |
| doctor `local_registry` is not `ready` | the registry file is missing, unreadable, or not a registry | follow `detail`; do not delete the file to “retry” |
| capabilities omit a harness | this build cannot drive that target | stay on a primary harness, or read [Harnesses](../harnesses.md) |
| a command is absent from `help --agent` | this install does not have it | stop; do not substitute a similar command |
| `ok: false` with `retryable: false` | repeating the same argv will not help | read `error.code` and `next_actions` |

## Related pages

| Page | Why |
| --- | --- |
| [Quickstart](../quickstart.md) | the first-run path in prose |
| [CLI](index.md) | envelopes, mutability, and the command groups |
| [Command map](commands.md) | one row per command |
| [Configuration](config.md) | values this install should honour |
| [Device](device.md) | identity of this installation |
| [Passports](passport.md) | developer and device facts |
| [Toolchain](toolchain.md) | managed tools and harness survey |
| [Agent Skill CLI](skill.md) | the CLI's own skill, not kind `skill` |
| [Troubleshooting](../troubleshooting/index.md) | what to do after a red check |

!!! note "Flags from `ai-stp help --agent --json`"
    If `help --agent` disagrees with a flag on this page, the CLI wins.
    Optional flags are not listed here. Read them from the descriptor.
