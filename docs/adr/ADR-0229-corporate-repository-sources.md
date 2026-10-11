---
description: "Bind a corporate project repository without manufacturing a local CLI identity."
last_verified: "2026-10-08"
---

# ADR-0229: Corporate repository sources

Status: accepted.

## Context

Project source selection in the web account must work without a CLI checkout or a
device session. CLI project links remain device-bound synchronization records.

## Decision

Keep CLI links unchanged. Store an explicit corporate repository binding separately,
scoped to the organization and project, with actor and exact plan digest. Project
reads and scans use a union of source bindings and CLI links. A project with a
source cannot bind another one. Creating a source does not create a CLI identity,
modify repository access, or queue scanning.

Resolve public GitHub metadata anonymously through the fixed GitHub API. GitLab
uses only the organization's configured host and credential. Preview stores an
expiring, actor-bound digest in the existing mutation ledger. Confirmation checks
the digest, authorization, project revision and live repository metadata under the
organization mutation lock. Both steps have durable idempotency receipts. GitHub
scans of public bindings recheck public visibility and immutable repository ID;
existing installation-authorized scanning retains its authorization boundary.

## Consequences

The project identity rail displays provider, repository URL and branch and exposes
an explicit check/confirm form to project editors. Read-only viewers see the source.
Private GitHub selection requires a separate connector-aware flow. No fake device
or local checkout is created. Rollback removes the new binding table only after
preserving any owner-created bindings; image rollback alone does not erase them.
