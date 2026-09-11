---
description: "Create the one initial corporate organization and superadmin safely."
last_verified: "2026-09-11"
---

# Corporate bootstrap

Set `AI_STP_CORPORATE_BOOTSTRAP_SECRET` to a high-entropy deployment secret, restart
the API, and call `POST /v1/corporate/bootstrap` once with the same value in
`X-AI-STP-Bootstrap-Secret`. The body names the existing account that becomes the
first `superadmin` and supplies an idempotency key. Store neither value in source
control or logs.

Retry the identical body and idempotency key after an uncertain response. The server
returns the original organization. A different bootstrap request is rejected after
the first organization exists. Remove the bootstrap secret from runtime configuration
after a successful read of the new organization's corporate context.

Rollback disables the corporate routes before reverting application code. Do not
downgrade migration `0063` after corporate data exists: retaining tenant and audit rows
is safer than converting or deleting them.

Corporate audit rows are append-only and retained indefinitely in B2B-01. There is no
product export or purge route in this milestone; database backup/restore is the only
operational export. A future retention policy must version its duration and migration
under SPEC-013 before any deletion job is enabled.

## Tenant execution context

Corporate database work runs with transaction-local `ai_stp.organization_id` and is
protected by FORCE RLS. Bootstrap, verified-identity lookup, and queue claiming may use
the internal `*` scope only while locating the tenant; handlers switch to the persisted
tenant before reading protected rows. Application database roles must not be granted
`BYPASSRLS` or PostgreSQL superuser privileges.

Tenant-bound jobs store the organization, principal, required permission, scope, and
authorization revision in their persisted envelope. A worker reruns the shared
evaluator and rejects a mismatched envelope, suspended principal, revoked binding, or
revision made stale by a later policy change. Corporate private objects use
`objects/organizations/{organization_id}/...`; account-scoped or global keys are not
valid substitutes.
