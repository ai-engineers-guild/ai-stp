---
description: "Runbook: operator-managed official GitHub and package upstream component snapshots."
last_verified: "2026-09-03"
---

# Official upstream components

AI STP Official publishes attributed snapshots of curated public GitHub and
package components. Operators configure independently identified sources
locally. A daily enqueue creates at most one `official_upstream_sync` job per
enabled source. The worker resolves each source through the shared
`SourceIntent`/`SourceSnapshot` adapters and reuses the existing plan, bind,
validate, and publish jobs. There is no public management endpoint and no
automatic ownership transfer, catalog replacement, or identity merge.

## Configure sources

The normal `seed` startup step idempotently creates the verified public
`AI STP Official` publisher profile in development and production. Source
configuration therefore never depends on an operator signing in as that
service account.

From a host that can reach PostgreSQL, upsert one source per component. Omit
`--id` to update the default `official` row. Additional Git or package sources
take an explicit identifier:

```sh
python -m ai_stp_platform.official_upstream upsert \
  --repository https://github.com/owner/repo \
  --ref main \
  --path skills/example \
  --type skill \
  --name "Example skill" \
  --project-name "Example" \
  --maintainer "Upstream maintainers" \
  --description "Reviewed summary of the snapshot." \
  --license MIT \
  --harness-id claude-code

python -m ai_stp_platform.official_upstream upsert \
  --id npm-example \
  --kind package \
  --ecosystem npm \
  --package-name example \
  --package-version 1.2.3 \
  --type skill \
  --name "Example package" \
  --project-name "Example" \
  --maintainer "Upstream maintainers" \
  --description "Reviewed summary of the snapshot." \
  --license MIT \
  --harness-id claude-code
```

`--path` is the skill directory, not `SKILL.md` alone. The snapshot is every
tracked file under that path. Gitignore is the filter; extract does not drop
tests, CI, or other committed trees.

The owner defaults to the AI STP Official account. Non-HTTPS GitHub URLs,
embedded credentials, traversing paths, unknown component types, unknown
package ecosystems, and a non-Official owner are rejected. Repeating the
command with the same `--id` updates that row only.

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
enabled source. Disable or delete a source to stop later enqueue for that row
without deleting published catalog versions, audit rows, or sync history.

```sh
python -m ai_stp_platform.official_upstream disable --id npm-example
```

A matching embedded snapshot may produce a dismissible catalog-replacement
suggestion when canonical coordinate and artifact digest both match. The
suggestion never replaces, promotes, or merges identities.

## Verify

1. Each intended source row is `enabled` and owned by the Official account.
2. The worker processed `official_upstream_sync` for today's UTC date per
   enabled source.
3. Unchanged component bytes leave the last published version in place.
4. A new digest creates the next unused minor version on that source's own
   stable line, then `validate` and `publish` jobs from the shared publication
   pipeline.
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

## Rollback

Disable the affected source so scheduling stops for that row. Immutable
published versions remain readable. A previous deployment can still read source
and sync rows.
