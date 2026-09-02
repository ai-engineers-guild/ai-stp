---
description: "SPEC-018: Background worker and PostgreSQL job queue."
last_verified: "2026-08-31"
---

# SPEC-018: Background worker and PostgreSQL job queue

## Purpose

The background `worker` executes asynchronous platform jobs through its own minimal queue on the existing PostgreSQL without an external broker. The queue provides at-least-once delivery, transactional enqueue in the same transaction as the domain record, bounded retries, dead-letter handling, and graceful shutdown. The chosen mechanism is fixed in `ADR-0038`; the worker execution shell is inherited from `SPEC-017`.

## Scope

Includes the job model, a closed job-type registry, states and transitions, claiming through `FOR UPDATE SKIP LOCKED`, transactional enqueue, idempotency, retries with bounded backoff, dead-letter handling, cooperative cancellation, and graceful draining on shutdown. The type registry expands additively; domain rules and real handlers for publication, validation, grants-mail, and eligibility belong to `SPEC-026` / `#181`, while writing object bytes belongs to the object-store slice. Queue mechanics do not duplicate product SPECs here. The queue table schema lives in the shared `Alembic` migration tree (owned by `#79`), but the queue model and migration are authored here.

## Terms

- `Job` — a unit of background work with its own type, payload, state, and attempt tracking.
- `Claim` — atomically acquiring a job by one worker through `FOR UPDATE SKIP LOCKED`.
- `Transactional enqueue` — enqueuing a job in the same transaction as the domain record, making the job table an outbox without a separate relay.
- `Dead-letter` — the terminal state of a job that has exhausted its retries, available for investigation and not retried automatically.

## Requirements

- `REQ-1801`: A single `job` table stores type, payload, state, attempt count, attempt limit, next-run time, unique idempotency key, priority, lock owner, lock time, last error, and timestamps.
- `REQ-1802`: The job-type registry is closed and contains: `upload` with a `visibility` parameter whose values are `public` and `private`; `update`; `validate`; `publish`; `reevaluate_eligibility`; `deliver_invitation`; `repository_metrics`; `github_archive`; `catalog_enrichment`; `seo_build`; `seo_enrich`; `official_upstream_sync`. Signing or writing an object to `S3` is a step within `upload`, `update`, or `publish`, not a separate type. An unregistered type is rejected; SEO handler semantics belong to `SPEC-053`; official upstream semantics belong to `SPEC-056`.
- `REQ-1803`: Job states `queued`, `running`, `retry_scheduled`, `dead_letter`, `succeeded`, and `cancelled` change only through permitted events, a terminal state is durably recorded before the response, and this state machine is separate from the mutation-operation state machine in `docs/contracts/operation.md`.
- `REQ-1804`: A worker claims a bounded batch of jobs through `FOR UPDATE SKIP LOCKED` when their state is `queued` or `retry_scheduled` and their run time has arrived; concurrent workers do not claim the same row.
- `REQ-1805`: A job is enqueued in the same transaction as the domain record, without a separate relay, and a retry with the same idempotency key does not create a second job.
- `REQ-1806`: Failure increments the attempt count and moves the job to `retry_scheduled` with bounded exponential backoff; reaching the attempt limit moves it to `dead_letter` without automatic retry.
- `REQ-1807`: A `dead_letter` job is available for investigation, is not retried automatically, and stores the last error without secrets.
- `REQ-1808`: Cancellation is cooperative: a cancelled job transitions to `cancelled` and is not claimed again.
- `REQ-1809`: On a shutdown signal, a worker stops claiming new jobs, completes or requeues running jobs within the timeout, and then exits without losing or duplicating jobs.
- `REQ-1811`: Handlers are idempotent, so redelivery does not cause a duplicate effect.
- `REQ-1812`: The polling interval is bounded.
- `REQ-1813`: The worker records safe operational telemetry for queue claim/empty-poll, queue wait, handler duration, result, and requeue; values are aggregated without job payload, idempotency key, or personal data.

## States and errors

A job progresses through `queued`, `running`, `retry_scheduled`, `dead_letter`, `succeeded`, and `cancelled`. Permitted transitions are `queued` to `running`, `running` to `succeeded`, `running` to `retry_scheduled`, `retry_scheduled` to `running`, `running` or `retry_scheduled` to `dead_letter` when attempts are exhausted, and `queued` or `retry_scheduled` to `cancelled`. A handler error distinguishes a transient failure, which causes a retry, from a permanent failure, which causes dead-lettering. Worker startup failure when a required dependency is unavailable is typed according to `SPEC-017`.

## Security and privacy

The job payload and last-error record contain no secrets or personal data. The idempotency key does not expose secret contents. Worker logs follow the structured-log rules in `SPEC-017` and the prohibition on tokens and personal data in `SPEC-013`. Signed object links are issued only by a verified server step and are not stored in a job as durable authority.

## Compatibility and migration

The queue schema evolves through the expand, migrate, switch, and contract sequence in `SPEC-010`. A new job field is initially optional. A new job type is added to the closed registry by a separate decision. Changing delivery semantics requires updating `ADR-0038`. A rollback must read jobs written by the new version during the compatibility window.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-1801` | The migration and model create the `job` table with all required fields and a unique idempotency key. |
| `REQ-1802` | A registry test accepts every listed type, including `seo_build`/`seo_enrich`/`official_upstream_sync`, and rejects an unregistered type and signing as a separate type. |
| `REQ-1803` | A transition test permits only allowed events and separates queue states from operation states. |
| `REQ-1804` | An integration test with concurrent workers confirms that exactly one worker claims a row. |
| `REQ-1805` | A shared-transaction enqueue test confirms atomicity and the absence of a second job for the same key. |
| `REQ-1806` | A retry test confirms bounded backoff and transition to `dead_letter` at the attempt limit. |
| `REQ-1807` | A dead-letter test confirms no automatic retry and records the error without secrets. |
| `REQ-1808` | A cancellation test moves the job to `cancelled`, and it is not claimed. |
| `REQ-1809` | A shutdown test confirms draining of running jobs without loss or duplication. |
| `REQ-1811` | An idempotency test confirms no duplicate effect on redelivery. |
| `REQ-1812` | A polling test confirms a bounded polling interval. |
| `REQ-1813` | A unit test checks claim/empty-poll, queue wait, handler result/duration, and requeue counters; the snapshot contains no job identifiers or payload. |
