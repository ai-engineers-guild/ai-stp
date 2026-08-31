---
description: "Decision to permit an explicit schema downgrade as a separate operation with a verified backup, while preserving the prohibition on an implicit downgrade within application rollback."
last_verified: "2026-08-12"
---

# ADR-0081: Schema downgrade is an operation, not a prohibition

Status: accepted.

## Context

`ADR-0044` considered two rollback methods and adopted the first: redeploy the
previous exact application artifact. The second—"rollback through a reverse
schema migration"—was rejected on the grounds that it "destructively moves data
backward and is dangerous once records have already been accepted." `REQ-2410`
established this as a rollback property, the runbook as a prohibition, and
`rollback.sh` as a "NEVER" comment.

The prohibition addressed a real problem, but addressed it too broadly. It is
not lowering the revision itself that is dangerous, but a downgrade that happens
**implicitly**: the operator asks to restore the previous application version and
loses data they did not ask to lose. That is exactly what `ADR-0044` prohibited,
but the prohibition was recorded as "reverse migration does not exist."

As a result, staging—where a mistake costs one run—was subject to a rule written
for an environment where it costs user data. The ordinary workflow—apply a
migration, discover that the model is wrong, go back and rewrite it—had no
supported path and was performed outside the tooling.

## Decision

Lowering the schema revision is a supported operation. It is separate from
application rollback, not permitted within it.

- Application rollback does not migrate the schema in either direction. The
  property from `ADR-0044` is preserved in full: without an explicit request,
  `rollback.sh` restores the previous artifact and leaves the schema in place.
- A downgrade is performed by an explicit request with a target revision. There
  is no default: a command without a revision downgrades nothing.
- A backup is taken in the same run before the downgrade, and its absence stops
  the operation. A backup taken yesterday does not count: a downgrade is exactly
  as irreversible as dropping a column.
- A downgrade is recorded in the operation log on the same terms as a forward
  migration: exact "from" and "to" revisions, backup name, and commit.

The difference between "forbidden" and "must be requested" is the entire
substance of this decision. The former sends the operator outside the tool; the
latter leaves an audit trail.

## Consequences

`REQ-2410` no longer describes application rollback through the absence of a
reverse migration and instead describes it directly: the previous artifact is
restored and the schema is untouched. A separate downgrade requirement mandates
a backup in the same run and an explicit target revision.

The tool no longer diverges from practice. While downgrade was prohibited, it
was still performed manually through `alembic downgrade` in the container—without
a lock, without a backup, and without a deployment-log entry—which is exactly
what the prohibition was intended to prevent.

The rule in `docs/engineering/schema-evolution.md`—"an irreversible
transformation requires a separate decision and a backup"—does not change and
is now enforced by code rather than merely read.

## Reconsideration conditions

Reconsider this decision when a production environment with user data appears:
the cost of error is different there, and downgrade may require additional
authority beyond a backup. Until then, staging remains an environment where
iteration is cheaper than caution.
