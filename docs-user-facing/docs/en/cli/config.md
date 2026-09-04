---
title: "Configuration"
description: "Create, show, validate, and change the closed CLI configuration file this installation honours."
---

# Configuration

The configuration file is the closed list of values this installation
should honour. Secrets, tokens, and cloud credentials do not live here:
they live in the operating system's secret store.

Every command on this page is copied with `--json`. `config show` is a
read. `config init`, `config set`, and `config unset` are applies. None
of them is destructive.

## Commands

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp config init` | `apply` | `none` | Create the configuration file if it is absent, and validate it either way. |
| `ai-stp config set` | `apply` | `none` | Write declared values to the configuration file. |
| `ai-stp config unset` | `apply` | `none` | Remove declared values so their defaults apply again. |
| `ai-stp config validate` | `read` | `none` | Read the configuration file and refuse it if it cannot be honoured. |
| `ai-stp config show` | `read` | `none` | Show the effective configuration and where each value came from. |

The field list is closed. An unknown key is a typed error with its path,
never a silent ignore. Writing `telemetry.enabled=true` into the file is
refused: telemetry is turned on only by [Install telemetry](telemetry.md)
consent.

## Typical path

```bash
ai-stp config init --json
ai-stp config show --json
ai-stp config validate --json
```

`config init` is idempotent: if the file already exists, the command
validates it rather than replacing it. Every field has a default, so
nothing *needs* this file to exist. Create it when you intend to change
a value, or when you want a file on disk that `doctor` can point at.

To change a declared field, then see that the source is now the file:

```bash
ai-stp config set --set search.result_limit=10 --json
ai-stp config show --json
```

To return that field to its default:

```bash
ai-stp config unset --field search.result_limit --json
ai-stp config show --json
```

`--set` and `--field` are declared options. Repeat them for several
paths. The assignment form is `path=value`. A path without `=` is
refused rather than treated as a silent no-op.

## Declared fields

These are the paths this build understands. Exact names, types, and
defaults come from `ai-stp help --agent --json` and from `config show`.

| Path | What it controls |
| --- | --- |
| `catalog.enabled` | whether the public catalog is consulted |
| `catalog.url` | base address of the platform, without the `/v1` prefix |
| `sync.enabled` | whether cloud synchronisation is on; needs sign-in |
| `registry.path` | where the local registry lives |
| `search.result_limit` | upper bound on candidates in a result |
| `projects.discovery_roots` | explicit roots searched for projects |
| `telemetry.enabled` | whether the anonymous install ping is sent |
| `telemetry.url` | where that ping would go |
| `provider.paths.<harness>` | absolute path to that harness's setup-system provider |

`<harness>` is one of `antigravity`, `claude-code`, `codex`, `cursor`,
`grok-build`, `opencode`, `pi`. An unknown harness is not a field.

`source` on each value is one of `default`, `config_file`, or
`command_argument`. “It is 20 because that is the default” and “it is 20
because you wrote 20” lead to different next actions. That is why
`config show` reports both the value and the source.

!!! note "`config show --set` is not a write"
    `config show` accepts a one-call override as `path=value`. It never
    writes the file. `config set` is the write. Do not confuse the two.

## `config init`

Create the configuration file if it is absent, and validate it either
way.

```bash
ai-stp config init --json
```

It never overwrites. Running it against an existing file validates that
file instead, which is what a caller wanting to know the file is usable
actually asks for.

## `config set`

Write declared values to the configuration file.

```bash
ai-stp config set --set search.result_limit=10 --json
```

The answer is the effective configuration afterwards, so you see both
the new value and that its source is now `config_file`. An unknown path,
a value the field cannot hold, or a secret-shaped key is refused.

Telemetry cannot be turned on this way:

```bash
ai-stp config set --set telemetry.enabled=true --json
```

That call is refused with `AI_STP_USER_DECISION_REQUIRED`. The next
action is `telemetry consent`, not another `config set`.

## `config unset`

Remove declared values so their defaults apply again.

```bash
ai-stp config unset --field search.result_limit --json
```

Unsetting a field that was never written is a successful no-op for that
path: the default already applies. Unsetting nothing at all is refused.

## `config validate`

Read the configuration file and refuse it if it cannot be honoured.

```bash
ai-stp config validate --json
```

Same reading `config show` does, without the “what would this call
override” question. Use it when you only need to know whether the file
is sound.

A file claiming a `schema_version` this build does not speak is refused
rather than read optimistically. Invalid YAML is refused. A mapping
that contains an undeclared key is refused, including a typo inside a
declared section.

## `config show`

Show the effective configuration and where each value came from.

```bash
ai-stp config show --json
```

This is a read. If the file is absent, every value is reported from
`default` and `config_path` still names where the file *would* live.

## What a successful envelope contains

All five commands return the same result shape in `data`:

| Field | What it is |
| --- | --- |
| `config_path` | where the file is, or `null` when there is no path to name |
| `values` | every declared field, each with `path`, `source`, and `value` |
| `schema_version` | the schema major of this report |

`source` is `default`, `config_file`, or `command_argument`. Path values
are folded away from the home directory in the report; that rendering
is not a different path on disk.

The envelope also carries `ok`, `warnings`, `next_actions`,
`request_id`, `operation_id`, and `schema_version`.

## What these commands never do

- store a token, password, key, or credential;
- turn telemetry on by writing `telemetry.enabled=true`;
- create a device or a passport;
- consult the catalog, even when `catalog.enabled` is true — that is
  [Registry](registry.md);
- change a harness target.

## Typical refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` “not valid YAML” | the file cannot be parsed | fix the file; do not delete it to retry `init` |
| `AI_STP_VALIDATION_ERROR` unknown path | that key is not in the closed field list | `config show --json` and use a path it names |
| `AI_STP_VALIDATION_ERROR` “nothing was set” | `config set` ran without a `path=value` | pass `--set path=value` |
| `AI_STP_VALIDATION_ERROR` “nothing was unset” | `config unset` ran without a field | pass `--field` |
| `AI_STP_USER_DECISION_REQUIRED` on `telemetry.enabled` | consent is an event, not a file value | `ai-stp telemetry consent --accept --confirm --json` or `--decline` |
| `AI_STP_VALIDATION_ERROR` schema version | the file was written by a different build | do not guess which keys still mean the same thing |

## Related pages

| Page | Why |
| --- | --- |
| [Observe](observe.md) | `doctor` reports the configuration check |
| [Install telemetry](telemetry.md) | the only way to turn the ping on |
| [Device](device.md) | identity is not a configuration field |
| [Sign-in](auth.md) | cloud credentials live in the secret store |
| [Provider](provider.md) | `provider.paths.<harness>` names the binary |
| [Project](project.md) | `projects.discovery_roots` is input to discovery |
| [Troubleshooting](../troubleshooting/index.md) | PATH and first-run failures |

!!! note "Flags from `ai-stp help --agent --json`"
    If `help --agent` disagrees with a flag on this page, the CLI wins.
    Optional flags are not listed here. Read them from the descriptor.
