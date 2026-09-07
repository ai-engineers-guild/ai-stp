---
description: "Runbook: database migration."
last_verified: "2026-08-05"
---

# Database migration

1. Record the code and schema versions.
2. Stop incompatible write processes.
3. Create a consistent backup and verify restoration and integrity.
4. Build a migration plan with the source and target schema digests.
5. Apply migrations transactionally or in resumable steps.
6. Check constraints, indexes, and data counts.
7. Run compatibility tests for the old and new versions.
8. Only then advance the code.
9. In case of an error, do not declare a rollback until the compatibility of written data has been verified.

## Recovery policy (forward-fix by default)

Normative requirements belong to `SPEC-020` (`REQ-2002`); this section describes the
execution procedure.

- The `Alembic` migration tree is single and linear: one history head outside the
  merge window. Parallel heads are resolved before the code is advanced.
- A defect in an already applied migration is corrected with a forward-fix: a new forward migration,
  not a rollback of the advanced schema. This keeps recovery independent of the compatibility of
  the old path with data written by the new version.
- `downgrade` is allowed only within the compatibility window, while the advanced code
  correctly reads and writes data in the new version, and only after step 9 has been verified.
- Each migration defines a forward operation and a reverse operation, or an explicit
  irreversibility marker with rationale.
- A backward-incompatible change proceeds through expand, migrate, switch, and
  contract under `docs/engineering/schema-evolution.md`; the old path is removed only
  after the dual-read window.

## Generated account names block revision 0040

If the migration reports `generated account identity collision`, distinguish
an allocator defect from a conflict in submitted names. The default-name
allocator previously truncated a canonical account ULID and could give two
different accounts the same generated name. The regression is exercised by
`test_identity_migration_preserves_distinct_account_suffixes` against a populated
pre-identity database.

Deploy the corrected allocator through the ordinary promoted ref, after checking
the backup and the source/schema identities. Retry the transactional forward
upgrade; do not rename accounts manually, merge owners, stamp the database past
the failed migration, or disable unique constraints. Already assigned names are
not rewritten. A distinct conflict in user-submitted names still requires the
conflict-resolution procedure from `SPEC-059`.

Read `/v1/system/version` after recovery and run the public verifier against the
promoted commit and migration head. A successful build or ref promotion does not
prove that the migration or the deployment completed.

## Locale repair scope in revision 0047

Before advancing a pre-0047 environment, use the corrected migration that
matches both locale and normalized display name. The earlier query selected
unrelated owners' names whenever the configured Official source existed.
`test_locale_repair_preserves_nonconflicting_names` exercises populated data in
both locales and requires unrelated names to survive.

This correction prevents that broad update on databases which have not applied
0047. It does not reconstruct names already overwritten elsewhere. Recovery of
such a database requires its verified pre-migration backup and an exact,
reviewed forward repair; do not guess original names from current slugs.

## Canonical catalog consumers in revision 0048

The forward migration permits the passport contract's standalone `cli` kind
in Official sources and removes the search table's invented `primary` default.
Bootstrap rebuilds the derived search rows from their passports and the current
harness registry, including on production where development seeding is off.
The rebuild holds a table lock against writers while ordinary readers retain
the previous committed projection. Catalog metadata and immutable artifact
bytes are not rewritten by reindexing.

A downgrade to the former component constraint is refused if `cli` source rows
already exist. Use a compatible forward repair; do not relabel programs as
slash commands or delete their history to force a downgrade.

Development bootstrap now requires configured artifact storage and loads the
canonical corpus with exact identities, complete setup references and verified
bytes. Frozen Sprint-1 fixtures live in test support and are not a production
seed path. See `SPEC-021` for the environment and immutability boundaries.

## Canonical support after target assessments

Revision `0052_restore_canonical_support_tiers` removes the SQL support-tier
fallback reintroduced with target assessments. It changes no passport, identity,
visibility, or version. The normal bootstrap rebuilds the derived catalog index
from the stored passports, preserving actual support declarations and excluding
unreadable records. Rollback restores only the preceding SQL default; it does not
rewrite any stored tier or immutable version.

## Current assurance expiry

Revision `0053_component_assurance_expiry` adds the derived expiry described in
[`target-assessments`](../../contracts/target-assessments.md). It clears legacy
component badges from the search index; the normal bootstrap rebuilds them from
current target and common evidence. Passports and evidence history stay intact.
Rollback drops only the derived column. Keep the preceding application version
and rebuild the index after rolling back both code and schema.
