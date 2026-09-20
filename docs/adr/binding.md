---
description: "Which accepted ADRs still constrain non-corporate work; default is binding."
last_verified: "2026-09-20"
---

# Binding ADRs

Owner: `ADR-0194`. This page is the reading list, not a second decision log.
The records themselves stay in this directory and are not rewritten.

## Default

Every accepted ADR in this directory is **binding** until this page lists it
under Historical. Unclassified is binding, not optional.

## Out of scope of the implementation-canon program

Corporate ADRs from ADR-0176 onward, and any ADR whose sole subject is the
colleague B2B zone, remain binding for that zone. The implementation-canon
program does not mark them historical and does not move their specs or tests.

## Historical

None yet. A later classification PR adds a row here only when
`docs/engineering/implementation-canon.md` records the ADR as historical and
the matching spec, if any, is in `specs/archive/` or was folded into a
rewritten active spec.

## Still-binding examples for the non-corporate line

These are not an exclusive list. They are the ADRs a non-corporate change
must not silently undo:

| ADR | Why it stays binding |
| --- | --- |
| [ADR-0001](ADR-0001-record-architecture-decisions.md) | When the source of truth or a hard-to-reverse rule changes, write a new ADR |
| [ADR-0147](ADR-0147-the-test-gate-does-not-fail-on-a-coverage-percentage.md) | Coverage percentage does not fail the gate |
| [ADR-0150](ADR-0150-full-task-authority-does-not-reprompt.md) | Task authority and staged replacement |
| [ADR-0180](ADR-0180-permanent-dev-and-protected-main.md) | `dev` integration, `main` promotion |
| [ADR-0181](ADR-0181-application-services-own-cli-effects.md) | Application services own CLI effects |
| [ADR-0109](ADR-0109-the-deployment-source-is-the-public-repository.md) | Public repository is the deploy source |
| [ADR-0135](ADR-0135-nginx-is-the-only-edge-proxy.md) | Host nginx is the public edge |
