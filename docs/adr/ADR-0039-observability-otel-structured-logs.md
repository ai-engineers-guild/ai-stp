---
description: "Decision on observability: an OpenTelemetry provider, trace correlation in the envelope, and daily structured file logs."
last_verified: "2026-08-05"
---

# ADR-0039: Observability through OpenTelemetry and structured file logs

Status: accepted.

## Context

The `api` and `worker` server applications need observability from day one, but `docs/engineering/tech-stack.md` establishes that APM and SX are not mandatory core dependencies, while `AGENTS.md` prohibits secrets and personal data in logs. `SPEC-017` requires request correlation, binding `trace_id` to a span, and a structured log with a closed field set. A solution is needed that provides tracing and structured logging without vendor lock-in or sensitive-data leakage.

## Options

1. A specific APM vendor and its agent. Fast to start, but creates vendor lock-in and a mandatory external core dependency, contrary to `tech-stack.md`.
2. Unstructured stdout logging only. Simple, but provides no tracing between a request and job and is difficult to parse mechanically.
3. An OpenTelemetry provider with a configurable exporter and structured logging to a daily file and stdout, without selecting a backend in the MVP.

## Decision

Option 3 is accepted.

Observability is a cross-cutting layer of the application's shared core:

- the OpenTelemetry provider is initialized by the application factory and instruments the `api` and `worker` boundaries;
- the exporter is configured: stdout or a collector in dev and OTLP in prod, while the MVP selects no specific backend;
- an unavailable exporter does not crash the application;
- `trace_id` is bound to the span and included in the response envelope beside `request_id`, providing correlation between an API request and background job;
- structured logs are written to a daily file rotated at midnight and to stdout, fields are limited to a closed set, and tokens and personal data are not logged.

The prohibition on tokens and personal data in logs belongs to `SPEC-013`; this decision applies but does not redefine it.

## Consequences

- dependencies are added for `opentelemetry-sdk`, FastAPI, SQLAlchemy, and asyncpg instrumentation, and the OTLP exporter, each addressing a concrete observability gap;
- a structured-logging dependency writes a daily file on a mounted volume under `SPEC-019`;
- there is no APM vendor lock-in, and a backend can be selected later without application-code changes;
- tests confirm startup with an unavailable exporter, `trace_id` binding to a span, and absence of tokens and personal data from logs.

## Reconsideration conditions

This decision will be reconsidered if a demonstrated need arises for a specific observability backend with special format requirements, or if OpenTelemetry instrumentation costs exceed the value of tracing at observed volume.
