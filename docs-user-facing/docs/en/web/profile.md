---
title: "Profile"
description: "The public profile, preview, and what is not a passport."
---

# Profile

Profile is the editor for the public publisher page: display name,
short bio, HTTPS links, and avatar. Save keeps a private draft.
Publish updates `/{locale}/publishers/{account_id}`.

It is presentation. It is not a component passport, not
`author_verified`, and not catalog tags.

## URLs and who can see them

| Projection | URL | Who can see it |
| --- | --- | --- |
| Human editor | `/{locale}/account/profile` | signed-in owner |
| Machine editor | `/{locale}/ai/account/profile` | same session |
| Human preview | `/{locale}/account/profile/preview` | signed-in owner |
| Machine preview | `/{locale}/ai/account/profile/preview` | same session |

No session → login. Onboarding pending → onboarding. Visitors never
see this editor; they see [Publishers](publishers.md) after you
publish.

Preview is **temporary and not saved**. It renders the current draft
(or empty). It is not a second public URL.

## What this screen is for

Use Profile to control what a visitor reads on your publisher page.

Use a component's **Edit bio and media** for catalog presentation of
one object. Use `component passport update` in the CLI for declared
facts. Those three layers must not be mixed.

Profile does **not**:

- change `account_id`;
- set `author_verified` or `component_verified`;
- publish a component version;
- allow HTML or `javascript:` links in the bio;
- store more than eight HTTPS links.

## What is on the screen

Back link to [Account](account.md). Title **Public profile**. Subtitle
explains display name, short bio, links, and avatar.

| Control | Label | Rules |
| --- | --- | --- |
| Avatar | Upload photo | JPEG, PNG, or WebP up to 5 MB; square ≥ 512×512 recommended |
| | Use from GitHub / Use from Google | import from a linked identity |
| | Remove | drop the published avatar |
| Display name | Display name | public string |
| Short bio | Short bio | limited Markdown; too long or unsafe URI is refused |
| Bio view mode | Plain text / Rendered | editor vs preview of the bio |
| Links | Label + URL (HTTPS) | up to eight; Add / Remove |
| Save | Save | private draft |
| Publish | Publish | updates the public page |
| Restore currently published data | — | reloads the last published revision into the editor |
| Preview | Preview | `/{locale}/account/profile/preview` |

Status chips: Published, Draft, Not published. Hint:

> Save keeps a private draft. Publish updates the public page.

Bio Markdown allows lists, headings, emoji, tables, links, bold, and
code. HTML and unsafe URIs fail with **Bio must not contain HTML or
unsafe URIs**.

Failed save or publish shows a toast. Avatar rejection is separate
from draft save: a rejected file is not stored.

### Preview page

Banner: **Preview — temporary and not saved**. **Edit public profile**
returns to the editor. Empty draft: **Nothing to preview yet.**

Human / Machine: machine profile prints `display_name` and `bio`.
Machine preview prints the banner and the projection fields.

## Matching CLI commands

There is no profile editor in the CLI. Related reads:

```bash
ai-stp auth status --json
ai-stp link web --json
ai-stp owner objects --json
```

`link web` can print the public publisher URL after you know the
account id (copy it from Account). `owner objects` lists catalog
objects; it does not patch the bio.

Passport work stays in the CLI and is a different document:

```bash
ai-stp passport developer show --json
ai-stp component passport show --json
```

Do not paste a profile bio into a passport to “publish it harder”.

## Dead-ends

| What you see | What it means | What to do |
| --- | --- | --- |
| Redirect to login | no session | sign in |
| Avatar rejected | type, size, or scan | use JPEG/PNG/WebP ≤ 5 MB |
| Bio is too long | over the limit | shorten |
| Bio unsafe URI | HTML or `javascript:` | use HTTPS text links |
| Could not publish | no draft revision | Save first, then Publish |
| Preview empty | nothing in the draft | type a name or bio |
| Public page still old | you Saved but did not Publish | press Publish |
| Public page 404 | privacy flags hide it | [Account](account.md) privacy |
| Import from GitHub missing | that identity is not linked | link it on Account first |

Secrets do not belong in a bio. Tokens in Markdown are still tokens.

## Draft versus publish

```text
empty → Save → Draft (private)
Draft → Publish → Published (public publisher page)
Published → edit → Save → Draft ahead of the live page
Published → Restore currently published data → editor matches live
```

Visitors never see Draft. Preview is your eyes only. Privacy flags can
still hide a Published page: then the publisher URL 404s even though
the editor says Published. Fix that on Account, not here.

Links: label is human text; URL must be HTTPS. `http://` and
non-URL strings fail on save. Eight is a hard cap.

Machine profile is `display_name` and `bio` of the **editable**
record, which may be the draft. Machine preview is the projection
with the unsaved banner. Neither is a passport digest.

## Related pages

- [Account](account.md) — id, identities, privacy flags.
- [Publishers](publishers.md) — visitor view.
- [Objects](objects.md) — per-object catalog bio and media.
- [Legal](legal.md) — what the operator processes.
- [Passports](../cli/passport.md) — developer/device passports.
- [Component passport](../cli/component-passport.md) — object facts.

!!! warning "Presentation is mutable; versions are not"
    You can rewrite a bio tomorrow. You cannot rewrite a published
    `X.Y` digest. Readers should trust the version page, not the
    avatar.
