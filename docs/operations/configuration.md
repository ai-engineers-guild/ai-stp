---
description: "Server configuration owners and separation from CLI settings."
last_verified: "2026-10-15"
---

# Server configuration

`.env.dev.example` and `.env.prod.example` own supported environment variable names.
`deploy/lib.sh` validates required production values before effects; `just
infra-env-check` runs that check without starting containers. Real environment files
belong to the host, are ignored by Git and must be excluded from source cleanup.

The deployment supplies database, queue, object storage, session and catalog-cursor
signing secrets, OAuth and content-import credentials. Empty optional provider
configuration disables that provider. Change access or authentication settings only
within the task's authorization. Never copy real values into documentation or logs.

`deploy/compose.prod.yml` and the selected deployment overlay own service topology and
ports. The [deployment runbook](runbooks/deploy.md) describes applying and verifying
changes. CLI network configuration is separate; see
[CLI configuration](../contracts/cli-config.md).
