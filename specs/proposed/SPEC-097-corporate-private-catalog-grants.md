---
description: "Proposed corporate presentation of existing private major-line grants without conflating assignments."
last_verified: "2026-09-29"
---

# SPEC-097: Corporate private catalog grants (proposal)

Status: proposed; existing AccessGrant and catalog assignment contracts apply.

## Goal

An authorized issuer can give an employee precisely scoped access to a private
setup/component major line and explain the grant separately from distribution.

## Requirements and oracles

| ID | Target behavior | Executable oracle |
| --- | --- | --- |
| `REQ-9701` | Corporate assignments and operational ownership do not confer private read/use or upstream edit. | Assigned/owner-without-grant negative API and delivery tests. |
| `REQ-9702` | Corporate issuance uses existing AccessGrant major-line semantics and verifies the issuer's current authority in the owning context. | Personal/corporate owner, foreign object and forged issuer matrix. |
| `REQ-9703` | UI identifies the major line, current included versions, recipient and source; it does not promise future majors or install-only separation without enforcement. | Contract/UI wording and version-boundary tests. |
| `REQ-9704` | Current grants are checked for card, manifest, artifact and every closed dependency; revocation stops later deliveries. | Revoked grant and dependency-closure delivery tests. |
| `REQ-9705` | Grant/create/revoke and denial audit excludes tokens and private artifact bodies, and old personal grants remain valid. | Audit redaction, regression and tenant-isolation tests. |

## States and migration

The control is absent until the corresponding API contract and tests ship.
Failed issuance leaves no grant. Rollback keeps existing grants and audit;
local copies already obtained are not remotely revoked.
