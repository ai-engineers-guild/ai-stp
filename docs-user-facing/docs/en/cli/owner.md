---
title: "Owner objects"
description: "List and show server-side objects owned by the authenticated account."
---

# Owner objects

Owner commands read the server-side objects this account owns, and the
exact versions of one object. They are reads. They do not publish, grant,
or change visibility.

The public catalog shows what is already public. This group shows what
**you** own, including private versions, lifecycle evidence, and whether a
version may start publication.

A local draft from `component adopt` is not an owner object. It becomes one
when a publication has stored it on the server. Grants you received appear
under [Access grants](grant.md), not here.

## Command table

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp owner objects` | `read` | `none` | list objects owned by the authenticated account |
| `ai-stp owner object show` | `read` | `none` | read one server-authorized owned object and its exact versions |
| `ai-stp owner version show` | `read` | `none` | read one exact owned version and its server lifecycle evidence |

`--json` is global. Always pass it. None of these commands takes
`--confirm`.

## Objects

```bash
ai-stp owner objects --json
ai-stp owner objects --kind component --json
ai-stp owner objects --kind setup --page-size 20 --json
ai-stp owner objects --cursor <cursor> --json
```

`--kind` is optional: `component` or `setup`. `--cursor` is the opaque
cursor returned by the previous page. `--page-size` defaults to 20.

Success fields: `items`, `page`. Each item is an owned object summary:
stable id, kind, and name. `page` carries the next cursor when more remain.
`--page-size` is bounded; do not invent a page size outside the contract.
Walk pages until the cursor is empty. A first page with no items is typed
emptiness, not a failure.

## Object show

```bash
ai-stp owner object show --kind component --id <stable_id> --json
ai-stp owner object show --kind setup --id <stable_id> --json
```

`--kind` and `--id` are required.

Success fields: `stable_id`, `object_kind`, `name`, `versions`. Each
version summary includes `version`, `visibility` (`public` or `private`),
`trust_lane` (`authoritative` or `experimental`), `author_verified`,
`component_verified`, `content_digest`, `lifecycle_state`,
`install_eligible`, `can_start_publication`, `published_at`.

`author_verified` and `component_verified` are independent. A confirmed
author can own an unverified version. `can_start_publication` is permission
to begin a plan, not a completed publication.

`visibility` is `public` or `private` for that version. Changing visibility
is not this command. `trust_lane` on an owner view is `authoritative` or
`experimental`. `install_eligible` is a server bit for that version; local
eligibility is still `select eligibility`. `lifecycle_state` is the server
lifecycle, not the local journal of an install.

## Version show

```bash
ai-stp owner version show \
  --kind component \
  --id <stable_id> \
  --version 1.0 \
  --json
```

`--kind`, `--id`, and `--version` are required. `--version` is the exact
`X.Y`.

The answer is the full owned version plus server lifecycle evidence: the
same coordinates as the summary, with the evidence the server stored for
that exact version. Use it before `publication plan`. Compare
`content_digest` with the local passport before you plan. A mismatch means
the local head moved; release a new `X.Y` rather than republishing the old
number.

Do not expect this command to return artifact bytes. Fetch published bytes
with [Registry](registry.md) `registry fetch`. Do not expect it to return
grantees; that is `grant list`.

## Happy path

```text
auth status
→ owner objects --kind component
→ owner object show --kind component --id <id>
→ owner version show --kind component --id <id> --version 1.0
→ publication plan --id <id> --version 1.0
```

For a setup graph, the same loop with `--kind setup`, then
`setup publish plan`.

After publication:

```text
owner version show --kind component --id <id> --version <X.Y>
→ visibility public, can_start_publication no longer the next step
→ registry version --kind component --id <id> --version <X.Y>
```

## Named success fields

| Command | Fields to read |
| --- | --- |
| `objects` | `items`, `page` |
| `object show` | `stable_id`, `object_kind`, `name`, `versions` |
| `version show` | `version`, `content_digest`, `lifecycle_state`, `can_start_publication`, `author_verified`, `component_verified` |

On each version, also read `visibility`, `trust_lane`, and
`install_eligible`.

## Refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `AI_STP_AUTH_REQUIRED` | no signed-in account | `auth login` |
| `AI_STP_PERMISSION_DENIED` | this account does not own that object | you are a grantee or a catalog reader; use `registry show` |
| `AI_STP_NOT_FOUND` | the id or version is not on the server | `owner objects`; a local-only draft is not here |
| `AI_STP_VALIDATION_ERROR` | `--kind` missing on show, or `--version` missing | `--kind` is required on object and version show |
| `AI_STP_DEVICE_REVOKED` | the device key is revoked for cloud reads | new device + login |
| treating `can_start_publication` as published | it is a permission bit | still run `publication plan` then `confirm` |
| expecting `experimental` to be hidden | owner views include what you own | public catalog lanes are a different surface |

Local drafts from `component adopt` are not owner objects until they have
been published or otherwise stored on the server. `owner objects` on a
fresh account is typed emptiness.

## Related links

- [Publication](publication.md)
- [Access grants](grant.md)
- [Registry](registry.md)
- [Sign-in](auth.md)
- [Web objects](../web/objects.md)
- [Publishing](../publishing/index.md)
- [Command map](commands.md)

## Machine help is the parser

```bash
ai-stp help --agent --json
```

This page groups owner commands so a person can find them. The installed
CLI is the source of flags, schemas, and `next_actions`. If this page and
the CLI disagree, follow the CLI.
