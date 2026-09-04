---
title: "Publication on the web"
description: "Confirm a publication plan in the browser."
---

# Publication on the web

A publication plan is built in the CLI. The website shows that
immutable plan and, when it is `ready`, lets you confirm the exact
`plan_hash`. The browser does not build passports, run scanners, or
pack artifacts.

## URLs and who can see them

| Projection | URL | Who can see it |
| --- | --- | --- |
| Human | `/{locale}/publications/{plan_id}` | signed-in owner |
| Machine | `/{locale}/ai/publications/{plan_id}` | same session |

There is no publication index. You arrive from:

- [Objects](objects.md) version page **Open publication plan** or
  **Start publication**;
- the CLI printing a web link (`link web` or the plan payload).

No session → login with `returnTo` set to this plan. 404/403 →
**Publication plan not found or not available to you.** without saying
which. Onboarding pending → onboarding first.

## What this screen is for

Use this page to review the plan the server already froze, then
confirm it if the state is `ready`.

Use the CLI to create the plan, sign attestation evidence, and poll
status from a script.

The page does **not**:

- edit the passport;
- change the digest;
- transfer experimental consent to installers;
- publish “whatever is in my working tree”.

Confirmation is final for this `plan_hash`. Consent is not transferred
automatically.

## What is on the screen

Subtitle: **Review the publication plan before you confirm. The
browser does not build passports.**

| Field | Label | Meaning |
| --- | --- | --- |
| State | State | server plan state |
| Object | Object | `object_kind / stable_id / version` |
| Content digest | Content digest | bytes being published |
| Plan hash | Plan hash | the value confirm binds to |
| Policy version | Policy version | publication policy pin |
| Expires | Expires | `expires_at` |
| Effects | Effects | declared effects, or an em dash |

Evidence rows (if any): `check_id` plus `result · source`.

When `state === "ready"` and CSRF exists: **Confirm publication** with
the warning above. Pending label: **Confirming…**. After success a
mutation reference may appear; the page then refreshes to a
non-ready state.

Otherwise:

> Plan is in state {state}. Confirmation is not available.

Human / Machine: machine publication prints `plan_id`, `plan_hash`,
`policy_version`, `expires_at`, `effects`, object identity. Confirm is
human-only.

## Matching CLI commands

```bash
ai-stp publication plan --json
ai-stp publication status --json
ai-stp publication confirm --json
ai-stp attestation sign --json
ai-stp owner version show --json
ai-stp link web --json
```

`publication plan` (`plan`) creates the immutable server plan for one
exact released component version. `publication status` reads it.
`publication confirm` (`apply`, `explicit_flag`) is the CLI twin of
the button on this page. `attestation sign` (`apply`,
`explicit_flag`) signs credential-dependent test evidence with the
**active device key** — that cannot be done in the browser.

Setup publication is a different pair:

```bash
ai-stp setup publish plan --json
ai-stp setup publish confirm --json
```

Those confirm a reviewed set: pinned components, then the setup. See
[Setup commands](../cli/setup.md).

## Dead-ends

| What you see | What it means | What to do |
| --- | --- | --- |
| Plan not found or not available | bad id or not yours | start from Objects or `publication status` |
| Confirmation is not available | state ≠ `ready`, or no CSRF | wait / refresh; re-login if CSRF missing |
| Plan expired | `expires_at` passed | create a new plan in the CLI |
| Start publication missing on Objects | no device or not allowed | link a CLI device; `publication plan` |
| Evidence empty | no extra rows | still read digest and hash |
| Want to change a file | too late for this hash | new version, new plan |
| Browser “build” | does not exist | CLI only |

Do not paste `plan_hash`, attestation signatures, or device keys into
chat. Confirm binds the hash; leaking it is not a grant, but treating
it as a secret is still the right habit.

## States you will see

The confirm button exists only for `ready`. Other states are
read-only on the web:

| You need | CLI | Web |
| --- | --- | --- |
| Create the plan | `publication plan` | Start publication on a version page |
| Watch it | `publication status` | refresh this URL |
| Sign evidence | `attestation sign` | not offered |
| Confirm the hash | `publication confirm` | Confirm publication |
| Publish a setup set | `setup publish plan` / `confirm` | not this URL shape |

If the CLI and the website both confirm, the second call is a no-op
or a refusal on an already-consumed hash — do not double-click to
“make sure”. Read `publication status` after one confirm.

Machine projection is the facts an agent should quote: `plan_id`,
`plan_hash`, digest, policy version, expiry. It should not press
Confirm.

## Related pages

- [Objects](objects.md) — where Start / Open plan live.
- [Catalog](catalog.md) — the public card after a successful publish.
- [CLI publication](../cli/publication.md) — plan, attest, confirm.
- [Publish a component](../cli/component-publish.md) — release `X.Y`
  first.
- [Setup commands](../cli/setup.md) — setup publish pair.
- [Owner](../cli/owner.md) — version evidence.
- [Trust and safety](../trust-and-safety/index.md) — publication ≠
  safety guarantee.

!!! note "Hash or it did not happen"
    Confirming without reading `plan_hash` and `content_digest` is how
    a wrong version goes public. The button is not “publish latest”.
