---
description: "Decision to add private report cases from web and CLI with auditable moderation and no automatic public issues."
last_verified: "2026-09-04"
---

# ADR-0031: Private report cases and moderation

Status: accepted.

## Context

The product deliberately excluded social mechanisms: ratings, feeds, and public discussions. This also excluded a minimal operational channel—the user's ability to tell the platform about a broken or malicious published object. Blocking a version remained possible only through the owners' own findings or the private vulnerability process.

In practice, a user encountering incorrect compatibility, a reproducible failure, or harmful behavior either stays silent or moves details into public channels where they do not belong. Platform operators receive no structured machine evidence, and moderation cannot correlate reports with exact versions and operations.

Rejecting social mechanisms was correct; treating the operational reporting channel as one of them was the mistake.

## Options

1. Keep the status quo: only owners' own findings and private vulnerability reports. Zero surface, but the platform is blind to real failures.
2. Create public GitHub issues from the product. Transparent, but exposes the reporter's environment, provides uncontrolled privacy, and turns reporting into a social mechanism.
3. Use one private `ReportCase` from web and CLI, with mechanically assembled contents, preview, moderator triage, and vulnerability escalation into the private process.

## Decision

Option 3 is accepted.

**One private case, two entry points.** The web report action and CLI report command create one internal private `ReportCase` through the shared application scenario. A report does not automatically create a public GitHub issue.

**Report contents are mechanical and private.** The CLI collects only: exact object, version, and hash; harness and its version; provider version; operation identifier and stage; validation snapshot identifiers; typed error code; and optional constrained sanitized diagnostics—only after explicit review and consent. Source code, prompts, `.env` contents, secret values, private object bytes, and full home paths are not sent automatically. The reporter sees a complete preview before submission.

**The case lifecycle is a closed enumeration.**

```text
submitted → triaged → awaiting_author → resolved | dismissed
                    ↘ security_escalated
```

Platform moderators perform triage. After triage, the object author receives a sanitized notification when needed. A case showing signs of a vulnerability is escalated to the private process under `SECURITY.md`.

**Report count blocks nothing by itself.** Repeated reports may be grouped, but report count never hides or blocks an object automatically. Hiding, blocking, and restoration remain explicit auditable moderator actions with actor, reason, and time.

**Abuse is constrained mechanically.** Submission requires an account, is rate-limited and idempotent; duplicates are grouped rather than multiplying the signal.

**The same case table accepts catalog proposals.** `topic` distinguishes object
reports, service proposals, and country proposals. Topic-specific data stays in
the existing bounded JSON payload. Object coordinates are present only for an
object report. This reuses moderation and audit controls instead of creating a
parallel request queue.

## Consequences

- the machine boundary for a case belongs to `docs/contracts/report-case.md`, and requirements belong to `SPEC-016`;
- `SPEC-007` stops excluding a user reporting channel: blocking remains an auditable owner action, while reports create cases and do not automatically change a version lifecycle;
- MVP and web boundaries receive reporting as a mandatory feature;
- API routes, CLI machine help, and data policy receive reporting requirements;
- operations receives a report-triage runbook and observability signals.

## Reconsideration conditions

This decision will be reconsidered if private cases are systematically used to suppress competing authors—in that event idempotency, grouping, and auditing will be tightened—or if report volume requires automatic prioritization, which still will not become automatic blocking.
