---
description: "Public profile fields, revisions, avatar, and separation from the developer passport."
last_verified: "2026-09-04"
---

# Public profile

The decision owners are `ADR-0023` and `ADR-0069`; the requirements owner is
`SPEC-028` (previously `SPEC-003` / `SPEC-013` for separation from the passport).
A public profile is not a passport and is not included in the `kind` list from
`passport-envelope.md`.

## Minimal form of a published revision

```yaml
schema_version: 1
kind: public_profile
account_id: "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
display_name: "Danil"
bio: "I build agent systems."
links:
  - label: "GitHub"
    url: "https://github.com/rldyourmnd"
avatar_asset_id: null
content_digest: "sha256:…"
```

`schema_version`, `kind`, and `account_id` are required. Content fields are
optional: a profile with no populated fields means there is no public profile,
not that the catalog contains an empty card.

## Revision fields (closed list)

| Field | Constraint | Meaning |
|---|---|---|
| `display_name` | 1–80 normalized UTF-8 characters, if provided; same plain-text policy as `bio` | Display name |
| `bio` | 0–1500 normalized UTF-8 characters; Unicode letters/digits, whitespace, and basic ASCII punctuation only; no invisible/typographic characters, unsafe URIs, markup, profanity, sexual content/services, threats/violence, extremism, or military-action markers | Short description |
| `links` | 0–8 items; `label` 1–60; normalized HTTPS `url`; unique | External links |
| `avatar_asset_id` | id of a processed asset, or absent | Association with AvatarAsset |
| `content_digest` | canonical revision digest | Snapshot identity |

Prohibited-content markers are matched as complete words or explicit phrases at
word boundaries; roots and suffixes are not matched.

## Lifecycle

- `ProfileDraft` is the owner's latest unpublished revision.
- There is one published revision per account; publish atomically replaces the previous one.
- Saving a draft does not change the public projection.
- The owner's preview uses the same allowlist projection as the public route, but
  is available only to the owner and is not an anonymous URL.
- The owner route additionally returns `editable`: the canonical source of editor
  fields with `source`, `base_revision_id`, and `base_content_digest`. The source
  is the draft if one exists, otherwise the published revision, otherwise an empty
  form. This does not change the public projection and lets the client discard
  local unsaved state if the server revision has already changed.

## Avatar

- Sources: upload (`image/jpeg`, `image/png`, `image/webp`, ≤ 5 MiB) or a linked
  OAuth identity (GitHub/Google) already read by the server.
- Uploads use a bounded binary request body with the image MIME type.
- The client does not submit an arbitrary remote URL. Profile mutations resolve
  the session from the server cookie and validate the form CSRF token; the session
  token is never serialized into browser component props.
- A successful upload or provider import replaces any local preview with the
  processed URL. Provider errors retain their typed code and safe message across
  the server-action boundary.
- A provider URL never becomes the public avatar URL: the server normalizes it,
  removes EXIF, stores the processed asset in object storage, and returns a safe URL.
- Provider fetches use HTTPS image hosts belonging to the chosen provider, validate
  every redirect (at most three), and stop at 5 MiB of decoded response bytes.
  Credentials and arbitrary client URLs are never sent to the image host.
- Inputs are decoded as JPEG, PNG or WebP with at most 16,777,216 pixels.
  The first frame is oriented and resized proportionally to fit 512×512 pixels,
  then encoded as a fresh PNG without EXIF, XMP, ICC or text metadata.
  MIME mismatch, malformed images and exceeded limits are validation errors;
  HTTP and storage failures are dependency errors. The current profile stays unchanged.
- Upload/import responses carry the asset id and processed URL, never an object key.
- Asset states: `processing`, `ready`, `rejected`, `deleted`.

## Public projection (allowlist)

The public route returns only `account_id`, current `author_verified`, published
`display_name`, `bio`, `links`, a safe avatar address (if the asset is in the
`ready` state), and the list of published objects. It does not return the email
address, linked identity, draft, object key, original media source URL, or media
verification state.

## Prohibited content

The profile does not contain environment values, tools, paths, decision history,
or developer passport fields. Changing the passport does not change the profile.

## Relationship to verified

`author_verified` is stored separately (`SPEC-007`) and is not inferred from
profile completeness. The public projection reads the current value on every
request, so granting or revoking it does not require republishing the profile.
