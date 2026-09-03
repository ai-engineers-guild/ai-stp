---
title: "Target"
description: "Daily status, diff, backups, and the named previous version. Restores nothing."
---

# Target

Target commands are the daily view of one project-and-harness pair. They
read. They never update the target, never take a backup, and never restore
one.

`target rollback` **names** the previous confirmed version. Restoring uses
`install plan --action rollback`. Reinstalling an earlier version through
`action=update` is not the same as restoring a backup.

## Command table

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp target status` | `read` | `none` | the daily state of one project and harness |
| `ai-stp target diff` | `read` | `none` | what installing the selected version would change |
| `ai-stp target backups` | `read` | `none` | provider-owned copies this pair can restore from |
| `ai-stp target rollback` | `read` | `none` | name the exact previous verified version |

`--json` is global. Always pass it. None of these commands takes
`--confirm` or a plan digest.

## Status

```bash
ai-stp target status --project <project_id> --harness codex --json
```

`--project` is the project passport's stable id. `--harness` is required
and is one of `antigravity`, `claude-code`, `codex`, `cursor`,
`grok-build`, `opencode`, `pi`.

To read the target as it is now, pass the provider:

```bash
ai-stp target status \
  --project <project_id> \
  --harness codex \
  --provider <exe> \
  --provider-manifest <path> \
  --protocol-version 3 \
  --target <dir> \
  --json
```

`--provider-manifest` is optional: the release this pair was last verified
under is read from the journal when the named executable is its exact
bytes. Without a signed release, the read asks in v3. `--unverified-provider`
reads through an executable no signed or attested release covers. It does
not relax isolation.

`--requires-env` is repeatable. Each value is an additional uppercase
variable this target needs beyond its setup passport. Never `NAME=value`.
`--catalog-version` is the newest known version, to report catalog drift.
`--target` is required by protocol v2 and v3.

`states` is a list because a pair can be waiting to install **and** missing
a variable at once. Values: `not_selected`, `pending_install`,
`local_drift`, `catalog_drift`, `needs_configuration`, `installed`.

Success fields: `project_id`, `harness_id`, `states`, `selected_stable_id`,
`selected_version`, `installed_stable_id`, `installed_version`,
`observed_target_digest`, `verified_target_digest`, `missing_env`,
`pending_authorization`, `shadowed_by`, `catalog_version`.

## Diff

Diff answers what installing the selected version would change. It changes
nothing. Options match `status`.

```bash
ai-stp target diff \
  --project <project_id> \
  --harness codex \
  --provider <exe> \
  --protocol-version 3 \
  --target <dir> \
  --json
```

Read the managed-path changes: `modified`, `added`, `deleted`, with
`expected_digest` and `observed_digest`. An `unsafe` observed digest means
the current bytes are not treated as a content address.

## Backups

```bash
ai-stp target backups --project <project_id> --harness codex --json
```

Without `--provider`, the answer is the journal's own record. With
`--provider`, the same rows also say which copies still exist and are
held — the only way to see a copy the journal still offers and the
provider no longer has.

```bash
ai-stp target backups \
  --project <project_id> \
  --harness codex \
  --provider <exe> \
  --provider-manifest <path> \
  --protocol-version 3 \
  --target <dir> \
  --json
```

Each copy carries `backup_ref`, the operation that took it, and the setup
version installed at that moment. This command restores nothing. To restore:

```bash
ai-stp install plan \
  --action rollback \
  --backup-ref <exact> \
  --provider <exe> \
  --provider-manifest <path> \
  --protocol-version 3 \
  --target <dir> \
  --json
ai-stp install approve --operation <id> --plan-digest sha256:... --json
ai-stp install apply --operation <id> --provider <exe> --json
```

## Rollback (name only)

```bash
ai-stp target rollback --project <project_id> --harness codex --json
```

Only `--project` and `--harness`. The answer names `setup_stable_id`,
`setup_version`, `operation_id`, `verified_at`, `project_id`, `harness_id`.
It rolls nothing back.

Three differences worth holding on to:

- `target rollback` names the previous confirmed version and restores
  nothing. It answers "where would a rollback go", not "roll back".
- Reinstalling an earlier version through `install plan --action update` is
  not the same as restoring: a bundle does not contain files you never
  installed, and a backup keeps them.
- Restoring returns the target **as a whole**. A single component cannot be
  restored, and asking for that is refused.

A setup is a pinned composition, not a folder of current files. Updating one
`skill`, disabling a `hook`, or changing a `setting` is already a new
setup version.

## Happy path

Daily:

```text
target status --project <id> --harness <id>
→ target diff --project <id> --harness <id>   # if states include local_drift
→ install plan …                              # if you decide to change it
```

After a successful apply:

```text
target status --project <id> --harness <id>
→ states includes installed
```

Before a risky change:

```text
install plan --action backup … → approve --plan-digest → apply
→ target backups --project <id> --harness <id>
→ target rollback --project <id> --harness <id>   # name, not restore
```

## Named success fields

| Command | Fields to read |
| --- | --- |
| `status` | `states`, `selected_*`, `installed_*`, `missing_env`, `shadowed_by` |
| `diff` | managed-path `code`, `expected_digest`, `observed_digest` |
| `backups` | `backup_ref`, held flag, setup version at the copy |
| `rollback` | `setup_stable_id`, `setup_version`, `operation_id`, `verified_at` |

## Refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` | `--project` or `--harness` missing, or `--target` missing for v2/v3 | add the declared options |
| `AI_STP_NOT_FOUND` | that pair has no journal yet | select and install first; empty status is typed emptiness when the pair exists with nothing installed |
| `AI_STP_UNSUPPORTED_APPLY` | that harness id is not in the closed set | use a supported harness |
| treating `target rollback` as restore | it only names a version | `install plan --action rollback --backup-ref` |
| asking to restore one component | restoring is whole-target | refused; compose a new setup instead |
| `NAME=value` on `--requires-env` | the option takes a name only | pass the uppercase variable name |
| deleting backups by hand | recovery still needs them | wait until recover/resume has finished |

A running agent does not modify its own active target in place. A new setup
is checked separately; the switch happens after that check.

## Related links

- [Install](install.md)
- [Select](select.md)
- [Provider](provider.md)
- [Setups](../setups/index.md)
- [Troubleshooting](../troubleshooting/index.md)
- [Command map](commands.md)

## Machine help is the parser

```bash
ai-stp help --agent --json
```

This page groups target commands so a person can find them. The installed
CLI is the source of flags, schemas, and `next_actions`. If this page and
the CLI disagree, follow the CLI.
