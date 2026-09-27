---
description: "SPEC-092: Fixed corporate reports and scoped current/history device heartbeat views."
last_verified: "2026-09-25"
---

# SPEC-092: Fixed corporate reports

## Purpose

Give leads and superadmins a familiar table for seeing which employee devices report now and how regularly they reported during a selected period.

## Scope

The Corporate Hub has `/corporate/reports`, separate from the complaint `/reports` route and the Dashboard builder. Device Heartbeat is the first working fixed report. Usage, Team Coverage, and Provider Health have only catalog placeholders. SPEC-087 owns authenticated heartbeat writes and current health; SPEC-089 owns retention, erasure, and audit.

## Terms

- `Current` — read-time installation state from the latest accepted signal and current tenant policy.
- `History bucket` — one fixed-width portion of a selected period with expected and received signal counts.
- `Coverage` — received expected signals divided by expected signals during observed reporting intervals.

## Requirements

- `REQ-9201`: The Organization secondary navigation shows Projects, Teams, Employees, Technologies, Reports. Installations and Usage no longer appear there. Their former URLs redirect to their fixed-report destinations. The existing complaint route is unchanged.
- `REQ-9202`: The Reports index has four equal-layout HTML/CSS preview cards for Device Heartbeat, Usage, Team Coverage, and Provider Health. Only Device Heartbeat provides a full report. The other pages state that details will be added later.
- `REQ-9203`: Device Heartbeat has a Current and History view inside one route. Team, employee, and status filters, URL state, sorting, and pagination share the same structure. History adds a 24-hour, 7-day, 30-day, or bounded custom date period. The table links employee and team names and shows stored device labels rather than technical identifiers.
- `REQ-9204`: Current uses the canonical latest heartbeat and the current tenant policy. Unknown devices remain visible before their first signal. The fixed report groups canonical `partial` health into its `failing` attention category without changing the canonical state or dashboard source.
- `REQ-9205`: History is built from accepted signal records, not only the latest-state row. Each row has fixed-count time buckets, expected/received counts, status, and coverage. Expected counts follow effective tenant policy revisions. Time before first observed enrollment, observed disabled intervals, and tenant-disabled intervals do not count as missing. Local offline opt-out is not observable by the server under REQ-8715, so the report cannot retrospectively identify its exact time.
- `REQ-9206`: The server checks active membership and role before report access. A superadmin with `telemetry.read` sees the organization. A lead sees only readable teams and members authorized for `telemetry.read`. Filter options come from the same scoped result. Direct URL manipulation cannot reveal foreign subjects. Privileged report reads append a telemetry access audit.
- `REQ-9207`: The report bounds its history to 31 days, its page size to 50, and each history query to 100,000 raw signals. It shows a table empty state, route loading skeleton, and in-page error state. EN and RU provide equivalent labels. Timeline segments are keyboard focusable and expose counts as text.

## States and errors

Current shows active, stale, failing, disabled, and unknown. History buckets show healthy, partial, missing, and not expected. Invalid periods and excessive source rows reject with typed validation errors; unauthorized scope rejects without data. A device with no accepted signal remains visible as unknown and has no measured history.

## Security and privacy

The API computes visible subjects before fetching device rows or returning filter options. It audits each privileged report read. Stored history uses only bounded heartbeat facts, follows raw retention, and is physically erased for device or account subject rights. Device labels appear only in the authorized report, never in public metadata.

## Compatibility and migration

Migration 0096 adds persistent device labels, accepted heartbeat history, and effective policy revisions with tenant row-level security. Existing heartbeat rows stay readable. The historical report begins collecting signals after this migration; older intervals are not presented as measured history. Rollback of the report UI uses the previous routes, while database rollback requires preserving or deliberately discarding the new historical data.

## Acceptance criteria

| Requirement | Executable oracle |
| --- | --- |
| `REQ-9201` | Corporate navigation test and route tests check new links and legacy redirects. |
| `REQ-9202` | Reports index component and browser checks verify four previews and placeholder pages. |
| `REQ-9203` | Browser flow selects a team, switches to History, and changes period; component tests cover URL sorting and pagination. |
| `REQ-9204` | API tests cover current state and a device without heartbeat. |
| `REQ-9205` | Bucket unit and API tests cover policy changes, duplicates, disabled intervals, and coverage. |
| `REQ-9206` | API tests reject a non-lead, foreign team, and foreign employee query. |
| `REQ-9207` | Contract, i18n, accessibility, and web checks cover bounds and UI states. |
