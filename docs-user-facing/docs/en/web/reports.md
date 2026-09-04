---
title: "Reports"
description: "How a signed-in user files and lists report cases."
---

# Reports

Reports is the signed-in page for **your** cases and for submitting a
new report against one exact catalog version. Staff triage at
`/staff/reports` is not a user page and is not documented here.

A report is a closed moderation case, not a public discussion.

## URLs and who can see them

| Projection | URL | Who can see it |
| --- | --- | --- |
| Human | `/{locale}/reports` | signed-in |
| Machine | `/{locale}/ai/reports` | same session |

Catalog cards and owner version pages send you here with:

```text
?object_kind=component|setup
&stable_id=…
&version=…
&digest=…
```

Those four facts are required before the submit form renders. Opening
`/reports` bare shows your cases plus:

> Choose an exact version first, then open report with object facts
> filled.

No session → login with the query preserved in `returnTo`. Missing
CSRF → session expired. Header **Reports** and the account menu open
this page.

## What this screen is for

Use Reports to tell operators that a **specific digest** is harmful,
wrong, or a vulnerability, after you have looked at the diagnostics
preview.

Use [Contact](contact.md) when you have no digest. Use GitHub only for
repository patches. Use CLI `report preview` / `report confirm` when
you want the envelope on disk.

Reports does **not**:

- let you browse other people's cases;
- let you block or hide a version (staff only);
- send finding payloads that may contain secrets (those stay hidden
  on the catalog card);
- change `author_verified` from this form.

## What is on the screen

### Submit form (only with a complete target)

| Field | Label | Source |
| --- | --- | --- |
| Object kind | Object kind | query, `component` or `setup` |
| Stable id | Stable id | query |
| Version | Version | query |
| Content digest | Content digest | query |
| Error code | Error code | optional |
| Diagnostics | Diagnostics (optional) | max 4000 characters, in-memory until submit |
| Vulnerability | Mark as vulnerability report | checkbox |
| Preview diagnostics | Preview diagnostics | required before submit |
| Consent | I reviewed the diagnostics preview and consent to send only the fields below. | required |
| Submit | Submit report | disabled until preview + consent |

Preview hint:

> Diagnostics stay in memory until you submit. Preview and consent are
> required.

Without preview and consent the form states **Preview diagnostics and
accept consent before submit.** Success: **Report submitted.** plus a
reference id.

Do not paste tokens, private keys, `.env` files, or private repo
contents into Diagnostics. Describe the public URL and the check id
instead.

### Your cases

| Column | Content |
| --- | --- |
| Case id | `case_id` |
| Target | `object_kind / stable_id / version` |
| State | server state |

Empty: **You have no report cases yet.** This list is the reporter's
ledger. It is not the staff worklist.

Human / Machine: machine Reports lists `case_id`, kind, id, version,
state, vulnerability flag, created_at. The submit form is human-only.

## Matching CLI commands

```bash
ai-stp report preview --json
ai-stp report confirm --json
ai-stp report list --json
```

`report preview` (`plan`, confirmation `none`) prepares the exact
bounded payload without sending it. `report confirm` (`apply`,
`explicit_flag`) submits one exact preview. `report list` lists the
current account's closed cases — the twin of **Your cases**.

There is no `ai-stp report staff` command in the user CLI.

## Dead-ends

| What you see | What it means | What to do |
| --- | --- | --- |
| Choose an exact version first | missing query facts | open Report from a card or version page |
| Preview and consent required | you skipped a step | Preview, tick consent, then Submit |
| Redirect to login | no session | sign in; query is kept |
| Empty cases | you have not submitted | expected for a new account |
| Catalog hides finding payload | may contain secrets | do not demand the raw snippet |
| Contact form instead | no digest | that is the other path |
| `/staff/reports` 404 or forbidden | not a user page | stop; use this page or Contact |

A submitted case does not notify you in the catalog. Watch **Your
cases** or `report list`.

## How the query is filled

| Source | Query it writes |
| --- | --- |
| Component card Report | kind, `stable_id`, latest version, digest |
| Setup card Report setup | same for the setup |
| Owner version **Report this version** | that exact `X.Y` and digest |
| Bare `/reports` | none — form hidden |

If latest has no digest yet, the card omits `digest` and this page
refuses the form. Open `/versions/{version}` and report from there.

Diagnostics are optional and capped. Preview is not a send. Consent
names the fields you actually post. Mark as vulnerability when the
issue is a security finding; it is a flag on the case, not a public
CVE page.

Machine Reports is the case list. Submit stays a human form.

## Related pages

- [Catalog](catalog.md) — Report on a card.
- [Component card](catalog-component.md) — digest in the query.
- [Objects](objects.md) — Report this version as owner.
- [Contact](contact.md) — no digest.
- [CLI reports](../cli/report.md) — preview then confirm.
- [Security checks](../security-checks.md) — check ids to cite.
- [Trust and safety](../trust-and-safety/index.md) — what “unsafe”
  means here.

!!! warning "Staff is out of scope"
    If a URL contains `/staff/`, you are not on a help-center path.
    Users file cases. They do not triage them.
