---
title: "Harness program"
description: "Install, update, remove, resume, and inspect the harness program under a prefix, not a setup."
---

# Harness program

These commands install the harness *program* — the binary under an
exact prefix — not a setup, not a component, and not the provider.
The provider is a separate binary that later writes native state.
Applying a setup is [Install](install.md). Surveying which harnesses
are visible on the machine is `toolchain harnesses`.

The subject is the program under `--prefix`, not the configuration in
`--target`. Mixing those two paths is how a setup lands in the program
directory, or a binary lands in a project.

## Commands

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp harness install` | `apply` | `none` | Install the harness program itself under an exact prefix. |
| `ai-stp harness update` | `apply` | `none` | Move the exposed harness program to the version its provider pins. |
| `ai-stp harness remove` | `destructive` | `explicit_flag` | Remove the harness program this CLI installed, and nothing else. |
| `ai-stp harness resume` | `apply` | `none` | Settle a stopped program operation by looking, never by applying again. |
| `ai-stp harness status` | `read` | `none` | What program stands under one prefix, from the journal and the disk. |

`install`, `update`, and `remove` require `--harness`, `--prefix`, and
`--target`. `remove` also requires `--confirm`. `status` requires
`--harness` and `--prefix`. `resume` requires `--operation`.

`--prefix` is the absolute directory the program lives under. It is
not the target. `--target` is the absolute harness configuration
target.

## Typical path

```bash
ai-stp toolchain harnesses --json
ai-stp harness status --harness codex --prefix <prefix> --json
ai-stp harness install --harness codex --prefix <prefix> --target <target> --json
ai-stp harness status --harness codex --prefix <prefix> --json
```

`<prefix>` and `<target>` are absolute paths. `--harness` is one of
`claude-code`, `codex`, `pi`, `opencode`, `grok-build`, `cursor`,
`antigravity`.

If an operation stopped without a settled outcome:

```bash
ai-stp harness resume --operation <operation> --json
ai-stp harness status --harness codex --prefix <prefix> --json
```

`resume` settles by looking, never by applying again. That is the same
rule as `install resume` for setups: repeating the effect is how you
get a second copy, not a recovered one.

To move to the version the provider pins:

```bash
ai-stp harness update --harness codex --prefix <prefix> --target <target> --json
```

To take back only what this CLI installed:

```bash
ai-stp harness remove --harness codex --prefix <prefix> --target <target> --confirm --json
```

## `harness install`

Install the harness program itself under an exact prefix.

```bash
ai-stp harness install --harness codex --prefix <prefix> --target <target> --json
```

The provider executable is resolved when `--provider` is omitted:
explicit path, then configuration, then the remembered choice, then
discovery. Those optional flags live in machine help. Do not invent a
provider path.

`state` after a successful apply is what the provider reported.
`verified` is the only state that says the program is installed and
its identity confirmed.

## `harness update`

Move the exposed harness program to the version its provider pins.

```bash
ai-stp harness update --harness codex --prefix <prefix> --target <target> --json
```

Same required options as install. This is not `provider update`.
Updating the provider binary is [Provider](provider.md). This moves
the *harness program* the provider exposes under the prefix.

## `harness remove`

Remove the harness program this CLI installed, and nothing else.

```bash
ai-stp harness remove --harness codex --prefix <prefix> --target <target> --confirm --json
```

Destructive. `--confirm` is required. Without it the command refuses
with `AI_STP_USER_DECISION_REQUIRED`. A program this CLI did not
install is not removed. Native configuration in `--target` is not
removed. Cached catalog bytes are not removed.

## `harness resume`

Settle a stopped program operation by looking, never by applying
again.

```bash
ai-stp harness resume --operation <operation> --json
```

`--operation` is required. It names the journal entry that stopped.
Optional asserts (`--harness`, `--prefix`, `--target`) are taken from
the operation when omitted; a different value is refused. Read those
from machine help if you need to pin them.

Resume does not download a second copy. It asks what is already on
disk and in the journal, then records the settled state.

## `harness status`

What program stands under one prefix, from the journal and the disk.

```bash
ai-stp harness status --harness codex --prefix <prefix> --json
```

Two independent sources, deliberately: the journal says what this
installation did, the filesystem says what is there now. Reporting
only the first would have called a verified operation a success on an
empty prefix.

`version` comes from the journal and never from running the program.
Asking a binary its version would execute a foreign executable from a
command declared `read`.

Successful `data` names:

| Field | What it is |
| --- | --- |
| `harness_id` | the harness you asked about |
| `prefix` | the directory you named |
| `state` | `present`, `removed`, `never_installed`, `foreign`, `lost`, or `interrupted` |
| `reason` | why that state is the report |
| `entry_point` | the exposed path under the prefix |
| `executable` | the program name as recorded |
| `version` | the version the journal recorded |
| `operation_id` | the last recorded operation, if any |
| `recorded_at` | when the journal last wrote |
| `recorded_operation` | `software_install`, `software_update`, or `software_remove` |
| `recorded_state` | what the journal last recorded |
| `stopped` | operations that stopped without a settled outcome |
| `schema_version` | the schema major of this report |

`lost` means the journal says verified and the prefix does not hold
the files. That is a report, not a prompt to install again without
reading it.

## What a successful envelope contains

`install`, `update`, `remove`, and `resume` return a program operation
in `data`:

| Field | What it is |
| --- | --- |
| `harness_id` | the harness |
| `prefix` | the program prefix |
| `operation` | `software_install`, `software_update`, or `software_remove` |
| `operation_id` | the journal entry |
| `plan_digest` | the exact plan that was carried out |
| `state` | what the provider reported after the effect |
| `version` | the program version |
| `executable` | the exposed executable |
| `artifacts` | archives the plan named |
| `effects` | what changed |
| `recovered` | what resume settled |
| `removed` | whether remove took the program back |
| `schema_version` | the schema major of this report |

`status` returns the status fields above. Every envelope also carries
`ok`, `warnings`, `next_actions`, `request_id`, `operation_id`, and
`schema_version`.

## Prefix is not target is not provider

| Path | What it is | Command |
| --- | --- | --- |
| `--prefix` | where the harness program lives | this page |
| `--target` | where native configuration lives | [Install](install.md), [Target](target.md) |
| provider executable | the binary that writes that target | [Provider](provider.md) |

`toolchain harnesses` answers “is this harness visible on the
machine”. `harness status` answers “what did this CLI put under this
prefix”. Do not use one as the other.

## What these commands never do

- apply a setup or write native configuration as the point of the
  command;
- execute the harness program to ask it its version from `status`;
- remove a program this CLI did not install;
- replace `provider update` or `toolchain install`;
- skip `--confirm` on remove.

## Typical refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` missing `--harness` / `--prefix` / `--target` | those options are required on install, update, and remove | pass all three; status needs harness and prefix |
| `AI_STP_USER_DECISION_REQUIRED` on remove | `--confirm` was missing | add `--confirm` after an explicit decision |
| `AI_STP_NOT_FOUND` on resume | that operation is not in the journal | `harness status` and read `stopped` |
| `AI_STP_PRECONDITION_FAILED` | the prefix, target, or provider does not match the plan | do not reuse argv from a different prefix |
| `state: foreign` | something else owns that prefix | do not `remove` it; this CLI did not install it |
| `state: lost` | journal verified, disk empty | read `reason`; resume or recover, do not blindly install again |
| `state: interrupted` | an operation stopped | `harness resume --operation <operation> --json` |

## Related pages

| Page | Why |
| --- | --- |
| [Toolchain](toolchain.md) | presence survey and capabilities |
| [Provider](provider.md) | the binary that writes native state |
| [Install](install.md) | applying a setup through that provider |
| [Target](target.md) | daily state of a project and harness |
| [Harnesses](../harnesses.md) | primary vs beta support |
| [Agent Skill CLI](skill.md) | the skill the program will read |
| [Quickstart](../quickstart.md) | first-run when the program is missing |

!!! note "Flags from `ai-stp help --agent --json`"
    If `help --agent` disagrees with a flag on this page, the CLI wins.
    Optional flags are not listed here. Read them from the descriptor.
    `harness install` and `harness update` require `--harness`,
    `--prefix`, and `--target`. `harness remove` also requires
    `--confirm`. `harness resume` requires `--operation`.
