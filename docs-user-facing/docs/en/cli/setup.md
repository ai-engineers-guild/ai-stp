---
title: "Setup commands"
description: "Compose, import, update, and publish a complete setup."
---

# Setup commands

A setup is the complete configuration of one harness. It pins exact
component versions. These commands compose a mixed setup from catalog and
external sources, import a native configuration you already have, replace
one embedded member, and plan publication of the whole graph.

They do not write the harness target. Installation still goes through
[Install](install.md) and the public provider.

## Command table

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp setup compose plan` | `plan` | `none` | resolve and freeze a new setup from catalog, Git, package, and path sources |
| `ai-stp setup compose apply` | `apply` | `explicit_flag` | record the exact still-current mixed setup as one immutable local version |
| `ai-stp setup import inspect` | `read` | `none` | read one native configuration; write nothing |
| `ai-stp setup import plan` | `plan` | `none` | plan exact component and setup drafts from one native configuration |
| `ai-stp setup import register` | `apply` | `plan_digest` | register the inspected configuration as your own setup |
| `ai-stp setup update plan` | `plan` | `none` | preview replacing one embedded component with a newer exact snapshot |
| `ai-stp setup update apply` | `apply` | `explicit_flag` | confirm one exact embedded update and create a new setup version |
| `ai-stp setup publish plan` | `plan` | `none` | plan publication of one released setup with every component it pins |
| `ai-stp setup publish confirm` | `apply` | `explicit_flag` | confirm one exact reviewed publication set |

`--json` is global. Always pass it.

`compose apply` and `update apply` require **both** `--expected-plan-digest`
and `--confirm`. `import register` requires `--plan-digest` (that is the
declared name). `publish confirm` requires `--set-digest` and `--confirm`.

## Compose plan and apply

Put the reviewed metadata and sources in a JSON manifest. External
components do not need a catalog listing.

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

```bash
ai-stp setup compose plan --manifest setup.json --root . --json
```

`--manifest` is required. `--root` bounds `path:` sources. `--id` is a
setup id returned by an earlier plan, when you are re-checking the same
identity.

The plan answer carries `setup_id`, `version`, `harness_id`, `created_at`,
`definition_digest`, `plan_digest`, `members`. Each member has `stable_id`,
`version`, `source`, `embedded`.

Apply repeats resolution and refuses changed bytes. Pass the returned setup
id, timestamp, plan digest, **and** `--confirm`:

```bash
ai-stp setup compose apply \
  --manifest setup.json \
  --root . \
  --id <setup_id> \
  --created-at <created_at> \
  --expected-plan-digest sha256:... \
  --confirm \
  --json
```

Git refs are resolved to commits, package sources require exact versions,
and local paths stay within `--root`. Embedded members are published only
inside the setup; catalog members retain their existing publisher.

Success fields: `setup_id`, `version`, `created_at`, `passport_digest`,
`definition_digest`, `plan_digest`, `created`.

## Import inspect, plan, register

Import brings a native harness configuration into the local registry as
your own setup. Secret values are not stored. The target is untouched: the
provider already made the backup; register only records where it is.

```bash
ai-stp setup import inspect --root <native-dir> --harness codex --json
ai-stp setup import plan --root <native-dir> --harness codex --json
ai-stp setup import register \
  --root <native-dir> \
  --harness codex \
  --backup-ref <ref> \
  --plan-digest sha256:... \
  --json
```

`--root` and `--harness` are required on all three. Register also requires
`--backup-ref` and `--plan-digest`. `--target` names which target the
backup was taken from. `--partial` registers even though some files were
left out; the passport records the mode and the exact paths.

Inspect success fields: `root`, `harness_id`, `detection_rule`, `files`,
`redacted_keys`, `oversized`, `unreadable`. Plan fields: `plan_digest`,
`inspection_digest`, `components`, `effects`, `excluded`, `blocked_by`.
Register fields: `stable_id`, `revision_id`, `backup_id`, `component_ids`,
`plan_digest`, `redacted_keys`.

## Update plan and apply

Replace one **embedded** component with a newer exact snapshot. Catalog
pins are not updated this way.

```bash
ai-stp setup update plan \
  --id <setup_id> \
  --version 1.0 \
  --component-id <embedded_id> \
  --source git:https://github.com/example/context7 \
  --commit abcdef0123456789abcdef0123456789abcdef01 \
  --subpath . \
  --harness codex \
  --project . \
  --json
```

`--id`, `--version`, `--component-id`, `--source`, and `--harness` are
required. `--source` is an exact `git`, `package:ecosystem:name@version`,
or `path:relative` coordinate. `--commit` is the exact lowercase
40-character Git SHA. `--project` is the project root whose selected setup
is checked.

Apply repeats the same options and adds `--expected-plan-digest` and
`--confirm`:

```bash
ai-stp setup update apply \
  --id <setup_id> \
  --version 1.0 \
  --component-id <embedded_id> \
  --source git:https://github.com/example/context7 \
  --commit abcdef0123456789abcdef0123456789abcdef01 \
  --harness codex \
  --expected-plan-digest sha256:... \
  --confirm \
  --json
```

Plan fields include `plan_digest`, `setup_id`, `component_id`,
`from_version`, `to_version`, `snapshot_coordinate`, `snapshot_identity`,
`suggested_catalog_stable_id`, `suggested_catalog_version`,
`suggested_catalog_dismissible`. Apply fields: `created`, `setup_id`,
`from_version`, `to_version`, `selected_stable_id`, `selected_version`,
`plan_digest`. The result is a **new** setup version.

## Publish plan and confirm

Plan the publication of one released setup together with every component it
pins. Confirming makes that exact graph public: pinned components first,
then the setup.

```bash
ai-stp setup publish plan --id <setup_id> --version 1.0 --json
ai-stp setup publish confirm \
  --set-digest sha256:... \
  --confirm \
  --json
```

Plan needs `--id` and `--version`. Confirm needs `--set-digest` (the digest
the plan returned) and `--confirm`.

Success fields: `set_digest`, `setup_stable_id`, `setup_version`, `state`,
`expires_at`, `members`. Each member has `plan_id`, `plan_hash`, `role`,
`object_kind`, `stable_id`, `version`, `state`, `already_published`.

## Happy path

Compose:

```text
setup compose plan --manifest setup.json --root .
→ setup compose apply --manifest setup.json --root . --id … --created-at … --expected-plan-digest … --confirm
→ select session / install plan
```

Import:

```text
setup import inspect --root <dir> --harness <id>
→ setup import plan --root <dir> --harness <id>
→ setup import register --root <dir> --harness <id> --backup-ref … --plan-digest …
```

Publish the graph:

```text
setup publish plan --id <setup_id> --version <X.Y>
→ setup publish confirm --set-digest … --confirm
```

## Named success fields

| Command | Fields to read |
| --- | --- |
| `compose plan` | `setup_id`, `created_at`, `plan_digest`, `members` |
| `compose apply` | `setup_id`, `version`, `passport_digest`, `created` |
| `import inspect` | `files`, `redacted_keys`, `unreadable` |
| `import plan` | `plan_digest`, `components`, `blocked_by` |
| `import register` | `stable_id`, `backup_id`, `component_ids` |
| `update plan` | `plan_digest`, `from_version`, `to_version` |
| `update apply` | `created`, `to_version`, `selected_version` |
| `publish plan` / `confirm` | `set_digest`, `members`, `state` |

## Refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `AI_STP_USER_DECISION_REQUIRED` | `--confirm` was omitted on compose apply, update apply, or publish confirm | pass `--confirm` after reviewing the plan |
| `AI_STP_VALIDATION_ERROR` | `--expected-plan-digest`, `--plan-digest`, or `--set-digest` missing | copy the digest the plan returned |
| `AI_STP_PLAN_STALE` | Git bytes, package bytes, or local paths changed | plan again; apply refuses changed bytes |
| `AI_STP_PRECONDITION_FAILED` | import register without a provider backup, or an unbound member | take the backup through install; fix the manifest |
| `AI_STP_AUTH_REQUIRED` | publish needs a signed-in account | `auth login` |
| `AI_STP_PERMISSION_DENIED` | this account cannot publish that setup | check owner and grants |
| path outside `--root` | local sources are bounded | move the files or change `--root` |
| floating package version | package sources require an exact version | pin `name@version` |
| inventing `--expected-plan-digest` on import register | that command declares `--plan-digest` | use the declared name |

Secrets redacted at inspect stay redacted. Do not paste them back into a
passport to "complete" the import.

## Related links

- [Setups](../setups/index.md)
- [Select](select.md)
- [Install](install.md)
- [Component source](component-source.md)
- [Component publish](component-publish.md)
- [Publication](publication.md)
- [Publishing](../publishing/index.md)
- [Command map](commands.md)

## Machine help is the parser

```bash
ai-stp help --agent --json
```

This page groups setup commands so a person can find them. The installed
CLI is the source of flags, schemas, and `next_actions`. If this page and
the CLI disagree, follow the CLI.
