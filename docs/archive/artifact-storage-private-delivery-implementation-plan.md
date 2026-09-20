---
description: "Implementation sequence for owner-scoped artifacts, platform assets, private delivery, and verified backups."
last_verified: "2026-09-07"
---

# Artifact Storage and Private Delivery Implementation Plan

Normative owners: `ADR-0166`, `SPEC-002`, `SPEC-007`, `SPEC-020`, `SPEC-024`,
`SPEC-026`, `SPEC-028`, `SPEC-035`, and `SPEC-038`. This plan sequences their
delivery and does not replace their requirements.

## 1. Freeze contracts and migration shape

1. Extend storage configuration with required artifact and asset bucket names;
   retain the current bucket setting as a read-only compatibility source during
   migration.
2. Add bucket role and owner binding to object locations through an additive
   Alembic migration. Keep existing rows readable until copy-and-verify finishes.
3. Add private publication visibility and private artifact delivery to the
   source-owned contract models, stable errors, OpenAPI, CLI schemas, and client.
4. Keep the access-grant contract limited to read, download, install, and fork
   for the exact major line; publication and mutation remain owner-only.

Exit: contracts and schema can represent both buckets, private publication, and
authorized delivery without changing stored bytes.

## 2. Establish the two storage classes

1. Create and readiness-check the artifact and asset buckets with public access
   blocked and service-only credentials.
2. Replace the global artifact key builder with one server-derived owner/digest
   key. Reject caller-selected buckets, owners, and keys.
3. Route profile, component, and platform media through the asset bucket's
   closed `users/`, `components/`, and `platform/` namespaces. Keep quarantine
   unavailable and replace metadata pointers only after validation.
4. Verify size and digest on every artifact read and preserve distinct missing,
   unavailable, and integrity errors.
5. Add a real RustFS test profile beside the current memory/fake adapter tests.

Exit: new writes have the correct bucket and owner binding, and no S3 endpoint
or credential is exposed to a client.

## 3. Package and publish exact component bytes

1. Reuse the canonical component-tree packer. Add one Git-aware inventory step
   for the explicit component root: tracked files plus untracked, non-ignored
   files; exclude repository metadata and ignored untracked files.
2. Display and bind the deterministic path inventory before creating or
   confirming the publication plan.
3. Add visibility to the plan. Default to private; require an explicit public
   choice and the existing public-source validation before public publication.
4. Upload exact archive bytes through the existing authenticated plan route.
   Preserve the same plan and digest across transport retries and expose durable
   bind state through status.
5. Create a public projection only for public visibility; private publication
   records the same immutable verified version without anonymous projection.

Exit: a local public or private component root becomes one verified immutable
version, and request/response loss can be recovered by status and same-input
retry.

## 4. Deliver private artifacts through one authorization path

1. Introduce one server predicate for artifact delivery: public active version,
   owner, or active grant for exact object and major line.
2. Use the predicate in exact component and setup artifact routes before reading
   an object location. Unauthorized and revoked reads use the same not-found
   surface.
3. Return typed dependency or integrity failures only after authorization has
   established that the caller may know the object.
4. Extend CLI download/install to use the authenticated route, verify digest and
   size before local caching, and keep already downloaded local bytes after
   grant revocation.
5. Authorize every private dependency of a setup independently; do not replace
   or omit an inaccessible dependency.

Exit: owner and active grantee install private versions; outsider, revoked
recipient, and uncovered major cannot read them.

## 5. Back up and restore verified storage

1. Export PostgreSQL and both working buckets to an off-host destination with
   separate backup credentials and bounded retention.
2. Generate a committed-object manifest containing bucket role, key, owner,
   digest, content ID, and size without object bytes or secrets.
3. Restore into an isolated PostgreSQL/RustFS copy and verify every referenced
   object before marking the backup usable.
4. Run the public/private owner/grantee/outsider/revoked matrix against the
   restored copy and record the rehearsal result and backup age.
5. Alert on failed backup, stale successful backup, restore verification
   failure, missing object, and digest mismatch.

Exit: loss of the deployment host has a documented and rehearsed recovery path
whose restored bytes agree with PostgreSQL.

## 6. Migrate and cut over

1. Deploy additive columns and dual reads while all new writes use the new
   bucket roles and keys.
2. For each legacy object location, derive the owner-scoped destination, copy
   bytes, verify digest and size, and write the new location idempotently.
3. Stop cutover on any missing, corrupt, or ambiguously owned legacy object.
4. Switch reads to the new locations after the complete inventory passes; keep
   old objects through the rollback window.
5. Remove compatibility configuration and old objects only through a later
   explicit retention change after restore evidence is green.

Exit: all live metadata resolves through owner-bound locations in the two
working buckets, with no destructive migration needed for rollback.

## Minimum test matrix

| Slice | Mandatory evidence |
|---|---|
| Packaging | Tracked, ignored, untracked, nested ignore, traversal, link, secret-like file, stable order, and exact archive digest. |
| Publication | Private default, explicit public, private-source refusal for public, same bytes for both visibility values, retry after lost request/response. |
| Authorization | Anonymous public, private owner, active grantee, outsider, foreign owner, revoked grant, current major, and new major. |
| Integrity | Missing object, changed size, changed digest, unavailable RustFS, conflicting repeated upload, and no partial projection. |
| Assets | User/component/platform namespace, foreign namespace rejection, quarantine, append-only replacement, and pointer rollback. |
| Recovery | Off-host backup, complete manifest, isolated restore, object verification, authorization matrix, and failed-restore refusal. |

## Explicitly deferred

- general RBAC, organizations, collaborative editing, and delegated publication;
- per-user buckets and direct client storage credentials;
- private GitHub credential retrieval until the connector owns that authority;
- resumable multipart API until measured size or retry cost exceeds the current
  bounded idempotent upload;
- a public S3 bucket or CDN origin until API-mediated delivery is a measured
  bottleneck;
- multi-region or multi-node RustFS until an availability target requires it.
