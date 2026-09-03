---
title: "Sync"
description: "Preview, push, merge, and pull the private account stream."
---

# Sync

Sync moves local passport revisions to and from the private account stream.
It is not the public catalog, not Git, and not install. A preview never
changes a head. Push, merge, and pull are explicit, replay-safe writes.

Local work does not need sync. Signing in is required for these commands
because they talk to the account stream. The stream carries passport
revisions, not harness target files and not provider backups.

## Command table

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp sync preview` | `read` | `none` | preview local fast-forward, merge, or conflict without changing a head |
| `ai-stp sync push` | `apply` | `explicit_flag` | push one exact local head with a durable replay-safe event |
| `ai-stp sync merge` | `apply` | `explicit_flag` | commit a mechanically clean merge of two developer-passport heads |
| `ai-stp sync pull` | `apply` | `explicit_flag` | pull and atomically apply one bounded page from the account stream |

`--json` is global. Always pass it. Push, merge, and pull require
`--confirm`.

## Preview

```bash
ai-stp sync preview --id <stable_id> --json
```

`--id` is the stable identifier whose local heads are compared.

Success fields: `stable_id`, `state`, `head_revision_ids`,
`common_ancestor_revision_id`, `candidate_revision_id`,
`server_head_revision_id`, `affected_fields`.

`state` is the next mechanical move:

| `state` | Meaning |
| --- | --- |
| `up_to_date` | one local head, nothing to merge or push past |
| `fast_forward` | a clean descendant exists; push or pull can move the head |
| `merge` | two heads have a clean mechanical merge candidate |
| `conflict` | the server names a head this device does not hold, or fields disagree |
| `manual_resolution` | more than two local heads, or no common ancestor |

Preview does not push. A conflict is an honest report, not a crash. One
local head plus a refused push that names a server head this device does
not hold is also `conflict`, not `up_to_date`.

## Push

```bash
ai-stp sync push --id <stable_id> --confirm --json
```

`--id` and `--confirm` are required. The event is durable and replay-safe:
a second push of the same head does not create a second effect.

Success fields: `stable_id`, `state`, `processed_events`, `event_id`,
`local_revision_id`, `remote_revision_id`, `server_head_revision_id`,
`conflicting_entity_id`, `conflict_fields`.

If `state` reports a conflict, stop and `preview` again. Do not push in a
loop.

## Merge

```bash
ai-stp sync merge --id <stable_id> --confirm --json
```

`--id` and `--confirm` are required. Merge commits a mechanically clean
merge of **two** developer-passport heads. It does not invent field values.
If the preview was `conflict` or `manual_resolution`, merge is refused.

The answer is a preview of the resulting heads: same schema as
`sync preview`. Push afterwards if the new head should leave this device.

## Pull

```bash
ai-stp sync pull --confirm --json
ai-stp sync pull --page-size 20 --confirm --json
ai-stp sync pull --skip-event <event_id> --confirm --json
```

`--confirm` is required. `--page-size` is the maximum events in this page.
`--skip-event` is repeatable: each value is the exact id of a refused event
to walk past, abandoning its revision. The skip is remembered by this
device, so a later pull walks past it unasked.

Success fields: `received`, `applied`, `replayed`, `next_cursor`,
`skipped`. Pull until `next_cursor` is empty if you mean to drain the
stream. Each page is atomic.

## Happy path

```text
auth status
→ sync preview --id <stable_id>
→ sync pull --confirm          # if the stream is ahead
→ sync merge --confirm         # only when preview says merge
→ sync push --id <stable_id> --confirm
→ sync preview --id <stable_id>
```

Read `preview` after every write. Do not push and pull in the same breath
without reading `state`.

## Named success fields

| Command | Fields to read |
| --- | --- |
| `preview` / `merge` | `state`, `head_revision_ids`, `candidate_revision_id`, `affected_fields` |
| `push` | `event_id`, `local_revision_id`, `remote_revision_id`, `state` |
| `pull` | `received`, `applied`, `replayed`, `next_cursor`, `skipped` |

## Refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `AI_STP_AUTH_REQUIRED` | no signed-in account | `auth login` |
| `AI_STP_DEVICE_REVOKED` | this device key is revoked for cloud operations | `device` + a new login; do not reuse the revoked key |
| `AI_STP_USER_DECISION_REQUIRED` | `--confirm` was omitted | pass `--confirm` after reading the preview |
| `AI_STP_NOT_FOUND` | that id has no local revision heads | `passport developer show` / create the object locally first |
| `AI_STP_CONFLICT` | the server head disagrees with this device | `preview`; merge only if the state is `merge` |
| `AI_STP_PRECONDITION_FAILED` | merge when heads are not a clean pair | resolve manually; do not skip events to hide it |
| `AI_STP_RATE_LIMITED` | the server asked to slow down | retry only if `retryable: true` |
| skipping an event | its revision is abandoned on this device | pass `--skip-event` only after a human refusal |

Do not put stream tokens in the command line. Do not treat sync as a backup
of a harness target. Target copies live with the provider; see
[Target](target.md).

## Related links

- [Sign-in](auth.md)
- [Passports](passport.md)
- [Device](device.md)
- [Owner objects](owner.md)
- [Command map](commands.md)

## Machine help is the parser

```bash
ai-stp help --agent --json
```

This page groups sync commands so a person can find them. The installed
CLI is the source of flags, schemas, and `next_actions`. If this page and
the CLI disagree, follow the CLI.
