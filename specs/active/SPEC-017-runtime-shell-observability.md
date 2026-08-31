---
description: "SPEC-017: Server application shell and observability."
last_verified: "2026-08-05"
---

# SPEC-017: Server application shell and observability

## Purpose

The `apps/api` and `apps/worker` server entry points receive a deterministic shell: factory-based application construction, a managed dependency lifecycle, a unified machine response envelope, safe error mapping, independent liveness and readiness checks, and observability. The shell contains no web or CLI business rules and does not duplicate local logic. `SPEC-010` remains the owner of platform requirements as a whole; only the runtime layer is described here.

## Scope

Includes the app factory, `lifespan`, typed settings, binding responses to the `ai_stp_foundation.envelope` envelope, request and trace correlation, mapping exceptions to the code registry, `liveness` and `readiness` endpoints, OpenAPI generation and verification against `#71` fixtures, an OpenTelemetry provider, and structured logging. Excludes the database schema and object storage (`SPEC-010`, `#79`), sign-in, accounts, and devices (`SPEC-002`, `#80`), registry and catalog domains (`#81`), the job queue (`SPEC-018`), and deployment packaging (`SPEC-019`).

## Terms

- `App factory` — a pure function that builds an application instance from validated settings without module-level global application state.
- `Envelope` — the unified machine response envelope `SuccessEnvelope`/`ErrorEnvelope` from `ai_stp_foundation.envelope`.
- `Readiness` — readiness to accept traffic, false until migrations are applied and required dependencies are available.
- `Observability provider` — the cross-cutting OpenTelemetry and structured-logging layer shared by `api` and `worker`.

## Requirements

- `REQ-1701`: `api` and `worker` are built by a deterministic factory from validated settings without module-level global application state.
- `REQ-1702`: Required dependencies are started in `lifespan` and released during shutdown; an unavailable required dependency produces a typed startup failure, not a deferred error on the first request.
- `REQ-1703`: Settings come only from explicit env sources through a typed model without secret defaults; a missing required secret produces a typed startup failure.
- `REQ-1704`: A `/v1` error uses the `ErrorEnvelope` / `CliError` envelope from `ai_stp_foundation.envelope` (the same wire format as the CLI). Success carries the **resource body** from the `#71` models (not the CLI `SuccessEnvelope`); for mutations, `operation_id` is in the `X-Operation-Id` header and/or body if the resource model declares it. Rule owner: `docs/contracts/http-api.md` and `packages/contracts`.
- `REQ-1705`: Every response carries `X-Request-Id` correlation (the resource body does not duplicate it); an incoming header is accepted and propagated, and the outgoing value is returned; `trace_id` is associated with the OpenTelemetry span.
- `REQ-1706`: An unhandled exception maps to `AI_STP_INTERNAL` with the registry exit class and without a stacktrace or secrets in the response; the `validation`, `auth`, `conflict`, `rate`, `dependency`, and `internal` categories map to registered codes, and codes and statuses come from the shared table without magic numbers in handlers.
- `REQ-1707`: `liveness` is independent of dependencies and does not access the database or storage.
- `REQ-1708`: `readiness` is false while migrations are not applied and required `PostgreSQL` and `RustFS` dependencies are unavailable; the response lists unready dependencies from a closed set.
- `REQ-1709`: OpenAPI is generated from code, and an equivalence check proves semantic equivalence with the `#71` fixtures; drift fails the check.
- `REQ-1710`: The observability provider is initialized as a cross-cutting layer, the exporter is configured, and an unavailable backend does not crash the application.
- `REQ-1711`: The structured log is written to a daily file rotated at midnight and to stdout; fields are restricted to a closed set; tokens and personal data are not logged, and `SPEC-013` remains the rule owner.

## States and errors

The application has `starting`, `ready`, and `stopping` startup states. Before `ready`, it responds to `liveness`, but `readiness` remains false. Failure of a required dependency during startup is a typed startup error and does not transition the application to `ready`. Response errors distinguish the `validation`, `auth`, `conflict`, `rate`, `dependency`, and `internal` categories; each maps to a registered `AI_STP_*` code with its exit class. An unhandled exception always becomes `AI_STP_INTERNAL` without leaking internal details.

## Security and privacy

Secrets come only from env sources and have no defaults. An error response contains no stacktrace, secret values, or internal paths. Structured logging uses a closed field set and does not write tokens or personal data. The observability provider does not export secret or request-payload contents.

## Compatibility and migration

Resource and error bodies follow the directed compatibility rules in `docs/engineering/schema-evolution.md`: the producer builds strict models and does not emit unknown fields, while the consumer tolerates optional additions. OpenAPI is a projection of code, while contract truth lives in the `#71` fixtures; a breaking change receives a new version under `docs/contracts/http-api.md`. The structured-log format is extended only by adding optional fields.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-1701` | A factory test builds two independent application instances without shared global state. |
| `REQ-1702` | A startup test with an unavailable required dependency gets a typed failure rather than an error on the first request. |
| `REQ-1703` | A negative test with a missing required secret gets a typed startup failure without a secret default. |
| `REQ-1704` | ASGI contract test: success is a `#71` resource body without the CLI success envelope; error is an `ErrorEnvelope` with `AI_STP_*`. |
| `REQ-1705` | A correlation test verifies the `X-Request-Id` header, propagation of an incoming value, and association of `trace_id` with the span. |
| `REQ-1706` | An unhandled-exception test gets `AI_STP_INTERNAL` without a stacktrace or secret, and the category matrix maps to the code registry without literals. |
| `REQ-1707` | The `liveness` test succeeds while the database is unavailable. |
| `REQ-1708` | The `readiness` matrix covers missing migrations, database, and storage and lists unready dependencies. |
| `REQ-1709` | The OpenAPI-to-`#71`-fixture equivalence check fails on artificial drift. |
| `REQ-1710` | An observability test starts the application with an unavailable exporter without failure. |
| `REQ-1711` | A log test confirms the daily file, closed field set, and absence of tokens and personal data. |
