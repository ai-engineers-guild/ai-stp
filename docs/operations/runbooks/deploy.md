---
description: "Exact-source deployment, settlement and verification."
last_verified: "2026-11-08"
---

# Deployment

GitHub Actions prepares and deploys qualified source through `.github/workflows/deploy.yml`.
The production timer runs `deploy/pull-deploy.sh`. Use the current scripts and
Compose configuration under `deploy/` for activation and recovery.

## Prerequisites

The production host uses Docker Engine/Compose, Git, rsync, curl and flock. Actual
`.env.prod` and deployment environment files stay on the host, outside source
synchronization. `.env.prod.example` lists the required names. Validate through
`just infra-env-check` before effects, including `AI_STP_SESSION_SECRET`,
`AI_STP_CATALOG_CURSOR_SIGNING_SECRET`, database/storage and content-import settings.
Never print their values. Do not create backups or snapshots unless requested.

GitHub repository variables `AI_STP_PUBLIC_ORIGIN` and `AI_STP_DOCS_ORIGIN` select
the public application and documentation origins verified after deployment.
They must be configured; a missing docs origin is not a successful skipped check.

## Promotion and activation

A successful push-triggered `check` on current `dev` provides the exact qualified
source. Run `just delivery-prepare SOURCE_RUN_ID` and observe its completed
preparation before promotion. Delivery verifies its published native CLI download and registers the
three unchanged, accepted CodeQL payloads for Main. It reads the candidate's
literal CLI link without executing candidate code and refuses absent, draft,
incomplete or unrelated releases.

From the qualified checkout, the existing Main administrator runs
`just delivery-promote SOURCE_SHA SOURCE_RUN_ID SOURCE_ATTEMPT`. This repeats
source and policy admission, requires processed Main analysis, fast-forwards
Main without force and dispatches CI. Hosted delivery never writes Main or
switches credentials after a refusal. Once Main equals the source, CI advances
`deploy/prod`, verifies public rollout and publishes any new Desktop version
from the qualified installers. See [Git workflow](../../engineering/git-workflow.md).

For interrupted publication, complete the original release and dispatch `deploy`
on Dev with the same successful `source_run_id`. Do not rebuild or rerun full
qualification merely to release a completed publication hold. Repeating the
operator command reuses an already advanced Main and dispatches reconciliation.
The production host is not a CI runner;
its timer fetches the public repository anonymously and initiates deployment.
No production SSH credentials are stored in Actions.

The host locks deployment, validates its environment, transfers the exact source,
builds images, migrates/initializes dependencies and starts services before health
checks. Source transfer preserves host-owned environment, state, volumes and runtime
files. Never use a broad deletion or Docker prune against a shared host.
The pull deployer retires only its own extracted source trees, retaining current
and previous releases. Docker containers, images, networks and build cache belong
to the host and its own cleanup; this project does not collect them.

`.deploy-state/in-progress` identifies an unfinished operation and stage.
`.deploy-state/current` records the last settled release. Inspect these markers and
service logs after interruption; resume the original operation through the owning
deploy script. A public health response may precede settlement of the host marker.

## Verification and recovery

Verify all three: the successful exact-SHA workflow, `/v1/system/version` matching
the promoted commit, and the settled host marker without an in-progress operation.
Check the application and both documentation locales (`/` and `/en/`).
For docs image changes, inspect the running nginx process and confirm it runs
as the configured unprivileged user. Match serving source to the promoted SHA.

On failure, identify the failed stage and preserve the current data. Apply a fix
through `dev` and `main`, or use `deploy/rollback.sh` only after reviewing the
previous application/schema compatibility. Rollback does not restore a database
or undo later user writes. See [database migration](database-migration.md).
