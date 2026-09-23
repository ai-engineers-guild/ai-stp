---
description: "Corporate dashboards query canonical operational health through a constrained contract."
last_verified: "2026-09-22"
---

# ADR-0207: Corporate dashboards query canonical health

Status: accepted.

## Context

Managed verification, installation heartbeats, and governed provider telemetry
already have distinct state owners. A dashboard needs aggregation without
creating another writable health truth or granting access through saved queries.

## Decision

Store only the latest closed managed CI verdict per tenant, project, device, and
harness. Project/device/account identity is bound to the authenticated write.
Read installation health through its read-time projection and provider health
from the latest governed provider heartbeat; do not copy their state into the
dashboard tables. Queries accept allowlisted fields and equality filters with
source-row, query-cost, and result limits. A lead's team/member/project rights
are checked before aggregation; superadmin reads use organization scope.
Diagnostic reasons require `audit.read`. Reads append privileged-access audit.

Saved views store validated query definitions, not query results. Their scope
is immutable, and each execution rechecks current permissions. User, team, and
organization scopes are distinct; a stored definition never confers access.

## Consequences

Heartbeat staleness changes as time passes without a writer job. A revoked
membership loses dashboard data immediately. The latest CI table does not
provide a historical CI time series; a line chart groups the currently retained
checks by check day. Large queries reject instead of silently truncating source
rows. Maintenance and remediation remain separate operations.
