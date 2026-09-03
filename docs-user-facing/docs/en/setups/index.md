---
title: "Setups"
description: "How ai_stp assembles a complete setup from exact component versions."
---

# Setups

A setup is the final configuration of one harness. It pins exact component
versions and is applied only through that harness's public provider.

A published setup version is immutable and has the form `X.Y`, not SemVer.
There is no patch number. Replacing one component, disabling a hook, or
changing a setting produces a new `X.Y`.

## Compose from catalog and external sources

`setup compose` creates one exact setup from catalog components and embedded
GitHub, package-registry, or local components. External components do not need a
catalog listing. Put the reviewed metadata and sources in a JSON manifest:

```json
{
  "schema_version": 1,
  "name": "Frontend developer",
  "description": "Playwright automation with local project checks.",
  "harness_id": "codex",
  "components": [
    {
      "source": {
        "kind": "catalog",
        "stable_id": "component_...",
        "version": "1.0",
        "passport_digest": "sha256:..."
      }
    },
    {
      "source": {
        "kind": "git",
        "repository_url": "https://github.com/example/context7",
        "tracked_ref": "main",
        "subpath": "."
      },
      "component_type": "mcp",
      "name": "Context7 MCP",
      "description": "Upstream Context7 MCP snapshot.",
      "license_spdx": "MIT",
      "redistribution_allowed": true,
      "upstream_project": "Context7"
    },
    {
      "source": {"kind": "path", "relative_path": "hooks/check"},
      "component_type": "hook",
      "name": "Project check",
      "description": "Locally authored project check.",
      "license_spdx": "LicenseRef-Proprietary",
      "redistribution_allowed": true
    }
  ]
}
```

Plan first, then pass the returned setup id, timestamp, and plan digest to apply:

```text
ai-stp setup compose plan --manifest setup.json --root . --json
ai-stp setup compose apply --manifest setup.json --root . --id <setup_id> --created-at <created_at> --expected-plan-digest <digest> --confirm --json
ai-stp setup publish plan --id <setup_id> --version 1.0 --json
```

Git refs are resolved to commits, package sources require exact versions, and
local paths stay within `--root`. Apply repeats resolution and refuses changed
bytes. Embedded members are published only inside the setup; catalog members
retain their existing publisher and identity.

## Setup update

Compose freezes a graph. Update replaces **one embedded member** with a newer
exact snapshot and creates a new immutable setup version. It does not pick a
"latest" tag for you.

```bash
ai-stp setup update plan \
  --id <setup_id> \
  --version 1.0 \
  --component-id <component_id> \
  --harness codex \
  --source git:https://github.com/example/context7 \
  --commit <40-char-sha> \
  --json

ai-stp setup update apply \
  --id <setup_id> \
  --version 1.0 \
  --component-id <component_id> \
  --harness codex \
  --source git:https://github.com/example/context7 \
  --commit <40-char-sha> \
  --expected-plan-digest <digest> \
  --confirm \
  --json
```

`--component-id` is the exact embedded identifier, never a display name.
`--source` is `git:…`, `package:ecosystem:name@version`, or `path:relative`.
A Git source may add `--commit` and `--subpath`. Catalog pins are not
rewritten by this command: change those through a new compose or a new
select confirmation.

The current setup version stays selected until you confirm a new one. Apply
creates the new `X.Y`; it does not write the harness target.

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
compatibility, access and safety checks. The assembler validates the graph
and builds the native package. The provider is the only writer of the
target. See [concepts](../concepts/index.md).

| Stage | Who is responsible | What must be visible |
| --- | --- | --- |
| Finding candidates | CLI and catalog | source, version, harness, trust line |
| Choosing the composition | user and agent | why each component was chosen |
| Checking the graph | the setup compiler | conflicts, incompatibilities, missing pieces |
| Plan to apply | provider | target diff, backup, digest |
| Applying | provider | the operation journal and status |

## Installation

Before changing the target, the provider builds a plan, takes a backup, and
applies the change only after confirmation. The commands live on
[Install](../cli/install.md): `install plan`, `install approve`,
`install apply`. Daily state of the pair is [Target](../cli/target.md).

A running agent does not modify its own active target in place. A new setup is
checked separately, and the switch happens after that check.

## Backup and rollback

If applying fails, recovery goes through the provider and the operation
journal. Do not delete backups by hand before recovery has finished.

The command path is owned by the CLI pages, not this one:

- take a copy, restore from a copy, approve and apply: [Install](../cli/install.md);
- list copies, name the previous confirmed version, read status and diff:
  [Target](../cli/target.md).

Three differences worth holding on to:

- `target rollback` **names** the previous confirmed version and restores
  nothing. It answers "where would a rollback go", not "roll back";
- reinstalling an earlier version through `action=update` is not the same as
  restoring: a bundle does not contain files you never installed, and a backup
  keeps them;
- restoring returns the target **as a whole**. A single component cannot be
  restored, and asking for that is refused.

```bash
ai-stp target backups --project <id> --harness <id> --json
ai-stp target rollback --project <id> --harness <id> --json
ai-stp install status --json
ai-stp install recover --operation <id> --json
```

??? tip "How to think about a setup version"
    A setup is not a folder of current files; it is a pinned composition. If
    you updated one `skill`, disabled a `hook` or changed a `setting`, that is
    already a new version of the setup.

Related: [Publishing](../publishing/index.md),
[Setup commands](../cli/setup.md).
