---
description: "Runtime responsibilities and data ownership."
last_verified: "2026-11-04"
---

# System boundaries

`apps/cli` owns local business operations: identity, SQLite state, authoring,
source analysis, selection, bundles, account/sync/publication, installation and
recovery. Its library performs operations; the executable renders JSON envelope v1.
The [CLI guide](../../apps/cli/README.md) maps services to modules.

The web owns account and catalog presentation. `apps/api` serves `/v1` through
`apps/platform` domain/persistence services; `apps/worker` processes asynchronous
jobs. PostgreSQL and object storage retain server state. The Tauri desktop shell
invokes the same CLI machine contract and owns no alternate installation engine.

Shared server models generate `schemas/v1` and the HTTP client. The retired
Python CLI is preserved on the `legacy/python-cli` branch.
It is not a runtime dependency of the native executable.

The native installation engine compiles exact setup graphs, reviews changes and
writes harness configuration through its transaction and custody services.
Historical external-provider operations keep their exact artifacts and recovery
route. The harness executable is managed by its user or vendor. See the
[configuration standard](../../standards/setup-systems.md).

Published component/setup versions pin exact immutable bytes. Mechanical
compatibility, provenance, trust and access checks run before effects. Mutations
retain exact plans and receipts for idempotent recovery. Credentials stay in the
selected credential store; runtime state is not a development cache.
