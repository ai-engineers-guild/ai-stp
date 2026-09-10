---
description: "Local, remote, and provider project identities remain distinct and are linked only by an explicit revisioned binding."
last_verified: "2026-09-09"
---

# ADR-0178: Project identities link explicitly

Status: proposed.

## Context

The local project passport and index are usable offline and currently remain
local by default. Corporate Hub introduces organization-owned remote projects,
while GitHub and GitLab provide their own repository identities. Names, paths,
and repository URLs can change or collide. Treating any of them as a universal
project key could silently merge unrelated projects or duplicate one project
after a move or rename.

Existing synchronization already uses content-addressed revisions, explicit
conflicts, idempotent receipts, and no last-write-wins merge. Project linking
must preserve those properties without making a local project dependent on the
server.

## Options

1. Match projects automatically by name, path, or clone URL. This is convenient
   but ambiguous and unsafe across devices, organizations, forks, and renames.
2. Replace the local identifier with the first server or forge identifier. This
   breaks offline identity and makes unlinking or provider migration destructive.
3. Keep local, remote, and provider identities distinct and connect them through
   an explicit revisioned link.

## Decision

Option 3 is selected.

A local project receives a stable `project_…` identifier when adopted. Its path,
display name, and Git remotes are mutable observations and never define identity.
A remote project has a separate server `project_…` identifier owned by one
organization. A provider binding records the provider, provider installation or
namespace, and the provider's immutable repository identifier; URL and name are
mutable metadata.

A `ProjectLink` binds one local project to one remote project after an explicit
plan and authorized confirmation. It records both identities, actor, device,
organization, timestamps, expected revisions, and optional provider evidence.
The link is not embedded as a claim that the two identifiers are equal.

Link, unlink, and conflict resolution are revisioned owner decisions. Unlinking
stops future synchronization and retains both projects and audit history.
Renames, local moves, provider transfers, archive state, and stale observations
do not create or replace a link automatically.

Project synchronization reuses the revision graph and idempotent server ledger
from `ADR-0005` and `ADR-0045`, scoped by organization for remote state. A
divergence produces an explicit conflict; neither server nor client silently
overwrites the newer owner decision. Local operation remains available while
offline or unlinked.

## Consequences

- `SPEC-078` owns identity fields, link states, synchronization, and executable
  conflict behavior.
- Technology detection and provider discovery may propose candidates, but only
  an authorized confirmation creates the link.
- The same physical repository may have observations on several devices while
  each local adoption retains its own local identity and explicit remote link.
- Existing project passports and revision history are preserved; migration adds
  bindings rather than rewriting project identifiers.

## Revisit conditions

Revisit this decision if a cryptographically verifiable portable project
identity becomes available across providers and local clones, or if one local
project must intentionally synchronize with several remote projects at once.
