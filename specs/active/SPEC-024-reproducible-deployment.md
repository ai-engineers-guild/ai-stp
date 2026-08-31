---
description: "SPEC-024: Reproducible deployment with web tier, health, logs, backups and rollback."
last_verified: "2026-08-10"
---

# SPEC-024: Reproducible deployment

## Purpose

> `ADR-0084` removed a separate pre-production tier: there is only one deployed environment.
> `ADR-0086` gave it the name `prod` and removed the renaming boundary that `ADR-0084`
> left open. “Tested on staging” is no longer an acceptance criterion anywhere.
> The requirements of this specification describe the topology, TLS, logs,
> backups, and rollback of the deployed environment and apply in full—with a single
> environment, rollback and backups are more important, not less.

The platform slice runs in an environment that can be recreated, diagnosed, and
rolled back from repository state. The `SPEC-019` foundation is extended with a web
tier in the topology, production TLS and a domain for the deployment host, structured
log collection with correlation and limited retention, PostgreSQL and RustFS backup
and recovery, deployment locking and serialization, abort criteria, documented
rollback to the previous exact artifact, and version, commit, and schema identity
visible in safe diagnostics.

The packaging and operations foundation belongs to `SPEC-019` and `ADR-0040`; this specification does not
redefine it, but completes production deployment hardening under `#84` and owns the requirements
`REQ-24xx`. Solutions for web tier, proxy routing, backups, rollback and
deployment locks belong to `ADR-0044`; observability and readiness -
`SPEC-017` and `ADR-0039`; log and data rules - `SPEC-013`; web application - `#82`,
`#83`, `SPEC-022`, `SPEC-023`; storage - `SPEC-020`.

## Scope

Includes: repository deployment topology for `api`, `worker`, `web`, `docs`,
`PostgreSQL` and `RustFS` behind a single public point `Caddy` (**prod**);
local **dev** compose without Caddy (published by `web`/`api`/`docs`,
same-origin hop via Next rewrite);
environment contract and `.env.example` with names without secret values and separation
dev/prod, including web variables; separate dev and prod images of the frontend; order
execution of migrations and seeding; production TLS, domain and proxy corresponding to the available
deployment host; checks `liveness` and `readiness` and deploy smoke; collection of structure logs
with query-operation correlation and limited storage; backup and
recovery of PostgreSQL metadata and RustFS objects; blocking and serialization
deployments, abort criteria and rollback to the previous exact artifact; visible in
safe diagnostics of version, commit and schema identity.

Excludes: public production release and repository publication; production
user data, SLA, autoscaling and multi-region; deployment
providers; secrets in GitHub or issue text; contents of domain handlers
(`SPEC-018`, `#79`, `#81`), application rules (`SPEC-017`) and web business logic
(`SPEC-022`, `SPEC-023`).

## Terms

- `Staging topology` — repository layout of services `api`, `worker`, `web`,
  `PostgreSQL`, `RustFS` and `Caddy` for the deployed environment.
- `Web tier` - `apps/web` application container with separate dev and prod images;
  in **prod** publicly available only through `Caddy` (`ADR-0044`); to local
  **dev** publishes the `web` port directly, without Caddy.
- `Docs tier` - container of public user documentation from `docs-user-facing/docs/`;
  in dev it is published on `localhost:8011`, in **prod** it is available through a separate
  host `AI_STP_DOCS_HOST`.
- `Env contract` - a set of environment samples with names without values and separation
  dev/prod, including web variables.
- `Deploy lock` - deployment serialization mechanism, eliminating simultaneous
  deployment (`ADR-0044`).
- `Rollback` - return to the previous exact application artifact compatible with
  the current schema and data (`ADR-0044`).
- `Safe diagnostics` - readiness and identity endpoint without secrets according to `SPEC-017`.

## Requirements

- `REQ-2401`: The deployed environment topology adds `web` and `docs` to `api`, `worker`,
  `PostgreSQL`, `RustFS` and `Caddy`; prod compose reproducibly lifts the entire slice,
  and `web` and `docs` in **prod** are publicly accessible only through `Caddy`.
  **Dev-exception:** `docker-compose.dev.yml` lifts `web` and `docs` without Caddy
  (ports per host); same-origin `/v1/*` provides dev-rewrite Next.js to `api`.
- `REQ-2402`: The environment contract is specified by `.env.example` samples with names without
  secret values and dev/prod separation, including web variables
  (`AI_STP_API_BASE_URL`, `NEXT_PUBLIC_APP_URL`, `AI_STP_USER_DOCS_URL`,
  `AI_STP_WEB_PROFILE`, optional build-time `AI_STP_FEATURE_*`,
  `AI_STP_SESSION_SECRET`, `AI_STP_USE_MOCKS` and other required `#82`/`#83`);
  real `.env.dev` and `.env.prod`
  excluded from the index; the absence of a required secret gives a typed failure
  start on `SPEC-017`, and not a quiet default.
- `REQ-2403`: The frontend is assembled with separate dev and prod images: the prod image is minimal
  (standalone Next.js output, minimal runtime, non-root), dev image suitable for
  local development; versions of base images are pinned and updated separately
  verifiable change.
- `REQ-2404`: In **prod** the reverse proxy `Caddy` remains the only one
  public entry point; the main host routes API requests to the `api`, and
  the rest to `web`, docs host routes user documentation to `docs`.
  **Dev exception:** Caddy is missing from dev compose; `web` and `api` publish ports
  to the host, `docs` publishes a port of user documentation; browser-relative
  `/v1/*` (and API docs paths) are rewritten Next in dev to `AI_STP_API_BASE_URL`.
  `PostgreSQL` and `RustFS` are not published outside; `web` refers to `api` by
  internal network, and not through a public address.
- `REQ-2405`: Migrations and seeding are performed in a certain order before receiving traffic;
  readiness blocks traffic until dependencies and migrations are ready (`SPEC-017`).
- `REQ-2406`: Production TLS and a domain corresponding to the available deployment host,
  served by `Caddy` (automatic HTTPS) on the deployment host; local **dev**
  works via plain HTTP on the published port `web` (without reverse proxy).
- `REQ-2407`: Containers have `liveness` and `readiness`; deploy smoke covers
  the landing page, catalog, OAuth, and device listing and revocation on the deployed slice.
- `REQ-2408`: Structural logs are collected with correlation between request and operation and
  limited storage; the log does not contain OAuth tokens, cookies, object bytes,
  private paths and environment values (`SPEC-017`, `SPEC-013`).
- `REQ-2409`: Backup and restore PostgreSQL metadata and objects
  RustFS are defined and rehearsed on the restored copy; recovery is checked and
  the backup and its log do not contain secrets or object bytes.
- `REQ-2410`: Deployment is serialized by locking, re-deployment
  idempotent, abort criteria are defined, and rollback returns the previous exact
  an application artifact and does not change the schema revision in any way.
- `REQ-2418`: Downgrading a schema revision is performed as a separate explicit operation with
  the specified target revision; it fails if the backup copy is not taken in that
  same run, and records the source and target revisions, the name of the copy and the commit.
- `REQ-2411`: Identity of version, commit and schema is visible in safe diagnostics without
  secrets (`SPEC-017`); diagnostics do not reveal environment and token values.
- `REQ-2412`: Clean authorized host unwraps slice from exact commit
  documented runbook commands; required evidence (artifact and commit,
  commands and exit codes, configuration validation, migration and seeding output, checks
  health, backup and restore rehearsal, rollback rehearsal, results
  smoke, failed tests and residual risks) are recorded.
- `REQ-2413`: Pull request code and deployment are executed in physically different
  permanent trust domains; runner roles, users accounts, file systems and
  hosts machines use different resources; CI is not
  receives deployment secrets and does not have an SSH route to the deployment host (`ADR-0046`).
- `REQ-2414`: New pull request run can cancel the previous pull request run, but the new one
  push does not cancel an ongoing deployment; durable stage marker allows the following
  run deterministically repeat the interrupted idempotent forward path.
- `REQ-2415`: SSH identity of the deployment host is secured by the trusted `known_hosts` outside
  network discovery; a key mismatch stops the operation until `rsync` and SSH.
- `REQ-2416`: After internal readiness, independent deployment runner through conventional
  DNS and strict TLS check public responses for liveness, readiness, web and safe
  diagnostics;
  commit, environment and head revision of the schema are as expected.
- `REQ-2417`: Auto deployment only accepts exact bi-parent
  merge commit of the only allowed pull request in `dev`; actor and personal branch
  are included in explicit allowlists, the solution is written without tokens and secrets.

## States and errors

The container service passes `starting`, `healthy` and `unhealthy` according to the result
healthcheck; a dependent service is not considered available until the dependency is truly ready
and migrations (`REQ-2405`). Deployment when a lock is held is serialized rather than
runs in parallel; if the readiness criterion is not met, the deployment is aborted
according to the recorded criterion and does not transfer traffic to an unhealthy artifact. Rollback returns
previous exact artifact; No destructive reverse migration is performed on rollback.
The absence of a mandatory secret results in a typed startup failure, rather than a silent default.

## Security and privacy

Secrets are not included in the repository, GitHub and issue text: only samples are indexed
no values (`REQ-2402`). `PostgreSQL` and `RustFS` are not accessible from the external network; on
in **prod** only `Caddy` (`REQ-2404`) is open to the outside; in local dev - ports
`web`/`api`/`docs`.
Structural logs, backups and secure diagnostics do not contain OAuth tokens,
cookies, object bytes, private paths and environment values (`REQ-2408`, `REQ-2409`,
`REQ-2411`, `SPEC-013`, `SPEC-017`). Long-lived storage credentials are not issued to the
client (`SPEC-020`).

## Compatibility and migration

The environment layout is expanded by adding optional keys with update
samples; changing network topology, restart policy, web tier, routing
proxies, backups, rollback and deployment blocking are reflected in `ADR-0040` and
`ADR-0044`. The transition to production TLS and a domain is performed on the deployment host without changes
boundaries `SPEC-019`. The rollback remains compatible with the current scheme: reverse migration when
rollback does not destroy data, and an incompatible schema change receives a separate
procedure according to `docs/engineering/schema-evolution.md`. Base image versions
are committed and updated with a separate verifiable change.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-2401` | Prod compose lifts `api`, `worker`, `web`, `docs`, `PostgreSQL`, `RustFS` and `Caddy` (`web` and `docs` via Caddy only). Dev compose picks up the same slice without `caddy`, with `web` and `docs` published. |
| `REQ-2402` | Checking the repository confirms dev/prod samples with web and user documentation names without secrets and the absence of real env files; the absence of a mandatory secret results in a typed startup failure. |
| `REQ-2403` | The assembly of dev and prod images of the frontend is underway; The prod image is minimal, non-root and does not contain development tools. |
| `REQ-2404` | Staging/prod: Caddy divides the main host `/v1` → api and the rest → web, and docs host → docs. Dev: no caddy; rewrite/proxy Next for `/v1`, docs published as a separate port. Postgres/RustFS are not accessible from the outside; web → api by internal URL. |
| `REQ-2405` | We check the order of migration and seeding, and readiness blocks traffic until dependencies and migrations are ready. |
| `REQ-2406` | Startup on the deployment host serves production TLS and the domain through `Caddy`; local dev uses plain HTTP on the `web` port without a reverse proxy. |
| `REQ-2407` | Deploy smoke on the deployed slice covers the landing page, catalog, OAuth, and device listing and revocation. |
| `REQ-2408` | Checking the logs confirms the request-operation correlation, limited storage, and the absence of tokens, cookies, object bytes, paths, and environment values. |
| `REQ-2409` | Rehearsing a PostgreSQL and RustFS backup and restore on the restored copy confirms the recovery and the absence of secrets in the copy. |
| `REQ-2410` | The test confirms deployment serialization, retry idempotency, abort criterion, and rollback to a previous artifact leaving the schema revision unchanged. |
| `REQ-2418` | The test confirms that the downgrade requires an explicit target revision and fails without a backup of that run. |
| `REQ-2411` | Safe diagnostics shows version, commit and schema without secrets and environment values. |
| `REQ-2412` | Deploying from the exact commit using documented commands to a clean host is reproducible; the evidence recorded is complete. |
| `REQ-2413` | PR job leaves marker/process; deployment runner does not see it, has a different name and is inventory on a different host/user; CI does not read secret and does not reach SSH endpoint. |
| `REQ-2414` | Two pushes around an artificially long deployment do not cancel the first one; fault injection leaves a marker after transfer/migrate/start, and the replay ends deterministically. |
| `REQ-2415` | The correct pinned host key passes; another key fails before the tree is transferred; The runbook describes the key overlap. |
| `REQ-2416` | Failure of DNS, certificate chain, nginx/Caddy route, expected SHA or schema revision individually brings down the external probe. |
| `REQ-2417` | Direct push, unauthorized or non-allowlisted actor/head, SHA without PR association and ambiguous association are rejected before reading deployment secrets. |
