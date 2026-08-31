---
description: "Machine contract for repository import, staff publication, and public article reads."
last_verified: "2026-08-29"
---

# Article publication

`SPEC-054` owns the behavior; `ADR-0132` owns the architectural decision. This
document owns identity, fields, API operations, and stable article publication errors.

## Identity and provenance

Article identity is the string `{type}:{slug}`. `type` accepts `article`,
`blog_post`, `changelog`, `release_notes`; `slug` matches
`^[a-z0-9]+(?:-[a-z0-9]+)*$` and is at most 120 characters long.

`source_kind` accepts `repository` or `staff` and is fixed when the Article is
created. A repository revision contains an exact 40-hex `source_ref` and a
repository-relative `source_path` below `docs-user-facing/content`; a staff revision does not
publish the actor ID.

A localized revision has `revision_id` and `content_digest`. The canonical digest
covers `type`, `slug`, `locale`, `title`, `description`, `published_at`, ordered
tags, the Markdown body, and public provenance. The active digest covers the
exact RU/EN revision identifiers of one Article.

## Shared localized entry

```text
type             = article | blog_post | changelog | release_notes
slug             = lowercase kebab-case, at most 120 characters
locale           = ru | en
title            = 1..160 characters
description      = 1..320 characters
published_at     = YYYY-MM-DD, not in the future
tags             = unique array of up to 12 items, each 1..40 characters
body             = safe Markdown, 1..200000 characters
content_digest   = canonical digest of all public revision fields
source_kind      = repository | staff
source_ref       = exact commit for repository, absent for staff
source_path      = repository-relative path for repository, absent for staff
```

Unknown request fields, duplicate tags, invalid dates, raw HTML, unsafe URLs,
and locale sets other than the exact `ru` plus `en` pair are rejected.

## Repository snapshot v1

```text
schema_version       = 1
repository           = repository ai-engineers-guild/ai-stp
commit               = exact 40-hex commit
snapshot_digest      = canonical digest of repository, commit, and sorted entries
expected_generation  = non-negative integer
entries              = at most 10000 localized entries
```

Each entry adds `source_path`. The snapshot contains only entries with
`draft=false`, is a full replacement of the repository-owned active set, and
contains no build timestamp, credential, or host path.

`GET /v1/content/repository/state` returns the current `generation`,
`snapshot_digest`, and `commit` without entries. The operation requires an
import credential.

`POST /v1/content/repository/import` accepts a snapshot. Response:

```text
schema_version   = 1
generation       = resulting generation
snapshot_digest  = accepted snapshot digest
created          = number of new localized revisions
activated        = number of changed active pointers
removed          = number of removed active pointers
unchanged        = number of unchanged active pointers
```

The same snapshot digest at the current generation returns `no_op` counts
without new revisions or jobs. An `expected_generation` mismatch returns
`AI_STP_CONTENT_STALE`.

## Staff publication v1

`PUT /v1/staff/content/{type}/{slug}` accepts:

```text
schema_version          = 1
expected_active_digest  = digest of the current RU/EN pair, or null on creation
translations            = exact object {ru, en}
```

Each translation contains `title`, `description`, `published_at`, `tags`, and
`body`. The operation creates and activates both localized revisions in one
transaction. The response contains `article_id`, `active_digest`, RU/EN
`revision_id`, and the public article representation.

`DELETE /v1/staff/content/{type}/{slug}` requires `expected_active_digest`,
unpublishes both locales, and retains the revisions. Repeating it after a
successful unpublish returns the same final result.

Both operations require a session for the current account in the staff allowlist
and create a private AuditEvent. They do not accept `source_kind`, `source_ref`,
`source_path`, or actor ID from the request.

## Public reads v1

`GET /v1/content?locale={ru|en}` returns published repository- and staff-owned
entries for one locale, sorted first by descending `published_at`, then by
ascending article identity.

`GET /v1/content/{type}/{slug}?locale={ru|en}` returns active detail or
`AI_STP_NOT_FOUND`. There is no automatic locale fallback.

The summary response contains `type`, `slug`, `locale`, `title`, `description`,
`published_at`, `tags`, `revision_id`, `content_digest`, and `source_kind`. Detail
adds the Markdown `body`; exact `source_ref` and `source_path` are added for
`repository`. The public response contains no inactive revisions, actor ID, or
audit fields.

Both responses have a public `ETag` computed from the active generation/digest
and allow `Cache-Control: public`. A conditional GET returns `304` without a body.

## Authorization

Repository state/import accepts only a separate bearer credential with the
`content_import` scope. It is not a user session and does not authorize staff
operations. Staff publication accepts only a valid session whose account ID is
in the operator staff allowlist. Public reads are anonymous.

## Stable errors

| Code | Condition |
|---|---|
| `AI_STP_CONTENT_INVALID` | Schema, limits, digest, locale parity, or safe Markdown policy is violated. |
| `AI_STP_CONTENT_SOURCE_CONFLICT` | The identity already belongs to another source owner. |
| `AI_STP_CONTENT_STALE` | Expected generation or active digest does not match. |
| `AI_STP_CONTENT_IMPORT_FORBIDDEN` | The import credential is absent, invalid, or has a different scope. |
| `AI_STP_NOT_FOUND` | The active article or requested locale is absent. |

The error response does not return the Markdown body, snapshot entries,
credential, private actor, or full request.
