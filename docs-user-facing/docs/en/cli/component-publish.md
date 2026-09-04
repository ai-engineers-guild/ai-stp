---
title: "Publish a component"
description: "Release an X.Y version, fork, validate a skill package, and promote an embedded component."
---

# Publish a component

These commands freeze a local head as an immutable `X.Y`, copy a version
under a new identity, check a skill package against the Agent Skills
Specification, and extract one embedded setup member into an ordinary
publication plan.

None of them makes the catalog public by itself. `component publish` is a
`plan`. The public write is [Publication](publication.md) confirmation, or
[Setup](setup.md) publish confirm when the whole graph goes out together.

## Command table

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp component version list` | `read` | `none` | every recorded version, and the next minor number |
| `ai-stp component version release` | `apply` | `none` | give the current head an immutable `X.Y`; minor unless `--major` |
| `ai-stp component fork` | `apply` | `none` | copy one recorded version under a new identity |
| `ai-stp component skill validate` | `read` | `none` | name every Agent Skills Specification deviation |
| `ai-stp component publish` | `plan` | `none` | extract one embedded component into a publication plan |

`--json` is global. Always pass it.

## Version list

```bash
ai-stp component version list --id <stable_id> --json
```

Success fields: `stable_id`, `versions` (each with `version`,
`passport_digest`, `revision_id`, `created_at`), `next_minor`,
`publishable`, `publish_reason`, `forked_from`, `forked_from_version`.
`next_minor` is computed from stored history. There is no `next_major`
field: opening a major line is a decision, not a suggestion.

## Version release

Release gives the current passport head an immutable two-integer number.
The default is the next minor. `--major` opens the next major line instead.
That boolean **is** the major-line decision. There is no second `--confirm`.

```bash
ai-stp component version release --id <stable_id> --json
ai-stp component version release --id <stable_id> --major --json
```

A number, once issued, is never reused and never rewritten. The answer is
the same version-line shape as `version list`, now including the new
`X.Y`. Validate the passport before releasing if you intend to publish.

## Fork

Fork copies one recorded version under a new identity. The original is
untouched.

```bash
ai-stp component fork --id <stable_id> --version 1.0 --json
```

`--id` and `--version` are required. `--version` is the exact `X.Y` being
copied. The answer is a version line for the **new** identity:
`stable_id` (new), `forked_from`, `forked_from_version`, `versions`,
`next_minor`.

## Skill validate

Check a directory against the Agent Skills Specification. This is a read.
It names every deviation. It does not adopt, patch, or publish.

```bash
ai-stp component skill validate --path ./components/demo-skill --json
```

Success fields include `conforms`, `name`, `description`, `findings`,
`extension_directories`, `other_entries`, `packaged_as`. Each finding has
`code` (`SK000`-style), `at`, and `summary`. `conforms: false` with a list
of findings is a successful report, not a crashed command.

This is not the CLI's own Agent Skill (`ai-stp skill …`). That skill is
documented on [Agent Skill CLI](skill.md). Kind `skill` is a component.

## Component publish

Extract one **embedded** component from a local setup into the ordinary
publication plan. Catalog members already have a publisher; this command is
for a member that still lives only inside the setup.

```bash
ai-stp component publish \
  --from-setup <setup_id> \
  --setup-version 1.0 \
  --component-id <embedded_id> \
  --json
```

`--from-setup`, `--setup-version`, and `--component-id` are required.
`--component-id` is the exact embedded identifier, never a display name.
`--attestation-file` is repeatable: each path is a full locally signed
attestation bound to the promoted version.

The answer is a promotion plan: `setup_id`, `setup_version`,
`source_component_id`, `catalog_stable_id`, `catalog_version`, `plan_id`,
`plan_hash`, `state`, `reused_passport`, `still_embedded`. Confirm it with
`publication confirm --plan-id … --plan-hash … --confirm`. The embedded
member stays embedded until that confirmation finishes.

## Happy path

From a local draft:

```text
component passport validate --id <id>
→ component version release --id <id>
→ publication plan --id <id> --version <X.Y>
→ publication confirm --plan-id <plan> --plan-hash <hash> --confirm
```

From an embedded setup member:

```text
component publish --from-setup <setup> --setup-version <X.Y> --component-id <id>
→ publication status --plan-id <plan>
→ publication confirm --plan-id <plan> --plan-hash <hash> --confirm
```

For a skill package you have not adopted yet:

```text
component skill validate --path <dir>
→ component adopt --path <dir>
→ component passport validate --id <id>
```

## Named success fields

| Command | Fields to read |
| --- | --- |
| `version list` / `release` / `fork` | `stable_id`, `versions`, `next_minor`, `forked_from` |
| `skill validate` | `conforms`, `findings` |
| `publish` | `plan_id`, `plan_hash`, `catalog_stable_id`, `catalog_version`, `still_embedded` |

## Refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` | a required id, version, or path is missing | read the descriptor |
| `AI_STP_NOT_FOUND` | the object, version, or embedded member is not here | `version list` or `select graph` |
| `AI_STP_PRECONDITION_FAILED` | the passport is not ready, or an attestation is unbound | `passport validate`; sign with `attestation sign` |
| `AI_STP_AUTH_REQUIRED` | promoting to the server needs a session | `auth login`, then `component publish` again |
| `AI_STP_PERMISSION_DENIED` | this account cannot publish that object | check owner and grants |
| `conforms: false` | the skill package deviates from the specification | read each `SK…` finding; do not adopt as if it passed |
| treating `component publish` as public | it is a plan | confirm with `publication confirm` |
| inventing `--confirm` on release | release has no such flag | `--major` is the only extra decision |

A public version must come from a public GitHub repository at an exact
commit and subpath. Local-only drafts stay local until that provenance
exists.

## Related links

- [Component commands](component.md)
- [Component passport](component-passport.md)
- [Component source](component-source.md)
- [Publication](publication.md)
- [Setup commands](setup.md)
- [Publishing](../publishing/index.md)
- [Authoring](../publishing/authoring.md)
- [Security checks](../security-checks.md)
- [Agent Skill CLI](skill.md)

## Machine help is the parser

```bash
ai-stp help --agent --json
```

This page groups publish commands so a person can find them. The installed
CLI is the source of flags, schemas, and `next_actions`. If this page and
the CLI disagree, follow the CLI.
