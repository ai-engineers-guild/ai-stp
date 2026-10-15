---
description: "Exact-source deployment, settlement and verification."
last_verified: "2026-10-15"
---

# Deployment

The source owners are `.github/workflows/deploy.yml`, `deploy/deploy.sh`,
`deploy/lib.sh` and the compose files under `deploy/`. Use their current commands;
do not reconstruct a deployment from historical session notes.

## Prerequisites

The authorized host needs Docker Engine/Compose, Git, curl and flock. Actual
`.env.prod` and deployment environment files stay on the host, outside source
synchronization. `.env.prod.example` lists the required names. Validate through
`just infra-env-check` before effects, including `AI_STP_SESSION_SECRET`,
`AI_STP_CATALOG_CURSOR_SIGNING_SECRET`, database/storage and content-import settings.
Never print their values. Do not create backups or snapshots unless requested.

GitHub repository variables `AI_STP_PUBLIC_ORIGIN` and `AI_STP_DOCS_ORIGIN` select
the public application and documentation origins verified after deployment.
They must be configured; a missing docs origin is not a successful skipped check.

## Promotion and activation

A successful push-triggered `check` on `main` lets the deployment workflow advance
`deploy/prod` to that exact qualified SHA. The production host is not a CI runner;
its timer fetches the public repository anonymously and initiates deployment.
No production SSH credentials are stored in Actions.

The host locks deployment, validates its environment, transfers the exact source,
builds images, migrates/initializes dependencies and starts services before health
checks. Source transfer preserves host-owned environment, state, volumes and runtime
files. Never use a broad deletion or Docker prune against a shared host.

`.deploy-state/in-progress` identifies an unfinished operation and stage.
`.deploy-state/current` records the last settled release. Inspect these markers and
service logs after interruption; resume the original operation through the owning
deploy script. A public health response may precede settlement of the host marker.

## Verification and recovery

Verify all three: the successful exact-SHA workflow, `/v1/system/version` matching
the promoted commit, and the settled host marker without an in-progress operation.
Check the application and docs origins and read back serving source against that SHA.
A ref move or successful image build alone is insufficient.

On failure, identify the failed stage and preserve the current data. Apply a fix
through `dev` and `main`, or use `deploy/rollback.sh` only after reviewing the
previous application/schema compatibility. Rollback does not restore a database
or undo later user writes. See [database migration](database-migration.md).
