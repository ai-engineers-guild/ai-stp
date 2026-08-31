---
description: "SPEC-019: Runtime deployment and operation."
last_verified: "2026-08-10"
---

# SPEC-019: Runtime deployment and operation

## Purpose

The server runtime gets reproducible packaging and operations for dev and prod: per-environment configuration without secrets in the repository, containers for `api`, `worker`, and public user documentation, a reverse proxy, network isolation, health checks, unhealthy-container restarts, and daily file logs. Production hardening with real TLS, backups, and recovery remains in `#84`; this specification defines the foundation and its requirements.

## Scope

Includes the env layout for dev and prod with samples, multi-stage images for `api`, `worker`, and user documentation, the `Caddy` reverse proxy for **prod**, direct host-publishing of `web`/`api`/`docs` for **dev** (without Caddy), `docker-compose` for dev and prod, network isolation, healthchecks for `liveness` and `readiness`, a restart policy, and file logs on a mounted volume. Excludes real ACME and a domain, production backups and the rollback procedure (`#84`), domain-handler contents (`SPEC-018`, `#79`, `#81`), and application rules (`SPEC-017`).

## Terms

- `Env layout` - a set of configuration files for environments, where only samples without secrets are included in the repository.
- `Reverse proxy` - `Caddy`, the only publicly accessible entry point of the **prod** stack. In **dev** public points are published ports of `web`, `api` and user documentation; same-origin `/v1/*` provides dev-rewrite Next.js.
- `Healthcheck` - `liveness` and `readiness` container check that controls dependency readiness and restart of unhealthy container.

## Requirements

- `REQ-1901`: The dev and prod configurations are specified by separate env files, only samples without secrets are included in the repository, and the real `.env.dev` and `.env.prod` are excluded from the index.
- `REQ-1902`: `api`, `worker`, and user documentation are built as multi-stage images, where the dev image is suitable for local development and the prod image is minimal or static.
- `REQ-1903`: The `Caddy` reverse proxy serves **prod** (ACME/domain — `#84` / `SPEC-024`). **Dev exception:** local `docker-compose.dev.yml` does not start Caddy; the browser accesses the published `web`, with same-origin `/v1/*` reaching `api` through a Next.js dev rewrite.
- `REQ-1904`: `docker-compose` **prod** starts `api`, `worker`, `docs`, `PostgreSQL`, `RustFS`, and `Caddy`. `docker-compose` **dev** starts `api`, `worker`, `docs`, `PostgreSQL`, `RustFS`, and `web` (without Caddy), publishing the `web`, `api`, and `docs` ports to the host.
- `REQ-1905`: `PostgreSQL` and `RustFS` are not published on the Internet and are only available via the internal network. In **prod** only the reverse proxy is exposed to the outside; in **dev** `web`, `api` and `docs` are open to the outside (not the database or object storage).
- `REQ-1906`: Containers have a healthcheck on `liveness` and `readiness`, dependent services start when the dependency is ready, and an unhealthy container is restarted by the restart policy.
- `REQ-1908`: Daily file logs are written to a mounted volume with daily rotation.
- `REQ-1909`: A clean `compose up` reproducibly brings the stack to actual readiness.

## States and errors

Based on its healthcheck result, a containerized service transitions through `starting`, `healthy`, and `unhealthy`. A dependent service is not considered available until its dependency is actually ready. The restart policy restarts an unhealthy service. A missing required secret in the env file causes a typed application startup failure under `SPEC-017`, rather than startup with a silent default.

## Security and privacy

Secrets are not included in the repository: only samples without values are indexed. `PostgreSQL` and `RustFS` are not accessible from the external network. The reverse proxy does not log request bodies or secrets. File logs are subject to a closed set of fields and a ban on tokens and personal data for `SPEC-017` and `SPEC-013`.

## Compatibility and migration

The env layout is extended by adding optional keys and updating the samples. A change in network topology or restart policy is reflected in `ADR-0040` or a new ADR for the added tier. The transition to production TLS and a domain is performed in `#84` without changing the boundaries of this specification. Base image versions are pinned and updated in a separate verifiable change.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-1901` | Checking the repository confirms the presence of samples without secrets and the absence of real env files in the index. |
| `REQ-1902` | The `api`, `worker` and `docs` images are built for dev and prod, and the prod image does not contain unnecessary development tools. |
| `REQ-1903` | Prod rises from `Caddy`; dev compose does not contain the `caddy` service, and `/v1/*` from the origin of the web reaches the API (rewrite/proxy). |
| `REQ-1904` | `docker-compose` prod raises api/worker/docs/postgres/rustfs/caddy (+ web by SPEC-024); dev - api/worker/web/docs/postgres/rustfs without caddy. |
| `REQ-1905` | Network test confirms that `PostgreSQL` and `RustFS` are not accessible from the outside; prod - only through a proxy, dev - through published web/api/docs. |
| `REQ-1906` | Healthcheck reflects `liveness` and `readiness`, the dependent service waits for the dependency to be ready, and the unhealthy container is restarted. |
| `REQ-1908` | Checking the volume confirms the daily file log with rotation. |
| `REQ-1909` | A clean `compose up` reproducibly brings the stack to actual readiness. |
