---
description: "What works without the network after initial setup and what requires connectivity."
last_verified: "2026-08-13"
---

# Offline operation boundary

The decision owner is `ADR-0019`, and the requirements owners are `SPEC-001` and
`SPEC-014`. This document defines the machine boundary: which operations must work
without the network after successful initial setup and which return a typed reason.

Offline capability is assessed only after successful initial setup. Before that, the
product truthfully reports that the toolset and providers have not yet been obtained.

## Offline operations

| Area | Behavior without the network |
|---|---|
| Developer and project passports | reading, modification, revisions |
| Project index | complete scan and rescan |
| Local registry | reading, drafts, registration, version recording |
| Imported and owned objects | selection, validation, installation |
| Search | local index and previously obtained catalog cache |
| Selection and compilation | from local and cached candidates |
| Checks | with installed toolset tools |
| Package and plan | construction and inspection |
| Installation and launch | application, state, recovery, launch from cached artifacts |

## Operations requiring the network

| Area | Reason |
|---|---|
| First uncached download of a tool or provider release | the artifact has not yet been obtained |
| Sign-in and identity linking | external provider |
| Uncached cloud search | server index |
| Access to private cloud objects | server-side entitlement check |
| Synchronization | revision exchange |
| Publication | server-side validation and immutable snapshot |
| Invitations and permissions | server state and email |
| Report submission | server-side moderation case |
| Revocation and blocking information update | policy freshness |
| Live validation of remote MCP | external connection point |

## Behavior rules

An offline operation uses only previously validated cached artifacts and does not relax
integrity, version, or trust-policy requirements.

`registry acquire --id <setup_id> --version <X.Y>` obtains the complete exact closure
of the published setup and atomically makes it available to the local compiler. The
`--offline` variant does not access the network: it revalidates stored passports and
artifact bytes and, if any node is absent, fails without a partially materialized graph.
Acquisition neither selects a setup nor changes the target.

When the cache is read again, it revalidates the size and original digest domain:
`ArtifactRef` uses `ai-stp:artifact:v1`, while an exact HarnessBundle uses a separate
raw SHA-256 ZIP. These bytes reside in separate cache spaces and do not substitute for
one another.

Signing out has two halves, and only one works offline. Server-side session revocation
requires connectivity; local credential deletion does not, and is performed in every
case: failure would leave the token on disk, which is worse than a session surviving it.
An uncompleted server-side revocation returns a warning in the envelope and does not
change the exit code. The requirement owner is `SPEC-002` `REQ-219`.

Cached catalog state is displayed with the time it was last checked. Stale blocking
information is not presented as current.

Network unavailability produces `degraded` or a typed reason, but does not become an
empty successful result or disable local functions.

Revoking a device prevents future cloud operations and does not delete local data or
already validated cached bytes.
