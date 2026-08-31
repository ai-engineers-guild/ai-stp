---
description: "Decision to synchronize through a revision graph."
last_verified: "2026-08-03"
---

# ADR-0005: Synchronize through a revision graph

Accepted on 2026-08-03.

## Context

The same passports and drafts may be changed independently on multiple devices. A simple last-write rule can silently lose confirmed data.

## Decision

Local and cloud state uses content-addressed revisions, parent links, fast-forwarding of non-divergent history, three-way field-level merges, explicit conflicts, and deletion markers. A silent "last write wins" rule is prohibited.

## Consequences

Local and server entity heads, an outgoing and incoming event log, a common ancestor, idempotency, an explicit conflict model, and concurrent-change tests are required.
