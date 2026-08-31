---
description: "Decision to use PostgreSQL and RustFS."
last_verified: "2026-08-03"
---

# ADR-0009: Use PostgreSQL and RustFS

Accepted on 2026-08-03.

## Context

The server needs transactional relationships among accounts, versions, revisions, grants, verification results, and audits, plus separate storage for large immutable artifacts.

## Decision

PostgreSQL stores server metadata, revisions, access rights, verification results, and audit records. RustFS with an S3-compatible interface stores immutable artifact bytes. FastAPI and the worker form a modular monolith, while Next.js remains a thin web interface.

## Consequences

PostgreSQL migrations, a transactional outbox, verifiable backups, object-level authorization, and coordinated deletion of metadata/object bytes are required.
