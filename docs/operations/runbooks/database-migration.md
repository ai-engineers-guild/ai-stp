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
