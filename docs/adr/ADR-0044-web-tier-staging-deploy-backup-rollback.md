---
description: "Decision on the staging web tier, Caddy routing, backups, rollback, and deployment locking for #84."
last_verified: "2026-08-07"
---

# ADR-0044: Staging Web Tier, Backups, and Rollback

Status: accepted. The staging tier was superseded by `ADR-0084-single-deployed-environment.md`: there is one deployed environment, updated directly. The backup, rollback, and concurrent-deployment locking mechanisms in this record remain fully applicable and become more important because errors are no longer caught by a separate tier. Read this record for those mechanisms and the context of the original choice.

## Context

`ADR-0040` established the runtime topology for `api` and `worker`: multi-stage
Python images, the `Caddy` reverse proxy as the only public endpoint, `compose` for
dev and prod, network isolation, healthchecks, and a restart policy. It also
explicitly left production hardening of staging to `#84`. `SPEC-019` repeated this
boundary, and `SPEC-024` now owns the staging requirements.

With the introduction of `apps/web` (`#82`, `#83`), the topology lacks three things
that `ADR-0040` did not address. First, the web has its own build—`bun`, Next.js, and
a Node runtime rather than the Python image from `ADR-0040`—so its packaging requires
a separate decision. Second, the single public endpoint now serves two different
backends on one domain—static content and server-side web rendering, and the API—so
the routing rule must be established. Third, `#84` requires production TLS and a
domain, rehearsable PostgreSQL and RustFS backups and recovery, deployment
serialization, and documented rollback to the exact previous artifact—mechanisms
absent from `ADR-0040`.

`ADR-0040` owns the topology skeleton; observability and readiness belong to
`SPEC-017` and `ADR-0039`; storage to `SPEC-020`; and the web stack to `ADR-0043`.
This record owns only the staging web tier, proxy routing, backups, rollback, and
deployment locking.

## Options

Frontend image:

1. A separate web build: `bun install` and `bun run build` with Next.js standalone
   output, followed by a minimal non-root Node runtime, with separate dev and prod
   images. A small prod image and a clear boundary from the Python image. The cost is
   a second image toolchain.
2. One image with Python and Node. Fewer files, but mixes two runtimes, bloats the
   image, and couples unrelated updates.

Public-endpoint routing:

1. `Caddy` remains the only public endpoint and splits traffic by path: API traffic
   goes to `api`, everything else to `web`; `web` reaches `api` over the internal
   network. One domain, one entry point, with the database and storage closed.
   Consistent with `ADR-0040`.
2. A separate public endpoint for the web. A simpler rule, but a second external
   surface and a departure from `ADR-0040`, where `Caddy` is the only public endpoint.

Backup and recovery:

1. A logical PostgreSQL dump and RustFS object copy on a schedule and on demand, with
   limited retention and rehearsable recovery. Simple and reproducible, with no
   secrets in the backup.
2. A volume snapshot only. Fast, but tied to the host and harder to validate through
   recovery on a clean host.

Rollback and deployment locking:

1. Rollback by redeploying the exact previous image artifact and commit without a
   destructive reverse migration; a lock serializes deployments; an abort criterion
   prevents switching traffic to an unhealthy artifact. Compatible with the current
   schema.
2. Rollback by reversing the schema migration. Destructively moves data backward and
   is dangerous after records have already been accepted; rejected as an application
   rollback method. `ADR-0081` revised the second half: revision downgrade remains
   prohibited within rollback and became a separate explicit operation with a backup.

## Decision

A separate frontend image, traffic splitting at `Caddy`, logical backups, and
rollback by redeployment under a lock are accepted.

Frontend image:

- The web is built separately from the `ADR-0040` Python image: the prod image builds
  Next.js standalone output through `bun` and runs it on a minimal Node runtime as a
  non-root user; the dev image supports local development with source files. Dev and
  prod use separate image files. Base-image versions are pinned.
- For standalone output, `apps/web` enables the corresponding Next.js build mode;
  this is a requirement for the `#82`/`#83` artifact, not for the contract.

Routing:

- In **staging/prod**, `Caddy` remains the only public endpoint (`ADR-0040`) and
  splits traffic by path: the API prefix and related service paths go to `api`, and
  everything else to `web`. `web` reaches `api` over the internal network, not
  through the public address. `PostgreSQL` and `RustFS` are not exposed.
- On the staging host, `Caddy` serves production TLS and the domain using automatic
  HTTPS.
- **Dev exception:** `docker-compose.dev.yml` does not include Caddy. The browser
  origin is the exposed `web` port; the Next.js dev server rewrites same-origin
  `/v1/*` (and docs paths) to `AI_STP_API_BASE_URL`. This does not change the
  staging/prod edge.

Backup and recovery:

- A staging backup consists of a logical PostgreSQL dump and a RustFS object copy on
  a schedule and on demand, with limited retention; recovery is rehearsed against
  staging data and verified. The backup and its log contain neither secrets nor
  object bytes beyond the backup data itself.

Rollback and locking:

- A lock serializes deployment; retries are idempotent; if the readiness criterion is
  not met, deployment aborts without switching traffic to the unhealthy artifact.
  Rollback redeploys the exact previous image artifact and commit and remains
  compatible with the current schema; no destructive reverse migration runs during
  rollback. An incompatible schema change receives a separate procedure under
  `docs/engineering/schema-evolution.md`.

Version, commit, and schema identity are exposed through the safe diagnostics of
`SPEC-017`, without secrets or environment values. Deployment, backup, recovery, and
rollback procedures are documented as runbooks in `docs/operations/runbooks/`.

## Consequences

- A second image type (web) and separate dev and prod frontend image files are
  introduced; `SPEC-024` gains requirements for the web tier, routing, backups,
  rollback, and locking; `docs/operations/runbooks/` gains a staging deployment
  runbook.
- Prod `docker-compose` adds a `web` service and a `Caddy` routing rule; dev
  `docker-compose` adds `web` with a host port and without Caddy (rewrite to Next);
  the environment contract gains web variables separated by dev/prod (`SPEC-024`
  `REQ-2402`).
- Backup and rollback are rehearsed on staging and produce recorded evidence for
  `#84`; rollback does not destroy data through a reverse migration.
- Security: in staging/prod, `Caddy` remains the only public endpoint; local dev
  exposes `web`/`api`; the database and storage remain closed; logs, backups, and
  diagnostics contain no secrets (`SPEC-013`, `SPEC-017`).
- Required checks: routing and network isolation, web dev/prod image builds,
  migration and seed ordering, deployment smoke, backup and recovery rehearsal,
  rollback rehearsal, and deployment serialization.
- Rollback of the decision itself: the image, routing, backups, and rollback procedure
  are encapsulated in `compose`, images, and the runbook; changing any of them
  requires a new ADR.

## Reconsideration Conditions

The decision will be reconsidered if load or availability requires an orchestrator
such as Kubernetes (shared with `ADR-0040`); if `Caddy` ceases to be the public
endpoint; if the staging host requires a TLS model other than automatic HTTPS; or if
there is a demonstrated need for rollback with a schema migration rather than
artifact redeployment.
