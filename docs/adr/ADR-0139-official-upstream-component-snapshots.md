---
description: "Decision to publish attributed snapshots of selected public upstream components from the AI STP Official account."
last_verified: "2026-09-01"
---

# ADR-0139: Official upstream component snapshots

Status: accepted.

## Context

ADR-0034 deliberately limited the launch catalog to first-party work and declined
to package third-party open-source components on their authors' behalf. The
catalog now needs a narrow curated path for useful public GitHub components whose
maintainers have not published them in AI STP. These objects must remain
reproducible, pass the ordinary publication barrier, attribute upstream authors
without implying affiliation, and be transferable when an upstream maintainer
claims them.

## Options

1. Keep waiting for upstream authors to publish. This preserves the old boundary
   but leaves common components absent.
2. Copy selected repositories directly into catalog tables. This is simple but
   bypasses provenance, validation, immutability, and audit.
3. Treat AI STP Official as the publisher of an exact attributed snapshot and
   pass it through the existing publication pipeline.

## Decision

Option 3 is accepted as a narrow exception to ADR-0034.

A reviewed allowlist names a public GitHub repository, tracked ref, component
subpath and type, reviewed description, and AI STP Official owner. A scheduled
sync resolves the ref to a full commit, downloads exact bytes, records their
digest and upstream identity, and uses the existing plan, bind, validate, and
publish path. It never writes a published version directly. ADR-0153 supersedes
the storage and delivery part of this decision by making that allowlist a Git
manifest reconciled through a durable outbox and ledger.

The catalog owner is the publisher of the AI STP snapshot, not a claim to have
authored the upstream project. Every version description starts with upstream
project, repository, license, and maintainer attribution and ends with the
ownership-claim instructions. `author_verified` continues to describe the
verified AI STP publisher account; `component_verified` continues to describe
only accepted evidence for the exact bytes. Neither axis proves upstream
affiliation.

Official synchronization consumes the shared `SourceIntent`/`SourceSnapshot`
resolver for multiple GitHub and package source rows. SPEC-057 owns explicit
ownership requests; ADR-0153 owns the atomic database transfer and source fence.
No public source-management endpoint, automatic claim approval, catalog
replacement, or identity merge is added.

## Consequences

- SPEC-056 owns source configuration, synchronization, attribution, and
  idempotency.
- The closed worker job registry gains one job type; scheduling reuses the
  PostgreSQL queue.
- A failed fetch or validation leaves the current published version untouched.
- Removing or disabling a source stops future syncs and does not delete history.
- Rollback disables the source and scheduler; existing immutable versions remain
  readable under normal lifecycle rules.

## Revisit conditions

Revisit when a second source host or package registry is required, an upstream
namespace can be verified mechanically, or maintainers request enough transfers
to justify a public claim workflow.
