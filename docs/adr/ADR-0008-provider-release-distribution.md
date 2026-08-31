---
description: "Decision to distribute providers as release artifacts."
last_verified: "2026-08-03"
---

# ADR-0008: Distribute providers as release artifacts

Accepted on 2026-08-03.

## Context

A Git submodule is convenient for development, but requires a checkout, mixes application and provider lifecycles, and does not give the user a separate verifiable update or version rollback.

## Decision

Public providers are distributed as versioned artifacts with a source repository/commit, contract version, size, SHA-256, and a signature or attestation. The CLI installs a new version alongside the old one and atomically switches the pointer after verification.

## Consequences

Updating a provider does not automatically change the target. Release manifests, anti-rollback state, separate source-to-artifact verification, and a path to return to the previous version are required.
