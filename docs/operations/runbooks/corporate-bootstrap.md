---
description: "Create the one initial corporate organization and superadmin safely."
last_verified: "2026-09-12"
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
downgrade migrations `0063` or `0064` after corporate data exists: retaining tenant and audit rows
is safer than converting or deleting them.

Corporate audit rows are append-only and retained indefinitely in B2B-01. The bounded
audit export is tenant-filtered, permissioned, redacted, and itself audited; there is
no purge route. Database backup/restore remains the operational recovery path. A future
retention policy must version its duration and migration under SPEC-013 before any
deletion job is enabled.

B2B-01 does not make search indexes (#212), application caches and non-audit product
exports (#247), private/runtime telemetry (#52, #218, #219), GitLab integration
(#18, #213), or feature-specific technology/background handlers
(#207, #208, #222, #215, #230) corporate-aware. Each owning follow-up issue must
add its tenant partitioning, denial/replay audit, redaction, retention/export, and
hostile cross-tenant runbook steps before enabling that feature for corporate
tenants.

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

## Teams and leads

Create or rename teams through the corporate team routes and assign staff or leads
through `membership-assignments` with a team identifier. A member may belong to and
lead multiple teams. Reassigning `team_role` replaces that member's scoped binding;
`operation: remove` removes membership and revokes the team's bindings. Mutations
require current authorization revision and a unique idempotency key; retry the same
request with its original key, and refresh context after a successful change.

Team details show the authorized roster and current leads. Staff see themselves and
active leads; leads see only the rosters of teams they lead. Archive a team instead
of deleting it to retain historical references. Archive disables its scoped grants
and blocks new assignments; superadmins can remove old assignments or restore the
team. Restore enables retained grants only for active principals. If every lead is
removed or suspended, a superadmin appoints a replacement; staff receive no automatic
privileges. Roll back an unintended archive by restoring the team's state using its
current revisions.
