---
description: "Wire semantics of public detail-view and artifact-download counters."
last_verified: "2026-08-17"
---

# Catalog usage metrics

When the feature is enabled, public component card/detail/version responses gain
nullable `usage_metrics` with non-negative `detail_views_count` and
`artifact_downloads_count`. All surfaces read the aggregate by `stable_id`;
absence means the feature is disabled or the value is unavailable, not zero.

A detail view is a successful public response. An artifact download is a
successful delivery of bytes after access and integrity checks. HEAD, preflight,
an error, an incomplete stream, and obtaining a download URL do not count. A
download is not an installation success.

The dedup key is built from the action, `stable_id`, window, and a keyed digest of
a minimal network signal. Raw IP, user-agent, account/device ID, and cross-window
digest are not stored. The window, retention period, and secret rotation are set
by server configuration; the public API does not return events or a unique-user
estimate.

The default anti-abuse window is `1 h`, dedup-row retention is `25 h`, and the
secret rotates every `24 h` with overlap for the current window. Bounded server
configuration values are: window `5 min..24 h`, retention no shorter than the
window and no longer than `7 d`, and rotation no less frequent than the retention
period. Changing defaults requires a privacy review and boundary tests.

## Operations

The API enables collection through `AI_STP_CATALOG_USAGE_ENABLED`; Web displays
the aggregate only when the build-time feature
`AI_STP_FEATURE_CATALOG_USAGE_METRICS` is also enabled. API parameters:

- `AI_STP_CATALOG_USAGE_SECRET` — required keyed-digest secret when enabled;
- `AI_STP_CATALOG_USAGE_WINDOW_SECONDS` — dedup window;
- `AI_STP_CATALOG_USAGE_RETENTION_SECONDS` — dedup-row retention period;
- `AI_STP_CATALOG_USAGE_SECRET_ROTATION_SECONDS` — rotation period.

The secret rotates with active-window overlap: the previous value is retained
until the window expires, then removed. Cleanup removes only dedup rows older than
the retention period; the aggregate does not decrease. The API does not start
with invalid configuration. For rollback, disable the Web feature first, then
`AI_STP_CATALOG_USAGE_ENABLED`; the public projection becomes nullable/absent,
and accumulated aggregates are not deleted.
