---
description: "Decision to implement a minimal custom PostgreSQL job queue instead of an external library or broker."
last_verified: "2026-08-05"
---

# ADR-0038: Custom PostgreSQL job queue

Status: accepted.

## Context

`docs/engineering/tech-stack.md` establishes a worker using a PostgreSQL-backed queue but does not define the mechanism. `ADR-0009` already selected PostgreSQL and RustFS as the platform, while `SPEC-010` REQ-1006 requires at-least-once delivery, a transactional outbox, bounded retries, and idempotent handlers. The MVP background-job set is small and coarse-grained: uploading an object with its publicity flag and scheduling an update, where signing the reference is a step within the job. The stack already includes SQLAlchemy 2, Alembic, and asyncpg. We must decide whether the queue uses minimal custom logic or an external library, and which delivery semantics apply.

## Options

1. The external `procrastinate` library. Mature and async, uses `LISTEN`/`NOTIFY` and `FOR UPDATE SKIP LOCKED`, and provides retries and scheduled jobs, but brings its own schema and migrations, creating a second migration system beside Alembic `#79`.
2. The external `pgqueuer` library. Lighter, but younger with fewer ready-made retry and dead-letter guarantees, while still adding a second migration surface.
3. An external broker, such as Redis with a task queue. Provides a mature ecosystem but adds a service and state outside the primary database for two infrequent jobs, contrary to the minimal-dependencies principle.
4. A minimal custom queue on existing PostgreSQL: one table, selection with `FOR UPDATE SKIP LOCKED`, transactional enqueueing, bounded backoff, dead-letter, and advisory locks for serialization.

## Decision

Option 4 is accepted.

The queue uses minimal custom logic on existing PostgreSQL:

- one `job` table stores type, payload, state, attempts, run time, unique idempotency key, and priority;
- workers take jobs through `SELECT ... FOR UPDATE SKIP LOCKED`, preventing concurrent workers from taking the same row;
- enqueueing occurs in the same transaction as the domain record, making the job table an outbox without a separate relay, while the unique idempotency key prevents duplicates;
- failure applies bounded exponential backoff, and exhausted attempts move to `dead_letter` without automatic retry;
- basic delivery relies on bounded polling.

When demonstrated need arises, the same PostgreSQL provides extensions without a new dependency: serialization of non-concurrent jobs via `pg_advisory_xact_lock` and lower latency via `LISTEN`/`NOTIFY`. They are unnecessary for the MVP and are not normative `SPEC-018` requirements.

Durability is provided by PostgreSQL itself through write-ahead logging and transactions. No PostgreSQL queue extensions are required. Normative queue states and requirements live in `SPEC-018`.

## Consequences

- there is no second migration system: the queue schema lives in the shared Alembic tree owned by `#79`, while `#78` authors the model and migration;
- at-least-once delivery is accepted, so handlers must be idempotent;
- there is no external broker or its operational burden;
- custom selection, retry, and drain logic is covered by concurrency, retry, and shutdown integration tests;
- no queue dependency is added, satisfying the minimal-dependencies rule in `tech-stack.md`.

## Reconsideration conditions

This decision will be reconsidered if job types and frequency grow until custom selection and retries become a bottleneck or require mature-library capabilities, or if a demonstrated need arises for a separate broker for load outside PostgreSQL.
