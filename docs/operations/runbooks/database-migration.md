---
description: "Server schema upgrades and local CLI migration boundaries."
last_verified: "2026-10-15"
---

# Database migration

The server uses Alembic migrations in `migrations/`; the native CLI owns its local
SQLite migration in `apps/cli/src/migration.rs`. These are separate state stores.

Use the normal deployment procedure for server upgrades. Read the current revision,
review the pending chain and run affected schema migration tests before deployment.
`migrations/history.lock` records merged revisions and their parents. Append new
revisions; never rewrite applied history or change a merged revision's parents.
Resolve parallel heads with the intended unapplied chain or a merge revision.

On failure, preserve the current database and read the failed migration and deploy
stage. Repair forward or use a reviewed downgrade only when the actual code and
stored data support it. Do not stamp past an error, rename owners, delete records
or disable constraints to make the migration appear successful. Backups and data
copies are separate owner-authorized operations, not an automatic prerequisite.

`deploy/postgres-major-upgrade.sh` owns the conditional PostgreSQL layout transition;
inspect its current preconditions and recovery markers before acting. Do not remove
a retained database volume as cache. Verify `/v1/system/version`, migration state
and application readiness after the deployment settles.

For existing local CLI state, use the explicit plan/apply transfer in the
[Rust CLI guide](../../../apps/cli/README.md#state-and-first-run).
