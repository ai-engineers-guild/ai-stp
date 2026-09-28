---
description: "Consolidate every compose file under deploy/ and every Dockerfile under deploy/docker/, with one app Dockerfile for all Python stages."
last_verified: "2026-09-27"
---

# ADR-0217: Deployment files live under deploy/

Status: accepted. Implemented behavior is recorded in SPEC-019, SPEC-024 and `standards/docker.md`.

## Context

The container surface had grown organically: three Dockerfiles at the
repository root (`Dockerfile`, `Dockerfile.user-docs`,
`Dockerfile.worker-safety`), two more under `apps/web/`, four compose files
at the root and one under `deploy/`. The same application's runtime
definition was scattered across two directory levels, and the file named
plainly `Dockerfile` was actually three images.

`Dockerfile.worker-safety` carried a verbatim copy of the main file's
`base` stage as `app-base` — same pinned digests, same `COPY` list, same
`uv sync` — because Docker cannot `FROM` a stage defined in another file.
The copy was held in sync by tests and convention, not by a mechanism, and
had already drifted once: it omitted `docs-user-facing/legal` that `base`
copied.

Corporate-server deployment had no compose expression at all:
`docker-compose.corporate-local.yml`, despite the name, patches the *dev*
stack for local acceptance of the corporate web profile.

## Options

- Keep the flat root layout and hand-maintain the `app-base` copy. Rejected:
  the duplication is guaranteed to drift, and the split locations keep
  deceiving readers about which file builds what.
- Merge the safety stages into the root Dockerfile but leave compose files
  at the root. Rejected: it fixes the duplication but not the scatter.
- Consolidate: all compose files under `deploy/`, all Dockerfiles under
  `deploy/docker/`, one app Dockerfile holding every Python stage.

## Decision

All compose files live in `deploy/compose.*.yml` and all Dockerfiles in
`deploy/docker/Dockerfile.*`:

- `Dockerfile.app` carries `base` plus `worker`, `api`, `content-import`,
  `go-tools`, `tools` (`FROM base`) and `worker-safety` (`FROM worker`).
  The duplicated `app-base` is gone; `worker-safety` now inherits
  migrations, the safety env defaults and `docs-user-facing/legal` from the
  same base as every other runtime image.
- `Dockerfile.web` carries `dev` and `prod` targets, built from the
  repository root and narrowed by `Dockerfile.web.dockerignore`.
- `Dockerfile.docs` is the former `Dockerfile.user-docs`.
- `compose.dev.yml` and `compose.prod.yml` are the stacks;
  `compose.corporate.yml` is the new corporate-server overlay on prod that
  pins the `corporate_hub` web build profile and its feature exclusions;
  `compose.corporate-local.yml`, `compose.seo-enrichment.yml` and
  `compose.observability.yml` remain overlays on the stacks they patch.

Compose files run with `deploy/` as the project directory: build contexts
name `..` and bind mounts and `env_file` paths reach the repository root
through `../` or stay inside `deploy/` (`./geoip`, `./cliproxy`,
`./litellm`), so a file works identically from any caller's cwd.

## Consequences

`just infra-static`, `infra-build`, `infra-up`/`infra-down`,
`deploy/lib.sh`, `run.sh`, `verify.sh`, `load-apparmor.sh`, the deploy
contract tests and the runbooks all name the new paths.
`docker compose config -q` renders every
declared combination including `prod + corporate`.

The deploy host unpacks the same tree, so `AI_STP_COMPOSE_FILE` defaults
change in place and existing `.env.prod` files are untouched.

Compose derives the project name from the project directory; moving the
files under `deploy/` would rename the project to `deploy` and orphan the
named volumes (`pgdata`, `rustfs`, `osv_offline`, `clamav_db`, `logs`).
Both stacks pin a top-level `name:` — `ai_stp` for prod (the documented
deployment root is `~/ai_stp`, so the name is identical to the one it
replaces) and `ai-stp` for dev — so the volumes are untouched. A host with
a non-default root overrides with `COMPOSE_PROJECT_NAME`, which still beats
the `name:` key.

Rollback of this change is a plain revert: no data, volume, or image-name
movement is involved.

## Revisit conditions

Revisit if a host ran under a project name other than `ai_stp`/`ai-stp`
and its named volumes did not migrate, or if a new runtime mode needs a
third base stack rather than an overlay.
