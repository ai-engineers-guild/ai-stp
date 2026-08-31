---
description: "Safe public projection of harness support evidence in the catalog."
last_verified: "2026-08-09"
---

# Catalog support evidence

Exact fields and enums belong to the `packages/contracts` models and generated
schemas. This document defines the meaning of the public projection under
`SPEC-033` and `ADR-0072`.

`support.tier` shows the product support tier of a harness: `primary` or `beta`.
`support.state` shows the state of required evidence: `verified`, `stale`,
`missing`, or `not_verified`. These axes are not
`trust_lane`, `author_verified`, or `component_verified`.

The public evidence record contains only a safe check summary: `check_id`, result,
source, provider and version identifiers, the exact release reference (commit or
digest), operating system, architecture, whether the check is required, and
timestamps. Raw reports, signature, storage key, credentials, private URL, and
object bytes are not published. `policy_version` preserves the version of the
applied support policy.

The server calculates the state from stored timestamps and its current time.
Web does not recalculate freshness. A complete fresh set of required `passed`
checks yields `verified`; an expired set yields `stale`; an absent required
record yields `missing`; failed, corrupted, or contradictory evidence yields
`not_verified` and does not change the trust axes.

Rows without evidence remain `missing`, so adding the projection is additive
and does not rewrite historical publications. The `support_tier` and
`support_state` filters are accepted on public catalog routes and do not change
consent to the `experimental` lane.
