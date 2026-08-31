---
description: "Runbook: report case triage."
last_verified: "2026-08-04"
---

# Report triage

Guild owners perform triage. There is no public SLA: cases are reviewed within a reasonable time, with priority given to cases showing signs of a vulnerability.

1. Open the case in the `submitted` state and check duplicate grouping.
2. Compare the object, version, and hash from the report with the registry; close a nonexistent version as `dismissed`.
3. Classify the case as an operation failure, incompatibility, harmful behavior, or suspected vulnerability.
4. Immediately move a suspected vulnerability to `security_escalated` and continue with the security incident runbook.
5. For the other classes, compare check snapshots and the typed error code with observability data.
6. If necessary, send the author a sanitized notification and move the case to `awaiting_author`.
7. Make any decision to hide or block a version through a separate auditable action under `SPEC-005` and `SPEC-007`; the number of reports is not grounds for doing so.
8. Close the case as `resolved` or `dismissed`, recording the outcome.
