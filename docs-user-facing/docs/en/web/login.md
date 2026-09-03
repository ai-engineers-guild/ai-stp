---
title: "Sign-in on the web"
description: "OAuth, device login, and the matching CLI commands."
---

# Sign-in on the web

Sign-in creates a browser session in a secure HttpOnly cookie. The
providers are Google and GitHub. There is no password field and no
magic-link email.

A second path links a **CLI device** to that same account: the CLI
prints a user code, you approve it on the website, the CLI completes.

## URLs and who can see them

| Projection | URL | Who can see it |
| --- | --- | --- |
| Human | `/{locale}/login` | anyone |
| Machine | `/{locale}/ai/login` | anyone |
| Device approve | `/{locale}/device-login` | signed-in to approve |
| Devices (same form) | `/{locale}/devices` | signed-in |

`returnTo` must start with `/`. Anything else is ignored and the
default landing is `/{locale}/account`. Protected pages send you here
with `returnTo` set to the path they wanted.

`reason=session_expired` shows **Your session expired. Please sign in
again.** `status=error|cancel|conflict` maps to Sign-in failed,
Sign-in was cancelled, or the identity-already-linked message.

Anyone may open `/login`. `/device-login` without a session shows
**Sign in first, then approve the device code** and a button back to
login, preserving `user_code`.

## What this screen is for

Use Sign-in to:

- start Google or GitHub OAuth for the browser;
- recover after an expired cookie;
- copy the CLI login command for a device.

Use `/device-login` or [Devices](devices.md) to type the code the CLI
printed. Use [Onboarding](onboarding.md) if the account is new and
still `onboarding_pending`.

Sign-in does **not**:

- merge two existing accounts (conflict is a refusal);
- create a local device identity (`device init` is CLI-only);
- store a provider token in localStorage;
- sign you into a harness (Claude Code / Codex / Grok Build sessions
  are unrelated).

## What is on the screen

| Control | Label | Effect |
| --- | --- | --- |
| Title | Sign in | — |
| Subtitle | Sign in with a supported provider. Session state is stored in a secure HttpOnly cookie. | — |
| Google | Continue with Google | `/v1/auth/google/login?client=web&return_to=…` |
| GitHub | Continue with GitHub | `/v1/auth/github/login?client=web&return_to=…` |
| CLI copy | Sign in a device from the CLI | `ai-stp auth login --provider github` |

In mock/e2e the buttons POST to a mock action instead of the API.
`?debug=1` with mocks adds extra error/cancel simulators. That gate is
not part of production.

OAuth is same-origin `/v1/auth/…` (rewritten to the API in
development). The callback sets the session cookie. Step-up linking of
a **second** provider on an existing account is
`/v1/auth/link/{provider}` from [Account](account.md), not this page.

### Device code

`/device-login` fields:

| Field | Label |
| --- | --- |
| User code | User code |
| Submit | Approve device |

Errors: unknown (retype), expired (run `auth login` again), resolved
(already used), csrf (reload), failed (retry). Success: **Device
approved** — return to the CLI; polling should complete.

Human / Machine: machine login lists the two providers as links and
the CLI command as a code block.

## Matching CLI commands

These are the only auth commands in the registry:

```bash
ai-stp auth login --provider github --json
ai-stp auth login --provider google --json
ai-stp auth complete --json
ai-stp auth status --json
ai-stp auth logout --json
ai-stp link web --json
```

`--provider` is required and closed to `github` and `google`.
`auth login` starts the flow and prints the code to approve.
`auth complete` finishes once you have approved. `auth status` reports
local-only, authenticated, expired, or revoked. `auth logout` ends the
cloud session and keeps local data. `link web` prints a canonical
website URL.

There is no `ai-stp auth device` command. The website hint that names
it is describing this same `auth login` code. Follow the CLI.

Device identity on the machine is separate:

```bash
ai-stp device init --json
ai-stp device show --json
```

`device init` does not sign you in. `auth login` does not create a
device. You usually need both, in that order, on a new install.

## Dead-ends

| What you see | What it means | What to do |
| --- | --- | --- |
| Sign-in failed | OAuth error | retry the same provider |
| Sign-in was cancelled | you aborted at the provider | retry or pick the other provider |
| This identity is already linked to another account | merge refused | use the account that already owns it |
| Session expired | stale cookie | sign in; `returnTo` is kept |
| Need sign-in on device-login | no browser session | sign in, code is preserved |
| Unknown code | typo | retype; do not add spaces |
| Code expired / already used | run login again | `ai-stp auth login --provider github --json` |
| Sent to onboarding | new account | accept the two revisions |
| Conflict on link | that Google/GitHub is on another account | unlink there first; no merge |

Never put the user code in a ticket, a screenshot of a public issue,
or a passport.

## Related pages

- [Account](account.md) — after a successful browser login.
- [Devices](devices.md) — list plus the same approve form.
- [Onboarding](onboarding.md) — first-time legal acceptance.
- [Home](home.md) — Sign in from the landing page.
- [CLI sign-in](../cli/auth.md) — envelopes for the same commands.
- [Device](../cli/device.md) — local identity.
- [Quickstart for people](../quickstart/human.md) — local work without an account.

??? question "Do I need Sign-in to read the catalog?"
    No. Anonymous catalog reads work in the browser and as
    `ai-stp registry search --json`. Sign-in is for likes, reports,
    devices, objects, grants, and publication confirm.
