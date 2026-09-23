---
description: "Corporate dashboard query, CI check, and saved-view HTTP contracts."
last_verified: "2026-09-23"
---

# Corporate dashboard contracts

All routes are under `/v1/corporate/organizations/{organization_id}/dashboard`.
`PUT /ci-check` accepts one session-bound, closed CI verdict. `POST /query`
accepts `{ "query": DashboardQuery }` and returns bounded cells with dimension
strings and integer measures. `GET /views`, `POST /views`, and
`PUT /views/{view_id}` list, create, and revision-update stored query definitions.
The exact field shapes are generated in `schemas/v1` and OpenAPI.
The CLI sends this verdict after an online `corporate assignment verify` with
an explicit corporate project and the signed-in account. It sends only the
closed status and reason, project/account/device/harness, optional setup ID,
and check time. Local diagnostics, paths, and source content stay on the device.
Offline, unscoped, and other-account verification does not write a CI check.

The datasets are `ci`, `heartbeat`, and `provider`. A fresh heartbeat may report
`partial` for an installation requiring recovery; stale reporting is still
evaluated from server receipt time. Dimensions are scoped per dataset; `provider`
is available only for provider health. Measures are count,
distinct devices, and (for CI only) distinct projects. A query can select up to
eight dimensions and at most eight distinct dimensions across display, grouping,
and pivots. Filters accept exact, bounded tokens. Line requires day, pie one
dimension, and heatmap two. The server rejects more than 1,000 source rows,
cost above 5,000, and emits at most 200 groups.

`reason` is a closed diagnostic code, available only to callers with
`audit.read`. Each query is audited. Saved-view access is checked on every read
and execution; its scope does not grant data rights. The API has no free-form
SQL, repository content, secret, path, or export field.
