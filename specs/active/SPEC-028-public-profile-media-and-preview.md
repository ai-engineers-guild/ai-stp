---
description: "SPEC-028: Author public profile, safe avatars, and preview."
last_verified: "2026-08-08"
---

# SPEC-028: Public profile, media, and preview

## Purpose

An author manages an independent public profile, sees it before publication,
and can select a verified avatar from a linked Google/GitHub identity or upload
their own. An anonymous reader sees only the published revision; drafts,
identities, and media originals are not disclosed.

## Scope

Included are a separate `PublicProfile`, draft and published revisions, an
owner-only preview, name, plain-text bio, HTTPS links, avatar, API-mediated
upload to RustFS/S3, media normalization and validation, and a public publisher
page.

Excluded are a social graph, subscriptions, comments, arbitrary profile fields,
synchronization of developer passport content, a browser setup editor, and
granting access through a profile link.

## Terms

- `PublicProfile` — an independent author object of the account, not a passport.
- `ProfileRevision` — an immutable profile snapshot; one may be published.
- `ProfileDraft` — the owner's latest unpublished revision.
- `AvatarAsset` — a processed image variant linked to a profile revision.
- `Public projection` — the exact allowlist projection of the published
  revision.

## Requirements

- `REQ-2801`: One account has at most one PublicProfile. An empty published
  profile is absent from the public catalog rather than displayed as an empty
  card.
- `REQ-2802`: Profile revision fields are strictly limited to `display_name`
  (1–80 characters), `bio` (0–1500 characters of restricted safe Markdown),
  `links` (0–8 unique normalized HTTPS URLs with labels of 1–60 characters),
  and `avatar_asset_id` or no avatar. Bio does not accept HTML or unsafe URIs.
- `REQ-2803`: The user-facing web flow does not expose a separate draft:
  `Save changes` saves the changes and makes them the current published profile
  through a server revision. The in-form preview is temporary frontend-only
  state and does not create a backend draft.
- `REQ-2804`: `GET` owner-profile, draft creation/update, preview, and publish
  are separate contract-first API scenarios. All mutations require an
  idempotency key; publication returns an operation identifier. Web does not
  synthesize a profile from account or OAuth claims.
- `REQ-2805`: Owner preview uses the same renderer and public projection as the
  anonymous publisher page but is available only to the owner. Preview clearly
  labels the draft/published state and is never indexed, given a public cache,
  or assigned a URL that works anonymously.
- `REQ-2806`: A user may select an avatar only from linked identities that the
  server has already read during the OAuth flow, or create their own
  AvatarAsset. The provider URL does not become the public avatar URL: the
  server fetches the permitted source, creates a normalized asset, and stores it
  in object storage.
- `REQ-2807`: A custom upload goes through the API with an allowlist of
  `image/jpeg`, `image/png`, and `image/webp`; the server limits size to 5 MiB
  and limits decoded pixels, removes metadata/EXIF, converts to a bounded set of
  sizes, and places the asset in quarantine until validation succeeds. A failed,
  unsupported, or oversized file never becomes publicly accessible.
- `REQ-2808`: Provider allowlists, HTTPS, a redirect limit, byte/pixel limits,
  and SSRF protection apply to URLs from OAuth. The client does not pass an
  arbitrary remote URL as an upload source.
- `REQ-2809`: The public-profile route returns only the account id, published
  profile fields, a safe address for the processed avatar, and published
  objects. It does not disclose a linked identity, email, source URL, object
  key, draft, asset original, or validation state.
- `REQ-2810`: The form shows field-level validation before submit and canonical
  API errors after submit; links are normalized by the server, and duplicates
  and non-HTTPS URLs are rejected. Removing the avatar and all fields is an
  explicit action with a preview.

## States and errors

A profile is `absent`, `draft`, `published`, or `asset_processing`; an asset is
`processing`, `ready`, `rejected`, or `deleted`. A revision conflict produces
`AI_STP_PRECONDITION_FAILED`; an invalid field produces
`AI_STP_VALIDATION_ERROR`; a foreign profile/asset produces the
indistinguishable `AI_STP_NOT_FOUND`; media dependency failure produces
`AI_STP_DEPENDENCY_UNAVAILABLE`. Repeating publish with the same key returns the
original outcome.

## Security and privacy

PublicProfile is separate from DeveloperPassport under ADR-0023. Source bytes,
quarantine, and object keys are not public. Media parsing is resource-bounded;
the public renderer escapes the bio and link labels. Audit records the actor,
revision digest, and operation id, but not an OAuth URL, source bytes, or EXIF.

## Compatibility and migration

Current seed profiles are migrated into published ProfileRevision records.
Before the public profile API exists, the `/publishers/[account]` route cannot
serve a fixture as production truth. New OpenAPI models and routes are additive;
the generated client is rebuilt only from the contract.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-2801` | An integration check proves that an account receives at most one PublicProfile and an empty profile does not enter the catalog. |
| `REQ-2802` | Contract checks accept a safe Markdown bio up to 1500 characters and reject HTML, unsafe URIs, non-HTTPS links, limit violations, and duplicates. |
| `REQ-2803` | A web check proves that the in-form preview does not write to the backend and Save changes publishes the current fields. |
| `REQ-2804` | The contract matrix checks separate owner-profile, draft, preview, and publish scenarios with an idempotency key. |
| `REQ-2805` | A browser check compares the sanitized preview with public rendering and proves owner-only access. |
| `REQ-2806`–`REQ-2808` | Storage checks cover provider import, upload, EXIF stripping, limits, SSRF, and quarantine. |
| `REQ-2807` | Upload checks cover the image MIME allowlist, size, pixels, EXIF removal, and quarantine. |
| `REQ-2809` | An access-redaction check proves the absence of identity, email, source URL, and object key. |
| `REQ-2810` | Accessible RU/EN form tests cover validation, deletion, and conflict recovery. |
