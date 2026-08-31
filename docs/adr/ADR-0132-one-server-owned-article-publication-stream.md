---
description: "Decision to converge repository import and the staff API into one server-side article publication stream."
last_verified: "2026-08-29"
---

# ADR-0132: One server-side article publication stream for Git and API

Status: accepted.

## Context

The content hub reads repository Markdown directly from the web image. A new or
changed article therefore requires a site build, while the server has no shared
revision history through which material can safely be added without changing
Git.

The platform already uses PostgreSQL, immutable revisions, and a public API. A
new authoring method through the staff API must not create a second serving
path: otherwise the web, Atom, sitemap, and machine projection would each merge
Git and the database themselves, resolve collisions, and handle failure of one
source differently.

## Options

1. **Keep Git in the web and mix DB entries into each request.** This requires
   no migration of repository content, but creates two sources of truth in all
   public projections and separate caching, deletion, and conflict rules.
2. **Write API content back to Git.** This preserves one file-based source, but
   publication depends on Git credentials, commit/push, and a new web deploy.
3. **Import a Git snapshot into the platform and read all published articles
   through the API.** Accepted: Git and the staff API remain two authoring
   sources, while the platform becomes the sole serving source.

## Decision

A stable `Article` belongs to exactly one source owner: `repository` or `staff`.
Both sources create immutable localized `ArticleRevision` objects, and active
pointers select the published RU/EN revisions. An identity collision on
`{type}:{slug}` between different owners is rejected and is never resolved by
priority or last-write-wins.

The deploy build validates `docs-user-facing/content` and creates a deterministic full
`snapshot` with the exact repository commit, source paths, content digest, and
whole-snapshot digest. The build does not call the API or PostgreSQL. During
deploy, after migrations and API readiness, a one-shot importer submits the
snapshot through a separate authenticated operation. The platform atomically
replaces only the active set owned by the `repository` source; repeated
snapshots are idempotent, while missing entries are unpublished without deleting
history.

Staff publication uses a separate API operation with an allowlist of accounts
and atomically publishes a strict RU/EN pair. It cannot change a
repository-owned identity. Concurrent changes are guarded by the expected active
digest; the editor's account remains in the private audit and does not enter the
public response.

Content pages, the index, Atom, and human/machine projections read only the
public content API. The Next.js server forms HTML from the same published
revision. `content_hub` remains a build-time feature under `ADR-0089`: a web
image with it disabled does not call the content API or publish the section's
routes.

Domain publication of an article does not depend on SEO materialization. A
successful active-revision change emits the `SPEC-053` event; the latest SEO
profile may catch up with the new article asynchronously without rolling back
its publication.

## Consequences

- A Git article changes through a new commit and deploy import; a staff article
  changes through an API call without rebuilding the web.
- PostgreSQL and the public content API become mandatory for serving the content
  hub; the repository snapshot remains a recoverable source only for its own
  entries.
- Deploy gains a one-shot import step and a separate restricted credential; its
  absence or failure does not change the previous active repository set.
- Revision history is retained through update, unpublish, and deletion of a Git
  file.
- The web no longer merges filesystem and DB records or determines source
  precedence.
- Rolling back the web restores the previous image; rolling back repository
  content reimports the snapshot of the previous exact commit. Staff revisions
  are unchanged.

## Reconsideration conditions

- A third authoring source appears for which the same snapshot or staff
  publication contract is insufficient.
- Measured load makes serving through the API unacceptable even with the current
  public cache boundary.
- An editorial workflow with roles, approval, or scheduling appears; the CMS
  lifecycle is then designed separately from the current publication operation.
