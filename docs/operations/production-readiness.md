---
description: "Operator procedure for evidence-gated production readiness and optional OpenObserve."
last_verified: "2026-08-28"
---

# Production readiness

Normative requirements belong to `SPEC-032` and `ADR-0071`. This procedure
collects evidence and deploys nothing: deployment is performed by the
`ADR-0109` pipeline—a green `check` advances `deploy/prod`. The decision to release
is made by the agent based on a current evidence set (`ADR-0118`).

## Optional OpenObserve profile

OpenObserve is a diagnostic single-node profile. It is not a dependency of
`/v1/health/ready`, an audit store, or a backup source. Run it only together with the
base stack and only with secrets in a gitignored runtime environment:

```bash
docker compose -f docker-compose.prod.yml \
  -f deploy/docker-compose.observability.yml \
  --env-file .env.prod up -d openobserve
```

The UI is bound to the loopback host. Use an SSH tunnel or an already
approved administrative boundary for access; do not expose the UI or OTLP externally. The API
uses a separate ingestion account through a runtime header. The initial root
account is not passed to the application. Stopping the profile does not delete its named volume;
data deletion is a separate destructive operation requiring owner confirmation.

`AI_STP_OPENOBSERVE_IMAGE` is required and contains an owner-approved immutable image
digest. Compose deliberately refuses to start the profile without it: a floating tag is not
a release identity.

When the exporter is unavailable, the application continues to operate, but release evidence
must record a failed telemetry/alert check and cannot be `complete`.

## Evidence checklist

Before release, record the exact commit, schema/config/policy revisions,
timestamp/expiry, safe outcomes, and residual risks. Env values,
credentials, tokens, raw logs, personal data, or object bytes must not be included.

| Check | Command / observation | Expected result |
| --- | --- | --- |
| Base topology | `docker compose -f docker-compose.prod.yml config` | Output contains no OpenObserve or public OTLP port. |
| Profile isolation | compose config with override | Loopback UI only; OTLP is not exposed. |
| Health | `curl -fsS "$ORIGIN/v1/health/ready"` | `200` without depending on the exporter. |
| Telemetry failure | deployed environment with an unavailable endpoint | API remains available; evidence records failure. |
| Recovery | `deploy/backup.sh` → isolated `restore.sh --yes` | PostgreSQL/RustFS integrity and readiness. |
| Rollback | `deploy/rollback.sh --yes` in the deployed environment | Previous exact artifact under lock; no downgrade. |
| Abuse | deterministic API test | `429` and `Retry-After`; the signal does not change the lifecycle. |

## Adopted single-node MVP policy

Until a separate review, the following values apply: API availability is
`99.5%` over 30 days; p95 public API latency is no more than `750 ms`; the error budget is
`0.5%`. OpenObserve telemetry is retained for `14 days`, and the operator leaves at least
`20%` free space on the volume filesystem. Evidence is valid for `24 hours`.

The rate limit is `100` requests per `60 seconds` for the entire process and `1000` requests
per `3600 seconds` from a single transport address, with no more than `2048` keys in the
address table (`ADR-0128`). This is deliberately basic single-node protection: browser
state and forwarded headers do not become a source of authority. Login, reports, and
sensitive changes require a separate policy class and a check at the server boundary
before production approval.

Alert routes remain on a local/test receiver until the owner explicitly selects an external
channel. The absence of a real receiver or recovery rehearsal makes evidence
`incomplete`, not implicitly successful.
