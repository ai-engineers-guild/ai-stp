---
description: "Migration sequence for moving the content hub to unified API serving for repository and staff publications."
last_verified: "2026-08-29"
---

# Hybrid Article Publication Implementation Plan

Normative owners: `SPEC-054`, `ADR-0132`, and
`docs/contracts/article-publication.md`. `SPEC-053` receives only the event for
an activated ArticleRevision and does not own import or staff publication.

## 1. Expand: contracts and persistence

1. Add canonical contract models and OpenAPI operations for public read,
   repository state/import, and staff publish/unpublish; regenerate schemas and
   the web client.
2. Introduce a stable Article with a source owner, immutable localized
   ArticleRevision, and active pointers. Extend the already prepared article
   tables with an additive migration instead of introducing a second document model.
3. Make the revision digest cover metadata, body, and provenance, and make the
   active digest cover the exact RU/EN pair.
4. Add scoped import credential configuration and AuditEvent records for
   import/staff mutations, without recording the body or credential.
5. Leave existing filesystem serving unchanged at this stage.

Exit: schema and API contracts deploy alongside the old web application; the old
image ignores the new tables and routes.

## 2. Repository snapshot and atomic import

1. Reuse the current content loader to validate and serialize published entries
   into a canonical snapshot; do not write a second Markdown parser.
2. Embed the snapshot and exact commit in the release artifact without accessing
   the API/DB during image build.
3. Move repository import from the SEO namespace into the content publication
   service; after successful activation, enqueue the SEO effect through the narrow
   `SPEC-053` call.
4. Implement a full-snapshot transaction: validate all, lock generation, reject
   source conflicts, create missing revisions, switch pointers and deactivate
   absent repository entries, then increment generation once.
5. Add a one-shot importer that reads state, sends the expected generation and
   exact snapshot, and logs only the commit, snapshot digest, counters, and outcome.

Stage result: repeating the exact snapshot is a `no_op`; an invalid or stale
snapshot leaves the active set and jobs unchanged.

## 3. Staff publication

1. Implement the staff allowlist guard with the existing account/session mechanism.
2. Publish RU/EN translations and active pointers in one transaction with an
   optimistic check against the active digest.
3. Implement staff unpublish without deleting revision history.
4. Forbid staff mutation of a `repository` source identity and prevent the
   `repository` source from taking over a staff-owned identity through a common
   source-owner check.
5. Bound the payload and apply the current safe Markdown policy before writing.

Stage result: a staff article appears in the public API without rebuilding the web
application; stale updates and source collisions have no partial effect.

## 4. Public serving and web switch

1. Implement unified public list/detail reads for active repository and staff
   articles, with ETag and redaction of private provenance.
2. Move the content index, detail, and metadata to the server-side API client;
   remove filesystem lookup from the request path and permit runtime slugs from the DB.
3. Move human/machine projections and Atom to the same public read model.
   Discovery/SEO continues to read active ArticleRevision through `SPEC-053`.
4. Preserve the build-time `content_hub` gate: a disabled image publishes no
   routes, navigation, or discovery and makes no content request.
5. Do not add client-side merging, fallback to repository files, or a separate
   cache service; use the current public RSC/API cache boundary.

Stage result: one API fixture shows repository and staff articles together in all
projections; a DB change does not require a rebuild.

## 5. Deployment and rollout sequence

1. Add the content importer as a one-shot release service after `migrate` and a
   healthy API. The new web application depends on its successful completion.
2. Before the first switch, import the current snapshot and compare type/slug,
   `locale`, metadata, body digest, and public count with the filesystem source.
3. Perform expand/import/switch: schema/API first, then snapshot backfill, then
   web API reads.
4. On failed import, do not change the active repository generation; stop the
   deployment and restore the previous exact ref/image under the current runbook.
5. After the rollback window, remove filesystem serving and the old build-time
   route list in a separate contract change; retain the authoring repository and
   snapshot builder.

Exit: the new release shows the snapshot from its exact commit plus all previously
published staff articles; rolling back the repository release does not change the staff set.

## Minimum test matrix

| Slice | Mandatory evidence |
|---|---|
| Snapshot | Determinism, exact commit/path, whole-content digest, bounds, and locale parity. |
| Platform | Atomic replace, no-op repeat, add/update/remove, source conflict, stale generation, and history retention. |
| Staff API | Allowlist, RU/EN atomicity, stale active digest, unpublish, and audit redaction. |
| Public API | Unified sorting, detail, no fallback, ETag, 404, and exclusion of private fields. |
| Web | SSR index/detail, metadata, human/machine/Atom parity, and disabled-feature 404. |
| SEO | One effect per active change; publication survives a failed worker. |
| Deploy | migrate→API ready→import→web ready, failed import, and rollback to the previous snapshot. |

## Explicitly deferred

- browser editor, preview interface, approval roles, and scheduled publication —
  until a separate editorial workflow;
- moving an Article between `repository` and `staff` — until an explicit,
  auditable migration operation;
- media upload and asset library — repository illustrations continue to operate
  under the current safe Markdown policy;
- message broker, CMS service, and separate content microservice — until measured
  load exceeds what API/PostgreSQL can handle;
- pagination of the public content list — until a measured size at which the
  bounded full locale list no longer fits the current cache contract.
