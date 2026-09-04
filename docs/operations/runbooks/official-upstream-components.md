---
description: "Runbook: operator-managed official GitHub and package upstream component snapshots."
last_verified: "2026-09-04"
---

# Official upstream components

AI STP Official publishes attributed snapshots of curated public GitHub and
package components. The checked-in manifest at
`packages/contracts/src/ai_stp_contracts/official/manifest.json` is the only
production inventory: PostgreSQL is its projection, not a second source of
truth. A daily enqueue creates at most one `official_upstream_sync` job per
enabled source. The worker resolves each source through the shared
`SourceIntent`/`SourceSnapshot` adapters and reuses the existing plan, bind,
validate, and publish jobs. There is no public management endpoint and no
automatic ownership transfer, catalog replacement, or identity merge.

## Current Official inventory

The normal `seed` startup step idempotently creates the fixed public account:
ID `account_01KZET6ZKJN7S72T5H4WDV62T0`, handle `ai-stp-official`, display name
`AI STP Official`. The manifest currently declares these exact source IDs,
stable component IDs, and displayed names:

| Source ID | Stable component ID | EN display name | RU display name |
|---|---|---|---|
| `ponytail` | `component_01M1PBHXMXW2WR8Q16KHJAHVHT` | Ponytail | Ponytail |
| `caveman` | `component_01M1PBHXMXW2WR8Q16KHJAHVHV` | Caveman | Caveman |
| `grill-me` | `component_01M1PBHXMXW2WR8Q16KHJAHVHW` | Grill Me | Grill Me |
| `context7-mcp` | `component_01M1PBHXMXW2WR8Q16KHJAHVHX` | Context7 MCP | Context7 MCP |
| `serena-mcp` | `component_01M1PBHXMXW2WR8Q16KHJAHVHY` | Serena MCP | Serena MCP |
| `ai-stp-skill` | `component_01M1PBHXMXW2WR8Q16KHJAHVHZ` | AI STP Skill | Навык AI STP |

The manifest also fixes each repository, ref, component subpath, component
kind, attribution, exact stable ID, canonical name, and update policy. Add or
change a source by editing and reviewing that JSON file, then deploy and run
manifest reconciliation. Do not hand-edit or production-upsert a source row;
undeclared rows fail reconciliation and transferred/removed rows stay fenced.

Validate or project the inventory from a host that can reach PostgreSQL:

```sh
python -m ai_stp_platform.official_upstream validate
python -m ai_stp_platform.official_upstream reconcile
python -m ai_stp_platform.official_upstream status
```

## Daily enqueue

Every running worker enqueues once when it starts and again after the UTC date
changes. The daily idempotency key makes multiple workers and restarts safe.
Repeating the scheduler command on the same UTC day returns the existing job
and does not run the fetch again.

A developer with PostgreSQL access can enqueue a new attempt without an HTTP
endpoint. `--force` writes a distinct audited queue row; the running worker
picks it up. Disabled sources are skipped; an explicit `--id` of a missing or
disabled row is rejected. Payload remains only `source_id`.

```sh
python -m ai_stp_platform.official_upstream.enqueue
python -m ai_stp_platform.official_upstream.enqueue --force
python -m ai_stp_platform.official_upstream.enqueue --force --id ponytail-skill
```

One source's failure, disable, or idempotency key does not affect another
enabled source. Disable a source to stop later enqueue for that row without
deleting published catalog versions, audit rows, or sync history. Ownership
transfer is a database-bound operation: it changes every historical catalog
row's current owner, appends an ownership revision, marks the source
`transferred` and `update_policy=disabled`, cancels pending outbox/jobs, and
fences running attempts. Reconciliation preserves that tombstone and cannot
reactivate it.

```sh
python -m ai_stp_platform.official_upstream disable --id ponytail
```

A matching embedded snapshot may produce a dismissible catalog-replacement
suggestion when canonical coordinate and artifact digest both match. The
suggestion never replaces, promotes, or merges identities.

## Verify

1. Each intended source row is `enabled` and owned by the Official account.
2. The worker processed `official_upstream_sync` for today's UTC date per
   enabled source.
3. Unchanged component bytes leave the last published version in place.
4. A new digest creates a canonical projection artifact and explicit adaptation,
   then the next unused minor version on that source's own stable line, followed
   by `validate` and `publish` jobs from the shared publication pipeline.
5. The published description starts with upstream project, repository or
   package coordinate, license, and maintainer attribution and ends with the
   ownership-claim notice.

`AI_STP_WORKER_GITHUB_TOKEN` is sent only to `api.github.com`. Without it,
GitHub allows 60 requests per hour per IP. Each git source uses two API
calls before the archive download, so a catalog of this size exhausts that
budget in one scheduler pass and jobs fail as `GitHub rate limit exceeded`.
A fine-grained token with public repository metadata read is enough; write
access and private repositories are not required. Redirects are followed
only to `api.github.com`, `github.com`, and `codeload.github.com`. The token
is never written to job payloads, source rows, logs, or descriptions. In
local compose it comes from gitignored `.env.dev` (`env_file`); do not set
an empty override in `environment`, which would wipe that value.

For delivery gaps or a worker crash, inspect the attempt ledger and outbox,
then run reconciliation. The status output includes attempt state/result,
retry count, queue and outbox IDs/states, error class/code, manifest digest,
provenance, plan ID, and timestamps. A failed attempt is retried only through
the bounded queue policy or an explicit `retry --id`; exhausted work remains
in the queue DLQ and the domain ledger as `dead_lettered`.

```sh
python -m ai_stp_platform.official_upstream reconcile-delivery
python -m ai_stp_platform.official_upstream retry --id ponytail
```

## Rollback

Disable the affected source so scheduling stops for that row. Immutable
published versions remain readable. A previous deployment can still read source
and sync rows.
