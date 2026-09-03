---
title: "Your objects"
description: "Private and published objects you own, versions, and presentation edit."
---

# Your objects

Objects is the signed-in inventory of components and setups this
account owns on the server. Passports, builds, and publication plans
are created in the CLI. The website lists them, shows lifecycle, and
lets you edit **catalog presentation** for a component.

## URLs and who can see them

| Projection | URL | Who can see it |
| --- | --- | --- |
| Human list | `/{locale}/objects` | signed-in owner |
| Machine list | `/{locale}/ai/objects` | same session |
| Human object | `/{locale}/objects/{kind}/{stable_id}` | owner |
| Human version | `/{locale}/objects/{kind}/{stable_id}/versions/{version}` | owner |
| Human edit | `/{locale}/objects/component/{stable_id}/edit` | owner |
| Machine twins | `/{locale}/ai/objects/…` | same session |

`{kind}` is `component` or `setup`. Anything else 404s. A 403/404 from
the API is shown as **This object is not available to your account.**
without saying whether it exists.

Header **Objects** and account menu **My objects** open the list.

## What this screen is for

Use Objects to:

- see owned names, `stable_id`, latest version, lifecycle, visibility;
- open the public catalog card when the object is public;
- inspect versions, digests, evidence, install eligibility;
- start or resume a publication plan the CLI prepared;
- edit component bio and media (mutable presentation);
- attach regional services (mutable metadata, not the digest).

Objects does **not**:

- create a component (use `component discover` / scaffold);
- change type, name, tags, source, or version bytes;
- apply a setup to a harness;
- set `author_verified` by ticking a box.

Subtitle on the list: **Owned components and setups. Passports and
builds stay in the CLI.**

## What is on the screen

### List

Empty: **No owned objects yet. Sync or publish from the CLI first.**
Two copy blocks:

```bash
ai-stp component discover
ai-stp toolchain harnesses
```

Those are the safe first steps (no extra arguments). They do not
publish.

Each row: `object_kind`, name, `stable_id`, latest version, lifecycle
badge, visibility badge, optional Author verified / Component
verified, **View public page**, **Manage object**.

### Object detail

Back to the list. Kind, name, `stable_id`. Buttons: View public page;
for components, **Edit bio and media**.

**External services** (when the external catalog is enabled): attach
existing services or **Create service** (name, primary HTTPS URL,
country codes). Save services is mutable catalog metadata. It does
not change the version digest.

**Versions**: each line is `version`, content digest, lifecycle,
Install eligible / Install blocked. Click through to the version
page. Empty: **No versions recorded for this object.**

### Version page

| Field | Meaning |
| --- | --- |
| Lifecycle | server lifecycle_state |
| Visibility | visibility |
| Content digest | bytes of this version, or em dash |
| Author verified | independent bit |
| Component verified | independent bit |
| Install eligible / blocked | server eligibility, not a safety guarantee |

Evidence table: check, result, source, expires. Empty evidence is
allowed.

If an open publication plan exists, **Open publication plan** goes to
[Publication](publications.md). If `can_start_publication`, **Start
publication** POSTs a plan (needs CSRF and a current `device_id`).
**Report this version** pre-fills [Reports](reports.md).

Eligibility note on the page: install eligibility and trust axes come
from the server. They are not a security guarantee of the content.

### Presentation edit (component only)

These fields change only the catalog presentation. The passport,
type, name, tags, source and versions remain immutable.

| Field | Rules |
| --- | --- |
| Catalog bio | presentation Markdown |
| Media | up to five items |
| Source per item | upload, pinned GitHub raw URL, or 11-character YouTube id |
| Upload types | JPEG, PNG, WebP, GIF, MP4, WebM up to 25 MB |
| GitHub URL | `raw.githubusercontent.com` pinned to a full commit SHA |
| Alt text | required |

A local preview is not enough: the upload must finish before Save.
YouTube wants the id, not a full URL.

## Matching CLI commands

```bash
ai-stp owner objects --json
ai-stp owner object show --json
ai-stp owner version show --json
ai-stp component discover --json
ai-stp toolchain harnesses --json
ai-stp publication plan --json
ai-stp publication status --json
```

`owner objects` is the list. `owner object show` is one object and its
versions. `owner version show` is one `X.Y` plus lifecycle evidence.
Publication confirm can be CLI or website; see
[Publication](publications.md).

## Dead-ends

| What you see | What it means | What to do |
| --- | --- | --- |
| No objects yet | nothing owned on the server | discover / publish from the CLI |
| Object not available | not yours, or unknown | do not probe ids |
| No versions recorded | never released | `component version release` in the CLI |
| Install blocked | eligibility false | read evidence; do not force apply |
| Start publication missing | not allowed, no CSRF, or no device | link a CLI device; use `publication plan` |
| Media upload failed | type/size/source | fix the item; do not Save mid-upload |
| Public page 404 | not published / not visible | expected for private drafts |
| External services hidden | flag off | catalog relationships omitted |

## Related pages

- [Publication](publications.md) — confirm a plan hash.
- [Catalog](catalog.md) — public cards.
- [Profile](profile.md) — account presentation, not object media.
- [Reports](reports.md) — report this version.
- [Owner](../cli/owner.md) — the same reads in the CLI.
- [Publish a component](../cli/component-publish.md) — release `X.Y`.
- [Publication (CLI)](../cli/publication.md) — plan, attest, confirm.

!!! note "Immutable bytes, mutable shelf"
    Presentation, service links, and likes can change. The digest of
    `1.2` cannot. Readers should pin the version, not the bio.
