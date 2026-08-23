---
description: "How ai_stp assembles a complete setup from exact component versions."
---

# Setups

A setup is the final configuration of one harness. It pins exact component
versions and is applied only through that harness's public provider.

## How a setup is assembled

The path, simplified:

```text
candidates from the catalog and the local registry
→ mechanical filters
→ the agent's questions
→ the user's confirmation
→ setup graph
→ deterministic compiler
→ provider plan
```

The agent helps choose what goes in, but it does not get around the
compatibility, access and safety checks.

| Stage | Who is responsible | What must be visible |
| --- | --- | --- |
| Finding candidates | CLI and catalog | source, version, harness, trust line |
| Choosing the composition | user and agent | why each component was chosen |
| Checking the graph | the setup compiler | conflicts, incompatibilities, missing pieces |
| Plan to apply | provider | target diff, backup, digest |
| Applying | provider | the operation journal and status |

## Installation

Before changing the target, the provider builds a plan, takes a backup, and
applies the change only after confirmation.

A running agent does not modify its own active target in place. A new setup is
checked separately, and the switch happens after that check.

## Rollback

If applying fails, recovery goes through the provider and the operation
journal. Do not delete backups by hand before recovery has finished.

### A deliberate rollback from a backup you took

This is a different path from recovering after a failure. Here you take a copy
of the target ahead of time, change the setup later, and return to that copy
later still.

The copy first:

```console
$ ai-stp install plan --action backup --project <id> --harness <id> \
    --provider <exe> --provider-manifest <path> --protocol-version 3 \
    --target <dir> --json
$ ai-stp install approve --operation <id> --plan-digest <exact> --json
$ ai-stp install apply --operation <id> --provider <exe> --json
```

You do not have to remember the copy afterwards — a command lists them:

```console
ai-stp target backups --project <id> --harness <id> --json
```

The answer carries the `backup_ref`, the operation that took it, and the setup
version installed at that moment. From there it is the ordinary plan, approve
and apply:

```console
$ ai-stp install plan --action rollback --backup-ref <exact> \
    --provider <exe> --provider-manifest <path> --protocol-version 3 \
    --target <dir> --json
$ ai-stp install approve --operation <id> --plan-digest <exact> --json
$ ai-stp install apply --operation <id> --provider <exe> --json
$ ai-stp target status --project <id> --harness <id> --json
```

Three differences worth holding on to:

- `target rollback` **names** the previous confirmed version and restores
  nothing. It answers "where would a rollback go", not "roll back";
- reinstalling an earlier version through `action=update` is not the same as
  restoring: a bundle does not contain files you never installed, and a backup
  keeps them;
- restoring returns the target **as a whole**. A single component cannot be
  restored, and asking for that is refused.

??? tip "How to think about a setup version"
    A setup is not a folder of current files; it is a pinned composition. If
    you updated one `skill`, disabled a `hook` or changed a `setting`, that is
    already a new version of the setup.
