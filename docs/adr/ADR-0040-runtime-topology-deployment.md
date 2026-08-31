---
description: "Decision on runtime topology: multi-stage images, Caddy reverse proxy, dev and prod compose, network isolation, health checks, and watchdog."
last_verified: "2026-08-07"
---

# ADR-0040: Runtime topology and deployment

Status: accepted.

## Context

The platform needs reproducible packaging of `api` and `worker` for local development and production. `ADR-0009` selected PostgreSQL and RustFS, `SPEC-010` requires that PostgreSQL and RustFS not be exposed to the internet, and `SPEC-017` requires separate liveness and readiness checks. The topology must define how images are built, how external traffic enters, how the network is isolated, how health is checked, and how an unhealthy container is restored. Production hardening of staging with real TLS, backups, and rollback belongs to `#84`; this record establishes the skeleton.

## Options

1. One image for the entire application and direct port exposure for services. Simple, but exposes the database and storage externally and mixes `api` and `worker` in one process.
2. A Kubernetes-class orchestrator from day one. Powerful, but excessive for the MVP and adds operational cost before it is needed.
3. Multi-stage `api` and `worker` images, `Caddy` reverse proxy as the only public endpoint, `docker-compose` for dev and prod, an internal network for database and storage, health checks, and restart policy.

## Decision

Option 3 is accepted.

- `api` and `worker` use multi-stage images: the dev image supports development, while the prod image is minimal;
- the `Caddy` reverse proxy serves **prod/staging** and is the only publicly accessible endpoint there; real ACME and the domain belong to `#84` / `SPEC-024`;
- **Dev exception:** `docker-compose.dev.yml` does not start Caddy; `web` and `api` are exposed on the host, and Next.js dev rewrite provides same-origin `/v1/*`;
- **prod** `docker-compose` starts `api`, `worker`, `PostgreSQL`, `RustFS`, and `Caddy` (plus `web` under `ADR-0044`); **dev** starts `api`, `worker`, `web`, `PostgreSQL`, and `RustFS` without Caddy;
- `PostgreSQL` and `RustFS` are available only on the internal network and are not externally exposed;
- containers have health checks for `liveness` and `readiness`, and dependent services start when dependency readiness conditions are met;
- restart policy returns an unhealthy container to service;
- daily file logs are written to a mounted volume under `SPEC-019` and `ADR-0039`.

Configuration is supplied through separate environment env files; only secret-free examples enter the repository.

## Consequences

- `SPEC-019` receives packaging and operational requirements, while `#84` completes production hardening of staging;
- network isolation satisfies the `SPEC-010` prohibition on exposing database and storage;
- health checks rely on `readiness` from `SPEC-017`, so a dependent service does not start before its dependency is ready;
- base-image versions are pinned and updated in a separate verified change;
- a reverse proxy is added as an operational component without business logic.

## Reconsideration conditions

This decision will be reconsidered if load or availability requirements demand a Kubernetes-class orchestrator, or if the staging/prod deployment model requires a public entry point other than the `Caddy` reverse proxy. Local dev without Caddy is an established exception and does not remove Caddy from staging/prod.
