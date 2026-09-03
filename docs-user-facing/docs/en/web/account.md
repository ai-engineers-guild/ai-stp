---
title: "Account"
description: "Account identity, linked providers, and privacy controls."
---

# Account

Account is the signed-in identity page: the account id, linked Google
and GitHub identities, shortcuts to the public profile, and privacy
flags. It is not the publisher page visitors see, and it is not a
developer passport.

## URLs and who can see them

| Projection | URL | Who can see it |
| --- | --- | --- |
| Human | `/{locale}/account` | signed-in, onboarding complete |
| Machine | `/{locale}/ai/account` | same session |
| Human privacy | `/{locale}/account/privacy` | signed-in |
| Machine privacy | `/{locale}/ai/account/privacy` | same session |

No session → login with `returnTo` set. `onboarding_pending` →
[Onboarding](onboarding.md). The account menu (shortcut `P`) opens
this page when signed in, and Sign-in when not.

Machine Account prints `account_id` and each identity as fields. It
does not expose the cookie.

## What this screen is for

Use Account to:

- copy `account_id` (the publisher id on catalog cards);
- unlink a spare OAuth identity, or link the missing one;
- open the public profile editor;
- open privacy flags and cookie settings;
- sign out of the browser session.

Account does **not**:

- edit display name (that is [Profile](profile.md));
- list devices (that is [Devices](devices.md));
- list owned components (that is [Objects](objects.md));
- delete the account from this page;
- write a harness or a passport.

## What is on the screen

| Element | Label | Effect |
| --- | --- | --- |
| Account id | Account id | copy control |
| Public profile | Edit profile | `/{locale}/account/profile` |
| | View public profile | `/{locale}/publishers/{account_id}` |
| Sign-in methods | provider, display name, linked at | one row per identity |
| Unlink | Unlink | refused if it is the last identity |
| Link another provider | Continue with Google / GitHub | step-up `/v1/auth/link/{provider}` |
| Privacy | Privacy settings | `/{locale}/account/privacy` |
| Sign out | Sign out | POST `/api/auth/logout?locale=…` |

Unlink last identity is blocked:

> You cannot unlink the last identity on the account.
> At least one identity must stay linked so you can sign in again.

Link another provider is **not** a merge. If that Google or GitHub
identity already belongs to a different account, login/link returns
conflict and no merge is performed.

### Privacy

`/{locale}/account/privacy`:

| Flag | Label | Meaning |
| --- | --- | --- |
| `show_profile_publicly` | Show profile publicly | visitors may see the rich profile |
| `allow_publisher_listing` | Allow publisher listing | the account may appear in publisher lists |

**Save preferences** writes those two flags. They do not hide already
published catalog objects. They do not change `author_verified`.

Cookie settings on the same page reopen the consent banner:
Necessary (always on), Analytics, Marketing.

Human / Machine switch keeps `/account` vs `/account/privacy`.

## Matching CLI commands

```bash
ai-stp auth status --json
ai-stp auth logout --json
ai-stp link web --json
ai-stp owner objects --json
```

`auth status` reports the platform relationship for **this CLI
device**, which may differ from the browser cookie. `auth logout`
ends the cloud session on the server and on that device, keeping
local data. Signing out in the browser does not run `device reset`.

There is no `ai-stp account privacy` command. Visibility flags are
website POSTs.

## Dead-ends

| What you see | What it means | What to do |
| --- | --- | --- |
| Redirect to login | no or stale session | sign in |
| Redirect to onboarding | legal revisions not accepted | [Onboarding](onboarding.md) |
| Unlink last blocked | one identity must remain | link the other provider first |
| Link conflict | identity belongs elsewhere | use that account; no merge |
| Could not unlink | API refusal | refresh; check CSRF |
| Public profile 404 | privacy empty / unpublished | publish from Profile, or ignore |
| The service is temporarily unavailable | API down | retry; CLI `auth status` is local-ish |
| Signed out but CLI still authenticated | two sessions | `ai-stp auth logout --json` on the device |

Revoking the **current** browser device on the Devices page also signs
you out. That is a device revoke, not this Sign out button.

## Identities and sessions

The product allows Google and GitHub. Zero identities cannot occur on
an active account: OAuth created the first one. Two is the maximum.

| You want to | Use |
| --- | --- |
| Stop this browser only | Sign out on this page |
| Stop this browser as a cloud device | Revoke current on [Devices](devices.md) |
| Stop the CLI cloud session | `ai-stp auth logout --json` |
| Retire the local CLI identity | `ai-stp device reset --confirm --json` |
| Hide the publisher bio | Privacy flags, then Save preferences |

`account_id` is stable. Copy it when someone needs to grant you a
major line ([Access](access.md) User ID) or when you file a report
that names a publisher. It is not a secret, but it is also not an
email.

Machine Account is read-only: id + identities. Unlink and link are
human POSTs.

## Related pages

- [Profile](profile.md) — display name, bio, avatar.
- [Publishers](publishers.md) — what visitors see.
- [Devices](devices.md) — CLI and browser sessions.
- [Sign-in](login.md) — OAuth start.
- [Onboarding](onboarding.md) — first acceptance.
- [Legal](legal.md) — privacy policy text.
- [CLI sign-in](../cli/auth.md) — `auth status` / `auth logout`.
- [Owner objects](../cli/owner.md) — server-owned inventory.

!!! note "Two sessions"
    The browser cookie and the CLI device session are siblings on one
    account. Signing out of one does not uninstall the CLI or wipe
    the local registry.
