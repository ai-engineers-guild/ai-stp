---
description: "Keep only main and dev branches while retaining the verified deployment pointer."
last_verified: "2026-09-15"
---

# ADR-0191: Deployment pointer is a tag

## Status

Accepted.

## Context

The owner requires only permanent `main` and `dev` branches. Production still
needs a pointer to the exact commit verified by a successful main push check.

## Decision

Use lightweight `refs/tags/deploy/prod` instead of `refs/heads/deploy/prod`.
This changes the ref namespace in ADR-0103 and ADR-0109, not their deployment
authorization or anti-rollback rules. The promotion workflow keeps non-forced
updates and the host keeps its ancestor check.

During migration, seed the tag at the old deployment SHA. Retain the old branch
until the new pull script has deployed, then delete it. Hosts with an explicit
`AI_STP_PULL_REF` override must change it to the tag before branch removal.

## Consequences

Only `main` and `dev` remain branches. Release tags and the deployment pointer
remain available. Rollback of this namespace change restores the branch at the
tag SHA and the previous script; application rollback remains governed by the
deployment runbook.
