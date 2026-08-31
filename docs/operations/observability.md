---
description: "Minimum signals for diagnosing the CLI, sync, publishing, and providers."
last_verified: "2026-08-29"
---

# Observability

## Local CLI

Every mutating operation has:

- operation ID;
- plan digest;
- entity/device/provider IDs;
- started/finished timestamps;
- state;
- safe error code;
- append-only steps;
- recovery instruction.

Raw secrets, prompts, and source content are not included in the log.

## Server mode

The following measurements are required:

- API requests, errors and duration;
- auth/login/link failures;
- sync accepted/rejected/conflict;
- publish validation outcome;
- worker queue depth/retry/dead letter;
- object storage errors;
- provider release download failures;
- report volume, triage time, and moderation actions;
- rate-limit and abuse signals;
- platform safety-scan counters (`safety_*`, see runbook `safety-scan.md`).
- SEO build/enrichment outcome and latency, active base/enriched share, rejection/stale reasons, indexing decision, sitemap generation/cache age, and model usage by operator alias without prompt, body, or subject ID (`SPEC-053`).

### Safety-scan signals (`safety_*`)

Source: in-process counters in the worker/API process (`ai_stp_platform.safety.metrics`),
plus the structured log event `safety_scan` / `safety_cli`. Snapshot:

```text
python -c "from ai_stp_platform.safety.metrics import snapshot; print(snapshot())"
```

| Metric | Decision |
|--------|---------|
| `safety_scan_total` | validate/scan volume |
| `safety_scan_duration_ms_avg/max/p50/p95/p99` | suite degradation / hard cap |
| `safety_scan_duration_ms_buckets` | bounded latency distribution; `+Inf` is above the hard-cap bucket |
| `safety_check_total` | number of executions of each `check_id` |
| `safety_check_result_total`, `safety_check_result_by_id_total` | failed/not_run/degraded balance globally and per check |
| `safety_check_duration_ms_avg/max`, `safety_check_duration_ms_buckets` | per-check cost and tail |
| `safety_finding_total` | family:severity pressure |
| `safety_cli_timeout_total` | external CLI hangs |
| `safety_sandbox_mode_total` | bwrap vs env_only coverage |
| `safety_queue_claim_total`, `safety_queue_empty_poll_total` | polling pressure |
| `safety_queue_claimed_total`, `safety_queue_wait_ms_*` | queue throughput and wait |
| `safety_queue_job_*` | handler duration/result |
| `safety_queue_requeued_total` | drain/stale-lease pressure |

Secrets and raw finding bodies are not included in the metrics.

### Safety performance evidence

The normative offline smoke/load corpus runs without network access or external CLIs:

```text
just safety-benchmark --iterations 3 --concurrency 1
```

The result is JSON with `schema_version`, exact local `commit`, fixed
`case_order`, profile, artifact digests, mandatory failures, and a metrics snapshot.
Corpus/order/profile are deterministic; `wall_ms` depends on the CPU, filesystem, and
current load and is used to compare identical environments, not as a
cross-machine success criterion. Production alerts use queue wait, scan tail,
tail, `degraded/not_run`, `+Inf` buckets, and requeue growth; the absence of an exporter does not
remove the local structured event or turn a lack of evidence into success.

## Provider and logs

Server mode uses the OpenTelemetry provider with a configurable exporter and a structured log written to a daily file under `ADR-0039`; an unavailable exporter does not bring down the application. `trace_id` is associated with the span and included in the response envelope alongside `request_id`. Tokens and personal data are not included in the log under `SPEC-013`.

## Principle

A signal is created only if a decision is made based on it. `success` must not be logged before a durable commit or provider verification.
