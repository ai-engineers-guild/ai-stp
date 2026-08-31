---
description: "Decision to maintain the local registry using the standard sqlite3 with a custom migration runner instead of Alembic."
last_verified: "2026-08-06"
---

# ADR-0059: Local Registry Using the Standard sqlite3

Status: accepted.

## Context

`SPEC-009` REQ-901 requires the local registry to support migrations, write-ahead logging, foreign keys, transactions, and restrictive file system permissions. Issue #74 names Alembic as the tool.

Alembic is designed for SQLAlchemy and does not work without it. Measurements in an empty environment show that it brings in five packages—`sqlalchemy`, `greenlet`, `mako`, `markupsafe`, and `typing-extensions`—of which SQLAlchemy alone occupies 14 MB. Importing `sqlalchemy` costs about 510 ms beyond an empty interpreter, while importing `alembic` costs about 440 ms. The standard `sqlite3` costs 2 ms.

The order of magnitude is decisive here. In `ADR-0058`, the `keyring` import was made lazy precisely because 100 ms is three times more expensive than Click and is noticeable in a command that stores nothing. Half a second is five times worse, and the very first command that opens the registry will pay that cost because migrations are applied on open.

Mako and MarkupSafe are included in the dependency tree for migration file generation—a development-time task that ends up in every user's wheel.

A separate complication is that Alembic expects a directory containing scripts and an `alembic.ini` alongside the project. In an installed wheel, these are package data, and running migrations no longer behaves the same as running them from the source tree. This is exactly the class of discrepancy that `smoke-cli` from #72 exists to catch.

The local registry data model is small: entities, revisions, heads, and an operation log. It requires neither an ORM nor automatic generation of migrations from models.

## Alternatives

1. Alembic and SQLAlchemy, as specified in the issue. A standard tool and familiar workflow, at the cost of 15 MB and half a second for every command that opens the registry.
2. Alembic on top of SQLAlchemy Core without an ORM. The dependency tree is the same; the only benefit is in code style.
3. The standard `sqlite3` and a custom migration runner ordered by `PRAGMA user_version`. Zero dependencies, identical behavior from the source tree and from the wheel; migrations are applied, are idempotent, and are rolled back where rollback is declared.
4. Defer migrations until a second schema version appears. Rejected: the very first installation creates a file that must be upgradable, and adding the mechanism after user data already exists means adding it at the worst possible time.

## Decision

Alternative 3 is accepted.

The registry is opened using the standard `sqlite3` with `journal_mode=WAL`, `foreign_keys=ON`, and transactional writes. The schema version is stored in `PRAGMA user_version`; migrations are declared as an ordered list, each with its own apply statements and, where expressible, rollback statements. Application is idempotent: a migration whose number is not greater than the current version is not executed again.

The database, content directory, and operation log are created with owner-only permissions using the same primitives as in `ADR-0058`.

A file with a schema version higher than the supported version is neither opened nor modified: the response is typed, and the original database remains untouched. The version must not be silently downgraded—doing so is the only way to lose data written by a newer build.

## Consequences

- the CLI dependency tree does not grow; `sqlite3` is part of the standard library;
- migrations are written as SQL rather than generated from models: discrepancies between the model and the schema are caught by a test, not by autogeneration;
- behavior from the source tree and from the installed wheel is identical by construction because nothing is looked up on disk alongside the project;
- the server track continues to use PostgreSQL and Alembic for its own issue; these are different storage systems with different requirements, and they do not share a common tool;
- there is no dependency owner because there is no dependency; no removal path is required.

## Reconsideration Conditions

The decision will be reconsidered if the local schema requires capabilities that `sqlite3` does not provide without an ORM, if the number of migrations makes a manual list more costly than autogeneration, or if the local and server layers begin sharing the same data-access code—today they share nothing except passport models.
