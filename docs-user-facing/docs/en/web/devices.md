---
title: "Devices"
description: "Devices linked to the account and how they relate to the CLI device."
---

# Devices

Devices lists browsers and CLI installations currently linked to your
account. You approve a new CLI device by typing the user code here (or
on `/device-login`). You revoke a device forward-only.

The website does not create a local device identity. That is
`ai-stp device init`.

## URLs and who can see them

| Projection | URL | Who can see it |
| --- | --- | --- |
| Human | `/{locale}/devices` | signed-in |
| Machine | `/{locale}/ai/devices` | same session |
| Device-login | `/{locale}/device-login` | signed-in to approve |

No session → login. Missing CSRF cookie → logout then login with
`reason=session_expired`. Onboarding pending → onboarding.

The account menu item **Devices** and the signed-in header nav both
land here.

## What this screen is for

Use Devices to:

- see which browsers and CLI installs can act as this account;
- approve a code printed by `ai-stp auth login`;
- revoke a lost or old device.

Devices does **not**:

- run `device init` or `device reset`;
- show the private key;
- wipe the local registry on revoke;
- approve a harness OAuth token.

Revoke stops **future cloud work** for that device. Local data is
kept. This cannot be undone from the web.

## What is on the screen

Each device card:

| Field | Label | Notes |
| --- | --- | --- |
| Name | Name | summary display name, or Web browser / CLI installation |
| State | State | e.g. active |
| Current device | Current device | this browser |
| Device type | Device type | `web` or CLI |
| Last connected | Last connected | last_active_at |
| Approximate location | Approximate location | or Unknown |
| OS / architecture | Operating system / Architecture | from CLI summary when present |
| Detected harnesses | Detected harnesses | survey, not an install |
| Toolchain profile | Toolchain profile | when published |
| Copy device id | Copy device id | clipboard |
| Revoke | Revoke | confirm dialog |

Empty list: **No devices registered.** That is unusual after a browser
login, because this browser is a device.

### Authorize a device

| Field | Label |
| --- | --- |
| Device code | Device code (`ABCD-EFGH` placeholder) |
| Confirm device | Confirm device |

Hint on the page tells you to run a CLI command then confirm the
code. The declared command is:

```bash
ai-stp auth login --provider github --json
```

(`google` is the other closed provider). There is no
`ai-stp auth device` in the registry.

Query `status=ok` shows Device approved — return to the CLI.
`status=error` asks you to check that the code is current.

Revoke current device: **You revoked the current device. You have been
signed out.** Stale eTag / conflict: refresh and decide again.

Human / Machine: machine Devices lists `device_id`, type, state,
last_active_at, location. It does not include the approve form.

## Matching CLI commands

```bash
ai-stp device init --json
ai-stp device show --json
ai-stp device reset --confirm --json
ai-stp auth login --provider github --json
ai-stp auth complete --json
ai-stp auth status --json
ai-stp auth logout --json
ai-stp passport device show --json
```

`device init` creates the local identity (idempotent). `device show`
prints where the key is kept. `device reset` is **destructive** and
needs `--confirm`; it is not a retry of `doctor`. `auth login` /
`auth complete` attach that identity to the account. `auth status`
reads the relationship. `passport device show` is the device passport
head, not this HTML list.

## Dead-ends

| What you see | What it means | What to do |
| --- | --- | --- |
| Redirect to login | no session | sign in |
| No devices registered | API returned empty | re-login in this browser |
| Unknown / expired code | typo or timeout | retype, or run `auth login` again |
| Code already used | resolved | run `auth login` again |
| Page went stale (CSRF) | reload | approve again |
| Revoke blocked (stale / conflict) | concurrent change | refresh |
| Revoke current → signed out | expected | sign in on a remaining device |
| CLI still works locally after revoke | local data kept | expected; cloud calls will fail |
| Approximate location Unknown | no geo | not an error |

Do not paste device codes or key material into chat. The code is a
one-time approval, not a password to store.

## Browser device versus CLI device

| | This tab | `ai-stp` on disk |
| --- | --- | --- |
| Type | `web` | CLI |
| Created by | OAuth cookie | `device init` |
| Linked by | login itself | `auth login` + approve code |
| Private key | session cookie | OS secret store (or file fallback) |
| Revoke on this page | signs you out if current | cloud calls stop; files remain |
| `device reset` | not applicable | new local identity; `--confirm` |

Approve the code on **either** `/devices` or `/device-login`. The CLI
polls until `auth complete` can finish. Approving twice with a spent
code is `resolved`: run `auth login` again.

Machine Devices is the list. The authorize form is human-only.

## Related pages

- [Sign-in](login.md) — OAuth and `/device-login`.
- [Account](account.md) — browser sign out without revoke.
- [CLI device](../cli/device.md) — init, show, reset.
- [CLI sign-in](../cli/auth.md) — login, complete, status, logout.
- [Passports](../cli/passport.md) — device passport refresh.
- [Quickstart](../quickstart.md) — local work before linking.

!!! note "Browser vs CLI"
    This tab is a `web` device. `ai-stp` on your laptop is a CLI
    device. Both can be linked. Revoking the CLI device does not
    uninstall `ai-stp-cli`.
