---
description: "One account identity owns corporate employee and public publisher projections."
last_verified: "2026-09-18"
---

# ADR-0192: One account identity in corporate UI

Status: accepted.

## Context

The Web currently presents corporate members, employees, and public publishers through
separate routes and partially separate detail layouts even though they refer to one
account plus context-specific relations. This duplicates navigation and permits the
same person to show inconsistent profile, role, team, and catalog information.

## Options

1. Retain separate member and publisher UI identities and synchronize their fields.
2. Introduce a new employee identity beside account and membership.
3. Keep account as the identity, membership as the tenant relation, and employee and
   publisher as context-specific projections.

## Decision

Choose option 3. Account is the stable person identity. Corporate membership stores
tenant role, job title, lifecycle, presentation, and organization relations. Publisher
is a public catalog projection of the same account. The canonical corporate routes are
`/corporate/employees` and `/corporate/employees/{account_id}` and use one shared
two-column account detail composition.

Legacy `/corporate/members` routes redirect permanently with safe query preservation.
Corporate links that identify a publisher account resolve to the employee detail when
that account is readable in the active organization. Public publisher routes remain
unchanged and do not expose corporate membership data.

## Consequences

Contracts continue to use membership where tenant participation is meant and account
where identity is meant. No data is copied into a new employee identity table. Route,
navigation, machine-projection, canonical-link, and browser tests must cover both
contexts and prevent private corporate data from entering public publisher responses.
Application rollback may restore legacy handlers without reversing stored data.

## Revisit conditions

Revisit only if one employee must represent a person without an account, or one account
must hold multiple independently addressable employee identities in the same
organization.
