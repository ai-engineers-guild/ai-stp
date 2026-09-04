---
title: "Access"
description: "Grants and invitations on the website."
---

# Access

Access is the signed-in workspace for invitations and major-line
grants you own. A grant covers one major line of one object. It never
opens the next major automatically.

Local copies on a grantee's machine may remain after revoke. Revoke is
forward-only.

## URLs and who can see them

| Projection | URL | Who can see it |
| --- | --- | --- |
| Human | `/{locale}/access` | signed-in owner |
| Machine | `/{locale}/ai/access` | same session |
| Accept | `/{locale}/invitations/{invitation_id}` | signed-in invitee |

No session → login (invitation accept keeps the invitation id in
`returnTo`). Missing CSRF on Access → session expired panel. Header
**Access** and the account menu both open the workspace.

The invitation token is **not** in the visible URL. It stays in the
tab (the accept component reads it there). Opening the email link
again is the recovery if the tab lost it.

## What this screen is for

Use Access to:

- invite someone by verified email to one exact major line;
- grant directly to a GitHub username or a user id;
- list pending invitations and active grants;
- revoke a pending invitation or an active grant.

Use the CLI when you need `--confirm` envelopes, environment-variable
tokens, or automation. The website is the same decisions with a form.

Access does **not**:

- grant “all my objects”;
- extend a grant to `major+1` when you release it;
- delete bytes on the grantee's disk;
- replace `author_verified`;
- accept an invitation on this page (that is `/invitations/…`).

## What is on the screen

### Create invitation / direct grant

| Field | Label | Values |
| --- | --- | --- |
| Recipient identifier | Recipient email / GitHub username / User ID | selects the kind |
| Value | the same label as the selected kind | required |
| Object kind | component / setup | `component` or `setup` |
| Stable id | Stable id | the object ULID |
| Major line | Major line | integer, default `1` |
| Submit | Create invitation | disabled until recipient and stable id are set |

Email recipients create an **invitation**. GitHub username and user id
create a **direct grant**.

### Lists

**Invitations** empty: **No invitations.** Each row: invitation id,
kind, `stable_id`, major, state, expires. **Revoke** asks:

> Revoke is forward-only. Local copies may remain on devices. Continue?

**Grants** empty: **No grants.** Each row: grant id, kind, `stable_id`,
major, grantee account id, revoked at. Revoke uses the same warning
plus an optional **Reason**.

A mutation reference id is shown after a successful POST so you can
correlate logs. It is not a secret.

### Accept invitation

`/{locale}/invitations/{invitation_id}`:

| Element | Copy |
| --- | --- |
| Title | Accept invitation |
| Subtitle | The token stays in this tab only. It is not in the visible URL. |
| Button | Accept invitation |
| Missing token | No invitation token in this tab. Open the link from the email again. |
| Need sign-in | Sign in before accepting an invitation. |

Human / Machine: machine Access lists invitations and grants as
fields (`invitation_id`, `object_kind`, `stable_id`, `major`,
`grantee_account_id`). Machine accept prints the invitation id.

## Matching CLI commands

```bash
ai-stp grant list --json
ai-stp grant invite --json
ai-stp grant direct --json
ai-stp grant accept --json
ai-stp grant invitation revoke --confirm --json
ai-stp grant revoke --confirm --json
ai-stp owner objects --json
```

`grant list` is the twin of this page. `grant invite` is email.
`grant direct` is an explicit account identifier. `grant accept`
reads a token from a **named environment variable** — do not put the
token on the command line and do not paste it into a passport.
Revoke commands are `destructive` and need `--confirm`.

## Dead-ends

| What you see | What it means | What to do |
| --- | --- | --- |
| Redirect to login | no session | sign in; returnTo kept |
| Session expired on Access | no CSRF | sign in again |
| Create disabled | missing recipient or id | paste `stable_id` from Objects |
| Revoke cancelled | you dismissed confirm | no change |
| Missing token on accept | tab lost the secret | open the email link again |
| Could not accept | expired, revoked, or wrong user | ask the owner to invite again |
| Grantee still has files | forward-only revoke | expected; local bytes remain |
| Next major still closed | grants do not auto-advance | invite `major` `2` explicitly |
| Kind typo 404 | only component/setup | fix the object kind |

Never put invitation tokens, emails of other people, or access reasons
that contain secrets into catalog text.

## Email invite versus direct grant

| Recipient kind | Server action | Invitee next step |
| --- | --- | --- |
| verified email | invitation | open the mail link → `/invitations/{id}` |
| GitHub username | direct grant | already granted; no token |
| user id | direct grant | already granted; no token |

Accept in the CLI reads the token from a **named environment
variable**. Accept on the website keeps the token in the tab. Both
refuse a token in the query string.

Major is an integer line, not an `X.Y`. Granting `1` covers `1.0` and
`1.4`; it does not cover `2.0`. Copy `stable_id` from Objects; typing
a display name fails.

Machine Access is the lists. Create and revoke stay human POSTs with
CSRF.

## Related pages

- [Objects](objects.md) — copy `stable_id` and kind.
- [Sign-in](login.md) — required before accept.
- [Reports](reports.md) — a different signed-in form.
- [CLI grants](../cli/grant.md) — flags and `--confirm`.
- [Owner](../cli/owner.md) — which majors you actually own.
- [Trust and safety](../trust-and-safety/index.md) — access ≠ verified.

!!! warning "Major lines"
    A grant for `1.x` does not become a grant for `2.x`. Releasing a
    new major is a new access decision.
