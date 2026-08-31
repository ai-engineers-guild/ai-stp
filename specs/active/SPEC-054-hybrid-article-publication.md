---
description: "SPEC-054: Unified server-side publication of repository- and staff-authored articles."
last_verified: "2026-08-29"
---

# SPEC-054: Hybrid article publication through the platform

## Purpose

The content hub exposes published articles from two authoring sources through a
single public API: the repository snapshot of the current web release and the
staff API. Repository materials are updated during deploy, while staff materials
are updated without a web rebuild; the web server builds human and machine pages
from the same active DB revision.

## Scope

The scope includes stable article identity, immutable localized revisions, source
ownership, repository snapshot build and import, staff publication and unpublish,
public list/detail reads, atomic activation, deploy ordering, cache identity,
audit, migration, and rollback. The exact wire contract belongs to
`docs/contracts/article-publication.md`, the architectural decision to `ADR-0132`,
and derived SEO revisions to `SPEC-053`.

The scope excludes a browser-based editor, approval workflow, scheduled
publication, arbitrary Git URL import, user authors, media upload, and identity
transfer between sources without a separate migration operation.

## Terms

- **Article** — a stable content-hub material with identity `{type}:{slug}` and
  source owner `repository` or `staff`.
- **ArticleRevision** — immutable localized Article content with a canonical
  content digest and provenance.
- **Active article set** — published RU/EN revision pointers read by the public
  API.
- **Repository snapshot** — a complete deterministic list of published entries
  from one exact repository commit.
- **Source owner** — the sole authoring source permitted to change an Article's
  active revisions.

## Requirements

- `REQ-5401`: Article identity is `{type}:{slug}`, where type is one of
  `article`, `blog_post`, `changelog`, `release_notes`; each identity has one
  immutable source owner and a strict `ru`/`en` locale pair.
- `REQ-5402`: ArticleRevision stores locale, title, description, published date,
  tags, Markdown body, a digest of the entire canonical revision, source
  kind/ref/path, creation time, and a private actor reference for staff
  publication; changing any public field creates a new revision.
- `REQ-5403`: The web build validates `apps/web/content/hub` using the active
  content rules and creates a complete snapshot of the exact commit without
  accessing the network, API, or DB; the snapshot and entries have canonical
  digests, and file ordering does not affect them.
- `REQ-5404`: After schema migration and API readiness, but before switching to
  the new web image, production deploy passes the embedded snapshot through an
  authenticated repository import operation; the importer does not read a
  checkout on the host and does not accept an arbitrary path or URL.
- `REQ-5405`: Repository import first validates the schema, digests, exact
  commit, uniqueness, and locale parity of the entire snapshot, then creates
  revisions and changes only the repository-owned active set in a single
  transaction; an error leaves the previous set and generation unchanged.
- `REQ-5406`: Repeating the active snapshot is a no-op. A changed entry creates
  revisions and a new generation, a new entry is activated, and a missing entry
  is unpublished; history and the staff-owned active set are preserved.
- `REQ-5407`: Repository import rejects an identity already owned by `staff`,
  while a staff operation rejects a `repository` identity; source precedence
  and automatic ownership takeover are prohibited.
- `REQ-5408`: An allowlisted staff account publishes or unpublishes an Article
  through the authenticated API without a web rebuild. Publication accepts the
  RU/EN pair in one transaction and checks the expected active digest; a stale
  expected digest results in a conflict with no partial effect.
- `REQ-5409`: The public API returns a unified active list and detail regardless
  of source owner, excludes drafts/unpublished/history/private actor data, and
  exposes repository provenance only as safe exact commit/path facts.
- `REQ-5410`: When `content_hub` is enabled, the web server obtains the index and
  detail from the public content API and builds metadata HTML, the human body,
  and the machine document from the same revision; Atom and discovery consumers
  have no separate filesystem fallback or second merge.
- `REQ-5411`: Staff publication becomes available without a web rebuild after
  the public cache identity is updated. Repository publication becomes available
  only after a successful deploy import; the new web image is not considered
  ready until this import completes.
- `REQ-5412`: Changing the active revision or unpublishing enqueues an
  idempotent article event for `SPEC-053`; an SEO failure does not roll back the
  domain transaction or change the active article set.
- `REQ-5413`: Repository import uses a separate, limited-scope deployment
  credential; staff changes are permitted only for an account in the
  `allowlist`. Request body and Markdown sizes are limited by the contract; raw
  body and credentials do not appear in logs, metrics, or error responses.
- `REQ-5414`: Import and staff mutation record an AuditEvent containing the
  operation ID, source kind, snapshot/revision digest, outcome, and safe
  counters; public reads remain anonymous and public-cacheable.

## States and errors

An Article has an active or unpublished serving state; history consists of
immutable revisions. Repository import results in `validated`, `applied`,
`no_op`, or `rejected`; no intermediate state becomes public.

Stable errors: `AI_STP_CONTENT_INVALID`, `AI_STP_CONTENT_SOURCE_CONFLICT`,
`AI_STP_CONTENT_STALE`, `AI_STP_CONTENT_IMPORT_FORBIDDEN`, and the existing
`AI_STP_NOT_FOUND`. Validation, permission, and stale failures do not change
active pointers, generation, or SEO jobs.

## Security and privacy

Repository content is a restricted input controlled by the repository owner, but
it is subject to the same safe Markdown policy as the staff payload. The import
credential grants only the right to replace the repository-owned snapshot and
grants no staff, account, or catalog permissions. The staff actor ID is available
only in the private audit. The public API does not return credentials, the
source's internal location on the host node, editor identity, or draft or
rejected bodies.

## Compatibility and migration

Rollout follows expand/import/switch: add additive article storage and API;
import the current repository snapshot and verify identities/digests; switch web
reads from the filesystem to the API. Before the switch, the current web
continues to read from Git, and the new API does not change public routes. After
the switch, URLs `/{locale}/content/{type}/{slug}` are preserved.

Rollback restores the previous web image and repository serving without deleting
the new tables. Re-importing the snapshot of the previous exact commit rolls back
only the repository-owned active set; staff-owned entries are preserved. The
contract phase and removal of filesystem reads are performed as a separate
change after the rollback window.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-5401`–`REQ-5402` | A migration/storage test verifies identity, source owner, locale pair, immutable revisions, and digest changes for every public field. |
| `REQ-5403` | Two builds of the same commit with different traversal orders produce a byte-identical snapshot without network access. |
| `REQ-5404` | A production scenario proves the migrate→API ready→import→web ready order and that web readiness fails when import fails. |
| `REQ-5405`–`REQ-5406` | A platform test repeats a snapshot, changes, adds, and removes an entry, and verifies the atomic active set, generation, and preserved history. |
| `REQ-5407` | A repository/staff conflict matrix rejects takeover in both directions without changing the owner or active revision. |
| `REQ-5408` | An ASGI test publishes an RU/EN pair, rejects a stale expected digest, and unpublishes a staff article. |
| `REQ-5409` | A public contract test combines repository/staff entries and proves redaction of unpublished content, history, and the private actor. |
| `REQ-5410` | A web test builds index/detail/human/machine/Atom output from an API fixture and does not read `content/hub` on the request path. |
| `REQ-5411` | An E2E test publishes a staff article without a rebuild and sees it after the cache identity changes; a repository article appears only after import. |
| `REQ-5412` | An integration test observes one SEO effect for a new active revision and preserves publication when the SEO worker fails. |
| `REQ-5413`–`REQ-5414` | A security test verifies scoped credentials, limits, forbidden Markdown, redacted logs, and an AuditEvent without body/token data. |
