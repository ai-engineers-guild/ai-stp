---
title: "Sign-in"
description: "Start and finish a platform sign-in, inspect the session, log out, and print canonical web links."
---

# Sign-in

Local work does not need an account. Sign-in is for private objects,
synchronisation, publication, devices on the website, and grants. The
CLI starts a device-code flow, prints the code a person must approve,
and stores credentials only after that approval.

`link web` sits on this page because it is the round-trip between a
catalog object and the website. It does not sign you in. It is a read.

## Commands

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp auth login` | `apply` | `none` | Start a sign-in and report the code the user must approve. |
| `ai-stp auth complete` | `apply` | `none` | Finish the pending sign-in once the user has approved it. |
| `ai-stp auth logout` | `apply` | `none` | End the cloud session on the server and here, keeping all local data. |
| `ai-stp auth status` | `read` | `none` | Report the platform relationship: local-only, authenticated, expired or revoked. |
| `ai-stp link web` | `read` | `none` | Print a canonical web URL and round-trippable CLI reference. |

`auth login` records a pending authorization, which is durable state.
`auth complete` stores credentials and re-owns local passports. There is
no `--confirm` on either: the decision is the user's approval in the
browser, which is the whole point of the flow.

## Typical path

You need a device identity first. Then:

```bash
ai-stp device init --json
ai-stp auth status --json
ai-stp auth login --provider github --json
```

`--provider` is required. The declared choices are `github` and
`google`.

The login envelope names `user_code`, `verification_uri`, and
`verification_uri_complete`. Open the URI, approve the code, then:

```bash
ai-stp auth complete --json
ai-stp auth status --json
```

`auth complete` does not wait forever for a person. If the approval has
not happened yet, it refuses and you ask again. A machine caller polls
itself. Do not wrap the command in a sleep loop that ignores
`retryable`.

To end the session later, keeping the local registry and passports:

```bash
ai-stp auth logout --json
ai-stp auth status --json
```

To point a person at the website for one catalog object:

```bash
ai-stp link web --kind component --id <stable_id> --json
```

`--kind` and `--id` are required. `--kind` is `component`, `setup`, or
`publisher`.

## `auth login`

Start a sign-in and report the code the user must approve.

```bash
ai-stp auth login --provider github --json
```

The result is the first half of the answer, not a session. No secret is
representable here. The device code the client polls with is kept in
the credential store, not published: it is the bearer of the pending
authorization.

Successful `data` names:

| Field | What it is |
| --- | --- |
| `provider` | `github` or `google` |
| `user_code` | the code the person types or confirms |
| `verification_uri` | the approval page |
| `verification_uri_complete` | the same page with the code already attached |
| `expires_in` | how long this pending authorization lasts |
| `device_id` | the device that will hold the session |
| `browser_opened` | whether a desktop browser was opened |
| `schema_version` | the schema major of this report |

`next_actions` names `auth complete` and `auth status`.

## `auth complete`

Finish the pending sign-in once the user has approved it.

```bash
ai-stp auth complete --json
```

On success the result is an auth status, not another device-approval
object. Local passports that were owned by the minted local account
are re-owned by the server account as a revision.

If the person declined, the code is `AI_STP_AUTHORIZATION_DECLINED`.
If the pending authorization expired, the code is
`AI_STP_AUTHORIZATION_EXPIRED`. Start again with `auth login`. If
nothing is pending, the code is `AI_STP_NOT_FOUND`.

## `auth logout`

End the cloud session on the server and here, keeping all local data.

```bash
ai-stp auth logout --json
```

Logout is not `device reset`. The device identity stays. Cached catalog
bytes stay. Passports stay. The session ends. Afterwards `auth status`
reports `local_only`.

## `auth status`

Report the platform relationship: local-only, authenticated, expired or
revoked.

```bash
ai-stp auth status --json
```

This is a read. It creates no identity and no session.

Successful `data` names:

| Field | What it is |
| --- | --- |
| `state` | `local_only`, `authenticated`, `expired`, or `revoked` |
| `account_id` | the account when there is one, otherwise `null` |
| `expires_at` | when the session expires, or `null` |
| `credential_store` | where the session secret is kept, or `null` |
| `schema_version` | the schema major of this report |

`local_only` is the ordinary state of a machine that never signed in.
It is not an error. Catalog search still works. Device init still
works.

`expired` means the credentials were here and are no longer valid.
`revoked` means the device is no longer trusted by the account.
Neither is repaired by repeating `auth complete` without a new login.

## `link web`

Print a canonical web URL and round-trippable CLI reference.

```bash
ai-stp link web --kind component --id <stable_id> --json
```

This is a read. It does not open a browser, does not sign you in, and
does not fetch the object. It projects one identity into a web URL and
a CLI command that names the same object.

Successful `data` names:

| Field | What it is |
| --- | --- |
| `web_url` | the canonical website URL |
| `cli_command` | a CLI invocation that names the same target |
| `cli_argv` | the same invocation as an argument list |
| `target` | `kind`, `stable_id`, and optional `version`, `locale`, `intent` |

`--kind` is `component`, `setup`, or `publisher`. A publisher `id` is
an `account_…`. Optional flags for version, locale, and the report
action exist in machine help; they are not required, so they are not
copied here.

## What a successful envelope contains

`auth login` returns the device-approval fields above. `auth complete`,
`auth logout`, and `auth status` return the auth-status fields above.
`link web` returns the deep-link fields above.

Every envelope also carries `ok`, `warnings`, `next_actions`,
`request_id`, `operation_id`, and `schema_version`.

## What these commands never do

- print a refresh token, access token, or the pending device code;
- delete local passports, the registry, or cached bytes on logout;
- create a device identity (`device init` does that);
- wait unbounded for a person to walk to a browser;
- write a harness target;
- treat a website URL as permission to install.

## Typical refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` on `auth login` | `--provider` missing or not `github`/`google` | pass `--provider github` or `--provider google` |
| `AI_STP_NOT_FOUND` on `auth complete` | nothing is pending | `ai-stp auth login --provider github --json` |
| `AI_STP_AUTHORIZATION_DECLINED` | the person declined in the browser | stop, or start a new login if they meant to approve |
| `AI_STP_AUTHORIZATION_EXPIRED` | the pending code timed out | start a new `auth login` |
| `state` is `expired` | the session is no longer valid | `auth login` then `auth complete`, not a retry of `complete` alone |
| `state` is `revoked` | the account no longer trusts this device | a new login; `device reset` is a separate, destructive decision |
| `AI_STP_VALIDATION_ERROR` on `link web` | `--kind` or `--id` missing or malformed | pass both required options |
| `AI_STP_AUTH_REQUIRED` on a later cloud command | there is no session | sign in, or stay on local and catalog-anonymous commands |

## Related pages

| Page | Why |
| --- | --- |
| [Device](device.md) | identity that holds the session |
| [Passports](passport.md) | ownership transfer on first login |
| [Sync](sync.md) | private account stream after sign-in |
| [Web sign-in](../web/login.md) | the same approval in the browser |
| [Web account](../web/account.md) | the account the session belongs to |
| [Registry](registry.md) | anonymous catalog reads need no sign-in |
| [Access grants](grant.md) | major-line access after sign-in |
| [Quickstart for people](../quickstart/human.md) | what you can do before an account |

!!! note "Flags from `ai-stp help --agent --json`"
    If `help --agent` disagrees with a flag on this page, the CLI wins.
    Optional flags are not listed here. Read them from the descriptor.
    `auth login` requires `--provider`. `link web` requires `--kind` and
    `--id`.
