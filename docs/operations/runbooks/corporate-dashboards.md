---
description: "Operate and troubleshoot Corporate Hub health dashboards."
last_verified: "2026-09-22"
---

# Corporate dashboards

Run migration 0092 before deploying the dashboard API and web route. A lead
needs current team/member telemetry rights and project read rights for CI;
superadmin needs organization `telemetry.read`. Diagnostic reasons additionally
require `audit.read`.

Open Corporate Hub → Dashboard, choose a dataset and view, then run the query.
Saved views retain query definitions only. If a formerly visible view returns
access denied, inspect current team, member, project, and audit permissions;
do not copy saved results or bypass the query endpoint. Empty means no matching
current records. Stale installation/provider health uses server receipt time;
check the CLI heartbeat or governed provider ingest when reports stop arriving.
Source row or query cost errors require narrower filters or scope. CI checks
coalesce by project/device/harness, so only the latest verdict is retained.

On API rollback, disable the dashboard routes and web page while retaining
tables and audit. If a database downgrade is required, back up CI checks and
saved views before dropping migration 0092.
