---
description: "Decision to keep articles, product documentation, and legal source under one public repository root."
last_verified: "2026-08-31"
---

# ADR-0136: One repository root for user-facing source

Status: accepted.

## Context

Public source had three unrelated physical owners: content-hub articles under
`apps/web`, product documentation in two root language directories plus a web
copy, and legal policies as Python package data. That layout made the renderer
look like the content owner, duplicated documentation, and hid the fact that
Git-backed articles and legal policies are imported into immutable database
revisions during deployment or API startup.

## Decision

`docs-user-facing/` is the canonical root for public authored source:

- `content/{locale}` contains repository-owned content-hub articles;
- `docs/{locale}` contains product and CLI documentation;
- `legal/{locale}/{slug}/{version}/document.md` contains immutable legal policy
  versions.

The existing publication boundaries remain. A deploy build creates an exact
commit snapshot from `content/` and the one-shot importer atomically updates the
repository-owned article set in PostgreSQL. The documentation service and web
documentation routes render the same `docs/` source. API startup synchronizes
`legal/` into immutable `DocumentRevision` rows and records the deployed commit
and canonical source path.

Application directories may receive source files in a container build context,
but no tracked application-local copy is canonical. Internal `docs/` remains the
normative engineering corpus.

## Consequences

- A Git commit and deployment remain required to publish repository articles or
  legal policy versions; staff-authored articles retain their API publication
  path.
- Moving files alone does not create new public revisions: article and legal
  digests still determine idempotency.
- Production images must include the relevant canonical subtree, and missing or
  empty sources fail the build or API startup rather than silently unpublishing
  content.
- Source links use paths below `docs-user-facing/` and the exact deployed commit.

## Reconsideration conditions

Reconsider if content is moved to an external CMS or repository, or if legal
publication requires an approval service beyond reviewed Git changes.
