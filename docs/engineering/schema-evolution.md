---
description: "Versioning, compatibility, and migration of persisted and transmitted schemas."
last_verified: "2026-08-03"
---

# Schema evolution

## Ownership

Each machine contract has one owner: JSON Schema, OpenAPI, or a public provider schema. Documentation and examples are validated against the owner and do not introduce alternative fields.

## Versions

A new optional field preserves compatibility within the major version. Renaming or changing the type, required status, canonicalization, or hash domain requires a new major version or an explicit dual-read migration.

An unknown enumeration value is not converted to an unsafe default. A reader either preserves an unknown optional value or returns a typed incompatibility.

## Change sequence

```text
extend the reader
→ write the compatible form
→ migrate or backfill the data
→ switch the readers
→ remove the old form after the compatibility window
```

For a database, locks, volume, resumability of the backfill, and rollback compatibility are also recorded. For a file schema, old and new readers are recorded. For an API, both sides of mixed-version operation are tested.

## Migration

A migration is idempotent, journaled, and has an integrity check. An irreversible transformation requires a separate decision and a backup. A rolled-back application must be able to read data written by the new version during the declared compatibility window.

## Published data

A published artifact and its hash are never rewritten. A transformation creates a new version or revision and preserves the original hash and provenance.

## Generation

Schemas, reference examples, client types, and documentation are generated with a pinned tool. Regeneration must produce a clean diff. CI verifies that the source and generated output match.
