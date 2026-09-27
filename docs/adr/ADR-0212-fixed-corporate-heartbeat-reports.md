---
description: "Corporate Reports presents fixed reports and retains accepted installation heartbeats for a bounded history."
last_verified: "2026-09-25"
---

# ADR-0212: Fixed corporate heartbeat reports

Status: accepted. Related decisions: ADR-0205, ADR-0208, and ADR-0211. Implemented behavior is recorded in SPEC-087, SPEC-089, and SPEC-092.

## Context

The Organization navigation exposes raw Installations and Usage pages. The installation page lists account and device identifiers instead of employees and teams. The existing heartbeat row is a latest-state snapshot, so it cannot prove how often the device reported during a selected period. The existing `/reports` route serves user complaints and must stay separate.

## Decision

Organization gets `/corporate/reports`, a catalog of fixed reports. Device Heartbeat is its first implemented report, with Current and History views in one page and shared filters and table structure. Usage, Team Coverage, and Provider Health remain catalog placeholders. Legacy Corporate Installations and Usage URLs redirect to their report destinations. The complaint route is unchanged.

Each strictly newer authenticated heartbeat updates the existing current row and appends one accepted-signal record in the same transaction. Equal or older writes leave both unchanged. The accepted-signal record contains only account and device references, receipt time, reported state, and the organization policy interval/version at receipt. Organization policy changes append an effective policy revision with enablement, cadence, and stale threshold. The history report uses these effective revisions for expected-signal counts and fixed-width time buckets. No raw payload, prompt, path, or credential enters history.

The report endpoint applies corporate authorization before it returns device rows, employees, teams, and filter options. Superadmins can see the organization. Leads can see only members within teams they can read and for whom `telemetry.read` is granted. The report maps a partial installation state to the report's `failing` attention category; the canonical heartbeat state remains `partial`. Device labels saved at registration are shown instead of technical identifiers, with a generic label for older devices.

Periods before the first accepted signal, periods when tenant policy disabled reporting, and observed disabled or revoked intervals are not counted as missed signals. Local CLI opt-out is offline and sends no server event under REQ-8715; until the server can observe that choice, silence after the last active signal remains indistinguishable from a failed sender and is treated as missing. The report must not claim to know the exact time of an unobserved local opt-out.

## Consequences

Accepted history grows with signal frequency and obeys the tenant raw-retention period and subject erasure. Reads are bounded by period, page size, and source-row cap. Exact historical coverage begins only after this migration; it cannot be reconstructed from older latest-state rows. The report is a fixed operational table, not a query builder or an additional dashboard.
