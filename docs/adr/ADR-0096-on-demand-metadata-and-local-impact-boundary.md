---
description: "ADR-0096: On-demand GitHub metadata, local blast radius, and shared context estimator."
last_verified: "2026-08-15"
---

# ADR-0096: On-demand metadata and local impact boundary

Status: proposed. Partially supersedes `ADR-0094` for the GitHub archive
read-model and account blast-radius delivery.

## Context

`ADR-0094` introduced server-owned archive history and account blast radius for
Web. The implementation proved broader than the product needed: the archive
panel is visible for an active/unavailable repository, the worker continuously
maintains a derived cache, and Web shows all active devices in the account
without a proven relationship to the installation. At the same time, the CLI
already owns the exact local blast radius and context/cost report. The local
SaaS standalone image was mistakenly substituted for the dev runtime and lost
the dev-only `/v1` rewrite, even though media bytes remained available through
the API.

## Options

1. Extend the periodic archive and account blast models. This preserves the
   current code but maintains unnecessary jobs/storage and does not correct the
   ownership boundary.
2. Move the GitHub call directly into the browser and retain server impact.
   This is less code, but places arbitrary external fetch/CORS/rate limits on
   the client.
3. Read limited server metadata for an exact coordinate on demand, return blast
   radius to the CLI-only boundary, and extract a shared pure context estimator
   for an honest public setup projection.

## Decision

Option 3 is selected.

- GitHub stars/archive are read with one best-effort request when detail is
  opened; the server resolves the source from the exact passport. The UI shows
  only stars and a conditional `Archived` badge next to the GitHub link.
- Periodic archive observation/history and the separate evidence panel are
  discontinued.
- Blast radius remains exclusively in the local CLI report. Server/Web surfaces
  are removed; Web does not enumerate devices, projects, or installations.
- The deterministic context estimator becomes a shared domain implementation
  for the CLI and server. Web receives only the absolute budget of the visible
  exact setup; the local baseline/delta remains in the CLI.
- Cost in Web is calculated client-side only from an explicitly entered rate
  and is not called actual usage.
- The local environment uses dev compose/Next rewrite without Caddy. The
  production path split remains Caddy's responsibility and is not changed by
  this decision.

## Consequences

Unnecessary jobs, storage, and API and interface surfaces are removed, but a
compatibility path is required for archive jobs already queued and a direct
migration only for derived tables. GitHub metadata may be absent because of a
rate limit or transport failure without breaking the card. The card makes one
external request; the catalog list makes none. The shared estimator requires
moving the actual logic, not creating a third copy. The Web estimate is
reproducible for artifacts visible to the server but intentionally does not
know the local installed baseline.

`ADR-0094` is superseded by this decision for the GitHub archive read model and
account blast-radius delivery. Its canonical copy/deep-link and other consumer
decisions remain in force.

## Reconsideration conditions

Reconsider this decision when there is a proven server-owned installation
graph, a mandatory GitHub SLA/credentialed quota, actual model usage telemetry,
or a safe local-agent bridge with a separate user-consent contract.
