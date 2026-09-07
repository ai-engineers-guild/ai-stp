---
description: "Mutable component and setup presentation in the catalog without changing the version passport."
last_verified: "2026-09-04"
---

# Object presentation

Catalog presentation belongs to the object owner and is stored separately from
the immutable passport. Changing the presentation does not create a version or change
`passport_document`, `passport_digest`, `name`, `component_type`, `tags`,
`source`, or publication state.

## Owner API

`object_kind` is `component` or `setup`.

- `GET /v1/owner/objects/{object_kind}/{stable_id}/presentation` returns the current
  presentation only to the owner;
- `PUT /v1/owner/objects/{object_kind}/{stable_id}/presentation` atomically replaces
  `bio` and the entire ordered `media` list;
- `POST /v1/owner/objects/{object_kind}/{stable_id}/presentation/media` accepts the
  author's binary upload and returns the ready media path `/v1/media/component/{id}`;
- `GET /v1/media/component/{media_id}` serves ready bytes without an object key only for a public object or its authenticated owner;
  private media is not available to anonymous callers or other accounts. Responses
  use `Cache-Control: private, no-store`. The historical `component` media path
  is an opaque locator shared by both object kinds;
- a missing object and access by another account both produce the same `404`;
- cookie-authenticated mutating routes require double-submit CSRF.

The request has `schema_version: 1`, a `bio` of up to 2000 normalized UTF-8
characters, and no more than five `media` items. Bio text accepts Unicode
letters/digits, whitespace, and basic ASCII punctuation only; invisible,
typographic, markup, unsafe-URI, profanity, sexual content/services,
threat/violence, extremism, and military-action markers are rejected.
Prohibited-content markers are matched as complete words or explicit phrases at
word boundaries; roots and suffixes are not matched.
An item contains `kind`, `url`, required `alt`, and optional
`caption`. For `youtube`, the `url` field contains an 11-character video ID. For
`image` and `video`, the following are allowed:

- upload path `/v1/media/component/{media_id}` after owner upload;
- an HTTPS URL on `raw.githubusercontent.com` pinned to an exact commit.

Upload allowlist: JPEG, PNG, WebP, GIF, MP4, WebM up to 25 MiB (REQ-3506).
Arbitrary embeds, HTML, and external hosts are prohibited.

Both detail responses expose `presentation_bio` and ready `media`.
The public catalog projection uses `bio` if the owner saved it, and otherwise
returns the current passport's `description`. An explicitly empty bio remains empty.
The search projection is refreshed atomically when presentation changes. The public media projection still
contains only items in the `ready` state.
