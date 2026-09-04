---
title: "Legal"
description: "How to read the versioned policies without mixing them with author licenses."
---

# Legal

Legal pages are the versioned policies of the hosted service. Each
document is an immutable revision: title, `policy_version`,
`effective_at`, locale, and HTML rendered from the source Markdown.

They are not component SPDX licenses, not the AGPL line in the footer,
and not the content-hub changelog.

## URLs and who can see them

| Projection | URL | Who can see it |
| --- | --- | --- |
| Human | `/{locale}/legal/{slug}` | anyone, if flagged |
| Machine | `/{locale}/ai/legal/{slug}` | anyone, if flagged |

`{slug}` is one of:

| Slug | Title on the site |
| --- | --- |
| `privacy` | Privacy |
| `cookies` | Cookies |
| `service-rules` | Service rules |
| `personal-data-consent` | Personal data consent |
| `licensing` | Licensing / author content responsibility |

Any other slug 404s. Optional `?revision=` pins an audit revision.
Without it, the current public revision is shown.

These routes exist when `saas_public_pages` is on (public SaaS
profile). Self-hosted omits the footer legal columns. Cookie consent
UI can still be compiled separately.

Anyone may read a policy. Accepting **Service rules** and **Personal
data consent** as a new account is [Onboarding](onboarding.md), which
stores the exact revision ids.

Footer links (SaaS): Privacy, Cookies, Service rules, Licensing.
Onboarding also links Personal data consent.

## What this screen is for

Use Legal to read the operator's rules: what personal data is
processed, how cookies are classified, what the service permits, what
authors remain responsible for.

Use a component card's **License** field for the SPDX of that version.
Use the footer `AGPL-3.0-or-later` line for the `ai_stp` software.
Those three layers do not substitute for each other.

Legal does **not**:

- collect a new signature on every visit (onboarding does that once
  per required revision);
- let you edit policy HTML;
- show author licenses for catalog objects;
- enable analytics by itself (cookie choices are a separate banner).

## What is on the screen

Left rail: **Back to home**, then **Policies** with the five slugs.
The current slug is marked `aria-current="page"`.

Main column:

| Element | Content |
| --- | --- |
| Title | policy title from the revision |
| Note | This is the current public revision. Human and machine views carry the same policy facts. |
| Version | `policy_version` |
| Effective | `effective_at` date, or an em dash |
| Language | `en` or `ru` |
| Source Markdown on GitHub | blob URL for the file under `docs-user-facing/legal/…` |
| Policy text | rendered HTML |

Human / Machine switch keeps the slug and `revision` query. Machine
legal prints the same version, effective date, and locale as fields,
then the text.

Cookie banner (when enabled) is not this page. It offers Necessary
(always on), Analytics, Marketing, Accept all, Reject optional, Save
choices. **Privacy policy** in that banner links here to `privacy`.
Account **Privacy** also offers **Cookie settings**.

## Matching CLI commands

There is no legal CLI. Onboarding acceptance is a website POST. Cookie
choices are a website POST.

Signed-in privacy flags (profile visibility) are on Account, not here:

```bash
ai-stp auth status --json
ai-stp link web --json
```

`auth status` tells you whether the device has an account session. It
does not print policy HTML.

## Dead-ends

| What you see | What it means | What to do |
| --- | --- | --- |
| Legal 404 | unknown slug, or pages not in this profile | use the five slugs above |
| `revision` 404 | that revision is not public | drop the query to see current |
| Footer has no Legal column | `saas_public_pages` off | read the repo `LICENSE` and local policy |
| SPDX on a card ≠ this page | author license vs operator policy | read both; they answer different questions |
| Onboarding still blocks | you have not accepted the pinned revisions | open [Onboarding](onboarding.md) |
| Cookie banner returns | optional categories unset | Accept, Reject, or Save choices |

Do not paste personal data into a GitHub edit link “to correct the
policy”. The source is reviewed in the repository like any other file.

## Three license layers

| Layer | Where you read it | What it covers |
| --- | --- | --- |
| Operator policies | this chapter | hosted service, personal data, cookies |
| `ai_stp` software | footer `AGPL-3.0-or-later` | the code of the product |
| Author object | catalog **License** (SPDX) | that component or setup version |

`licensing` on this site is author-content responsibility for the
hosted catalog, not a second AGPL copy. A MIT component is still
served under the operator's service rules.

Onboarding pins `service-rules` and `personal-data-consent` only.
Privacy and cookies are readable without a checkbox. Changing cookie
categories does not rewrite these Markdown revisions.

Machine legal is the same facts: version, effective date, locale,
body. An agent should cite `policy_version` and `revision`, not
paraphrase a remembered clause.

## Related pages

- [Onboarding](onboarding.md) — accepting service-rules and
  personal-data-consent revisions.
- [Account](account.md) — privacy flags and cookie settings.
- [Contact](contact.md) — a stored message, still without secrets.
- [Home](home.md) — Back to home.
- [Component card](catalog-component.md) — SPDX on an object.
- [Trust and safety](../trust-and-safety/index.md) — product trust
  model, not a policy.

!!! note "Immutable revisions"
    Onboarding records `service_rules_revision_id` and
    `personal_data_consent_revision_id`. A later policy edit is a new
    revision. Your acceptance row keeps the old ids.
