---
description: "Grouped component page, author media gallery, and reactions."
last_verified: "2026-08-17"
---

# SPEC-035: Component page, media, and reactions

## Purpose

The public component page must quickly explain what it is, who authored it, where
its source is, how to use the object, and how its versions changed. The author may
curate a gallery without extending the version passport or exposing object storage internals.

## Scope

The specification covers the public component detail page, separate component
media metadata, safe media delivery, aggregate likes for components and setups,
and navigation to the existing report flow. A passport editor, public comments,
arbitrary embeds, and disclosure of the list of reacting accounts are excluded.

## Terms

- `Media item` — an ordered gallery record with one permitted source.
- `Preview item` — the sole media item used as the component cover.
- `Reaction` — a private idempotent association between an account and a component or setup;
  only the aggregate is public.
- `Storage asset` — a verified object delivered through a restricted public projection.

## Requirements

- `REQ-3501`: The first screen contains the name, current version, trust and
  support labels, like count, GitHub source, and copy, like, and report actions.
- `REQ-3502`: Each fact appears in exactly one semantic section; technical
  metadata does not repeat the first screen, support, or compatibility.
- `REQ-3503`: The page shows a public author card and a separate history of
  all available versions with date, lifecycle, and a link to the immutable version.
- `REQ-3504`: The author may save up to five ordered media items and select
  exactly one preview item when the gallery is non-empty.
- `REQ-3505`: A media item has one source: an upload, a pinned raw GitHub file,
  or a YouTube video ID. Arbitrary HTML/embed is prohibited.
- `REQ-3506`: Upload accepts JPEG, PNG, WebP, GIF, MP4, or WebM up to 25 MiB.
  The worker verifies MIME/magic bytes and resource bounds and removes audio tracks
  from video before publication.
- `REQ-3507`: A GitHub source uses HTTPS, an allowlisted GitHub host, an exact
  commit SHA, and a direct file path. Fetch is protected against SSRF and redirect escape.
- `REQ-3508`: The public projection contains no object key, quarantine URL, or
  original upload URL. Storage assets are delivered using a short-lived signature.
- `REQ-3509`: The gallery preview does not start video or show controls.
  The lightbox contains native/custom controls; autoplay occurs only when the lightbox is open,
  the item is active, and the document/section is visible. Changing slides, closing, a hidden
  tab, and leaving the viewport stop playback. Reduced motion and browser
  restrictions are respected (`muted`, `playsInline`).
- `REQ-3510`: A like is an idempotent authenticated account/object reaction,
  and the public API shows only the non-negative aggregate `likes_count`.
- `REQ-3511`: The report action leads to the existing preview-first private report
  flow and does not create a public GitHub issue.
- `REQ-3512`: RU/EN, keyboard navigation, reduced motion, mobile layout, and
  labels for external/storage links are covered by web tests.
- `REQ-3513`: The authenticated component owner may change only the catalog bio
  and media from the owner workspace and public detail page. This operation does
  not change the passport, digest, name, type, tags, source, or versions; another owner's
  `stable_id` returns an indistinguishable `AI_STP_NOT_FOUND`.
- `REQ-3514`: An authenticated user sees their own reactions on a separate page,
  can navigate to it from the account menu, and can remove a reaction by repeating
  the action on the detail page. The list does not disclose other accounts' reactions.

## States and errors

Media passes through the `pending`, `ready`, `rejected`, and `deleted` states; the
public projection returns only `ready`. Errors distinguish an invalid source,
format, size, preview-invariant violation, verification failure, and storage
unavailability. A repeated like does not increase the aggregate beyond one reaction per account.

## Security and privacy

An upload is considered untrusted until MIME and magic bytes are verified. GitHub fetch
is permitted only from an allowlisted host and exact commit, with every redirect
revalidated and SSRF protection applied. Object keys, quarantine URLs, original upload URLs,
reaction account IDs, and internal moderation reasons do not enter the public projection.
Arbitrary HTML, scripts, embeds, and audio tracks are prohibited.

## Compatibility and migration

Passports and immutable object versions do not change: `media` and `reactions` are stored
as separate platform records. On rollback, the new tables and UI are disabled,
while the existing `component detail route`, `report flow`, and public projection without `media`
remain operational. Old components are displayed with an empty gallery and
a zero `likes_count`.

## Acceptance criteria

| Requirement | Executable oracle |
| --- | --- |
| `REQ-3501` | Component/E2E test finds the name, version, labels, aggregate, source, and three actions. |
| `REQ-3502` | Component test confirms that each fact appears once in its semantic section. |
| `REQ-3503` | Component/E2E test finds the author card and links for every version in the timeline. |
| `REQ-3504` | Contract/API tests reject a sixth item and a violation of the single-preview invariant. |
| `REQ-3505` | Contract tests accept the three permitted source variants and reject a mixed source/embed. |
| `REQ-3506` | Worker tests verify the format allowlist, 25 MiB boundary, magic bytes, bounds, and audio removal. |
| `REQ-3507` | Adapter tests reject non-HTTPS, a foreign host, branch ref, private address, and redirect escape. |
| `REQ-3508` | Projection tests prove redaction of internal fields and the limited lifetime of the storage URL. |
| `REQ-3509` | Browser/component test verifies no autoplay in the preview, controls and autoplay only in the active lightbox, keyboard arrows, focus trap, and Escape closing. |
| `REQ-3510` | API scenario repeats a like by one account and observes the aggregate without account IDs. |
| `REQ-3511` | E2E test completes the preview-first report route without creating a public issue. |
| `REQ-3512` | Locale parity, a11y, and desktop/mobile browser tests pass for detail and gallery. |
| `REQ-3513` | API test changes the owner's bio/media, verifies passport immutability, and rejects another account. |
| `REQ-3514` | API test verifies idempotent like, private list, and unlike; web test covers the page and menu link. |
