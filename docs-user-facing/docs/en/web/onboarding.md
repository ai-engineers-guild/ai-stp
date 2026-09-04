---
title: "Onboarding"
description: "What a new account confirms before it can use signed-in surfaces."
---

# Onboarding

Onboarding is the gate a new account hits after the first successful
OAuth. You must accept the current **Service rules** and **Personal
data consent** revisions before Account, Objects, Devices, or any
other private page will open.

It is not a product tour. It is not optional copy.

## URLs and who can see them

| Projection | URL | Who can see it |
| --- | --- | --- |
| Human | `/{locale}/onboarding` | signed-in, `onboarding_pending` |
| Machine | `/{locale}/ai/onboarding` | same pending session |

`returnTo` must start with `/{locale}/`. Anything else is replaced with
`/{locale}/account`.

`requireSession` on every private page redirects here while the
account status is `onboarding_pending`. `requireOnboardingSession` on
this page redirects **away** to `returnTo` once the account is
`active`. Signed-out visitors are sent to login.

`reason=required` shows a red note: both confirmations are required.

## What this screen is for

Use Onboarding to record that you read two exact policy revisions and
consent to the processing they describe.

The account stores the revision ids and the acceptance time. You can
withdraw consent later by deleting the account (not by unchecking a
box here after the fact).

Onboarding does **not**:

- publish a profile;
- link a CLI device (do that after, on [Devices](devices.md));
- skip either checkbox;
- accept “whatever the latest policy is” without pinning ids;
- appear on self-hosted builds that never create SaaS accounts the
  same way — if you never see it, you are not in this gate.

## What is on the screen

Title: **Before you continue.** Body: review the current service
rules and consent to the processing needed to operate your account.

| Control | Label | Bound revision |
| --- | --- | --- |
| Checkbox 1 | I have read and accept the Service rules. | `service_rules_revision_id` |
| Checkbox 2 | I consent to the processing described in the Personal data consent. | `personal_data_consent_revision_id` |
| Submit | Continue | both required |

The Service rules link is
`/{locale}/legal/service-rules?revision={id}`. Personal data consent
is `/{locale}/legal/personal-data-consent?revision={id}`. Opening those
pages without the query shows the current public revision, which
should match at the moment of signup.

Footer evidence sentence:

> Your account keeps the exact revision and acceptance time. You can
> withdraw consent by deleting your account.

Human / Machine: machine Onboarding is the title and body paragraph.
The checkboxes are human-only.

## Matching CLI commands

There is no onboarding CLI. After you pass the gate:

```bash
ai-stp auth status --json
ai-stp auth login --provider github --json
ai-stp device init --json
```

`auth status` should move off a pending relationship once the website
acceptance has been stored and the CLI session is completed. Do not
try to POST legal acceptance from a shell; the revision ids are
bound in this form.

## Dead-ends

| What you see | What it means | What to do |
| --- | --- | --- |
| Both confirmations are required | you submitted with a box off | tick both |
| Redirect loop to onboarding | acceptance did not stick | retry; check API availability |
| Redirect to account immediately | already `active` | you are done |
| Redirect to login | no session | sign in, then onboarding |
| Legal 404 on the link | `saas_public_pages` off or bad id | do not invent a slug; retry signup |
| Want to change a checkbox later | not an editor | read [Legal](legal.md); withdrawal is account deletion |
| CLI cloud calls refused | onboarding still pending | finish this page first |

Do not paste personal data into the checkboxes' neighbouring fields —
there are none. Do not paste policy text into a passport.

## Typical path

1. [Sign-in](login.md) with Google or GitHub for the first time.
2. OAuth callback creates the account in `onboarding_pending`.
3. Every private URL bounces here until Continue succeeds.
4. Tick both boxes. Follow the revision-pinned legal links if you
   have not read them.
5. Continue stores the two revision ids and the time.
6. You land on `returnTo` (default Account).

Cookie choices (analytics / marketing) are a **different** banner.
They are not these two checkboxes. Unchecking analytics later does
not withdraw personal-data consent; deleting the account does.

## What this gate is not

| Surface | Confused with onboarding? | Difference |
| --- | --- | --- |
| Cookie banner | sometimes | optional categories; not account creation |
| Profile publish | no | presentation, after you are `active` |
| Device approve | no | links a CLI device to an already-active account |
| Catalog experimental | no | consent for objects, not for the operator |

If a policy is revised after you accepted, your stored ids remain the
revisions you saw. The product does not silently re-bind you to a new
hash from this page.

Continue is a single POST of both flags. There is no “accept later”
queue. Closing the tab leaves the account pending: the next private
URL brings you back here.

## Related pages

- [Legal](legal.md) — the five policy slugs and immutable revisions.
- [Sign-in](login.md) — OAuth that created the pending account.
- [Account](account.md) — first private page after Continue.
- [Devices](devices.md) — link the CLI next.
- [Contact](contact.md) — questions about processing, without secrets.

!!! note "Pinned revisions"
    Acceptance is of the ids in the form, not of an unnamed “current
    policy”. A later legal edit is a new revision. Your stored ids
    stay.
