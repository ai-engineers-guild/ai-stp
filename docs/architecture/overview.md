---
description: "Runtime responsibilities and data ownership."
last_verified: "2026-10-15"
---

# System boundaries

`apps/cli-v2` owns local business operations: identity, SQLite state, authoring,
source analysis, selection, bundles, account/sync/publication, installation and
recovery. Its library performs operations; the executable renders JSON envelope v1.
The [CLI guide](../../apps/cli-v2/README.md) maps services to modules.

The web owns account and catalog presentation. `apps/api` serves `/v1` through
`apps/platform` domain/persistence services; `apps/worker` processes asynchronous
jobs. PostgreSQL and object storage retain server state. The Tauri desktop shell
invokes the same CLI machine contract and owns no alternate installation engine.

Shared models generate `schemas/v1` and the HTTP client. `apps/cli` remains a
Python compatibility oracle for existing consumers and migration fixtures.
It is not a runtime dependency of the native executable.

A provider is an ai-stp installation component released from its public setup-system
repository. The CLI authenticates its exact release and prepares the bundle;
only that component writes the harness's final configuration. Linux isolation
and staged activation enforce this boundary. The user/vendor owns the harness
executable and its updates.

Published component/setup versions pin exact immutable bytes. Mechanical
compatibility, provenance, trust and access checks run before effects. Mutations
retain exact plans and receipts for idempotent recovery. Credentials stay in the
selected credential store; runtime state is not a development cache.
