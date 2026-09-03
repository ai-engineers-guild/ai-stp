---
title: "Access grants"
description: "Invite, grant, accept, and revoke major-line access."
---

# Access grants

A grant shares one exact object **major line** with another account. It is
not a setup install, not a catalog listing, and not a passport edit. Local
bytes stay on the machines that already have them. Revocation is
forward-only.

These commands need a signed-in account. The invitation token is read from
a named environment variable. It is never a command-line flag.

## Command table

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp grant list` | `read` | `none` | invitations and major-line grants owned by the current account |
| `ai-stp grant invite` | `apply` | `explicit_flag` | create an email invitation for one exact object major line |
| `ai-stp grant direct` | `apply` | `explicit_flag` | grant one exact major line to an explicit account identifier |
| `ai-stp grant accept` | `apply` | `explicit_flag` | accept an invitation using a token from a named environment variable |
| `ai-stp grant invitation revoke` | `destructive` | `explicit_flag` | revoke one pending invitation without deleting local bytes |
| `ai-stp grant revoke` | `destructive` | `explicit_flag` | revoke one active grant forward-only while retaining local bytes |

`--json` is global. Always pass it. Every mutating command requires
`--confirm` and an `--idempotency-key`.

## List

```bash
ai-stp grant list --json
```

Success fields: `grants`, `invitations`. Each grant has `grant_id`,
`object_kind`, `stable_id`, `major`, `state`, `owner_account_id`,
`grantee_account_id`, `recipient`, `recipient_kind`, `created_at`,
`revoked_at`. Each invitation has `invitation_id`, `object_kind`,
`stable_id`, `major`, `state`, `created_at`, `expires_at`.

## Invite

```bash
ai-stp grant invite \
  --kind component \
  --id <stable_id> \
  --major 1 \
  --email user@example.com \
  --idempotency-key <key> \
  --confirm \
  --json
```

`--kind` is `component` or `setup`. `--id` is the stable object identifier.
`--major` is the exact major line. `--email` is a verified recipient
address. `--ttl-seconds` is optional; the default is seven days.
`--idempotency-key` and `--confirm` are required.

The answer is the invitation: `invitation_id`, `object_kind`, `stable_id`,
`major`, `state`, `created_at`, `expires_at`. The token is **not** in the
envelope. It is delivered out of band.

## Direct

```bash
ai-stp grant direct \
  --kind setup \
  --id <stable_id> \
  --major 1 \
  --recipient-kind github_username \
  --recipient octocat \
  --idempotency-key <key> \
  --confirm \
  --json
```

`--recipient-kind` is `github_username` or `user_id`. `--recipient` is the
value in that namespace. `--kind`, `--id`, `--major`, `--idempotency-key`,
and `--confirm` are required.

The answer is the access grant: `grant_id`, `object_kind`, `stable_id`,
`major`, `state`, `owner_account_id`, `grantee_account_id`, `recipient`,
`recipient_kind`, `created_at`, `revoked_at`.

## Accept

```bash
ai-stp grant accept \
  --invitation-id <invitation_id> \
  --token-env AI_STP_GRANT_TOKEN \
  --idempotency-key <key> \
  --confirm \
  --json
```

`--token-env` names the environment variable that holds the invitation
token. Do not pass the token as a flag. The answer is an access grant, same
shape as `direct`.

## Revoke invitation, revoke grant

```bash
ai-stp grant invitation revoke \
  --invitation-id <invitation_id> \
  --reason "issued to the wrong address" \
  --idempotency-key <key> \
  --confirm \
  --json

ai-stp grant revoke \
  --grant-id <grant_id> \
  --reason "access no longer needed" \
  --idempotency-key <key> \
  --confirm \
  --json
```

`--reason` is optional. Both answers carry `revoked` and
`local_bytes_retained`. Local bytes are retained. Revocation does not
uninstall a target.

`grant invitation revoke` and `grant revoke` are `destructive`. They are a
separate decision from listing or inviting.

## Happy path

Invite:

```text
grant list
→ grant invite --kind component --id <id> --major 1 --email <addr> --idempotency-key <key> --confirm
→ grant list
```

Accept, on the recipient's machine:

```text
# token already in the named environment variable
grant accept --invitation-id <id> --token-env AI_STP_GRANT_TOKEN --idempotency-key <key> --confirm
→ grant list
```

Direct:

```text
grant direct --kind setup --id <id> --major 1 --recipient-kind user_id --recipient <account_id> --idempotency-key <key> --confirm
```

## Named success fields

| Command | Fields to read |
| --- | --- |
| `list` | `grants`, `invitations` |
| `invite` | `invitation_id`, `expires_at`, `state` |
| `direct` / `accept` | `grant_id`, `grantee_account_id`, `major`, `state` |
| `invitation revoke` / `revoke` | `revoked`, `local_bytes_retained` |

## Refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `AI_STP_AUTH_REQUIRED` | no signed-in account | `auth login` |
| `AI_STP_USER_DECISION_REQUIRED` | `--confirm` was omitted | pass `--confirm` after reviewing kind, id, and major |
| `AI_STP_VALIDATION_ERROR` | `--idempotency-key`, `--token-env`, or `--kind` missing | read the descriptor; `--kind` is `component` or `setup` |
| `AI_STP_PERMISSION_DENIED` | this account does not own that major line | `owner objects`; you cannot grant someone else's object |
| `AI_STP_NOT_FOUND` | the invitation, grant, or object is unknown | `grant list` |
| `AI_STP_CONFLICT` | the idempotency key already names a different intent | use a new key, or reuse the key only for the same intent |
| `AI_STP_PRECONDITION_FAILED` | the invitation expired or was already revoked | `grant list`; send a new invite |
| putting the token on the command line | that option does not exist | put it in an environment variable and name the variable |

A major line is an access boundary. `--major 1` does not grant `2.x`.
Opening a new major with `component version release --major` is a different
command.

## Related links

- [Owner objects](owner.md)
- [Sign-in](auth.md)
- [Publication](publication.md)
- [Web access](../web/access.md)
- [Trust and safety](../trust-and-safety/index.md)
- [Command map](commands.md)

## Machine help is the parser

```bash
ai-stp help --agent --json
```

This page groups grant commands so a person can find them. The installed
CLI is the source of flags, schemas, and `next_actions`. If this page and
the CLI disagree, follow the CLI.
