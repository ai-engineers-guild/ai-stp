---
description: "Decision to remove the GitHub Actions runner from the production host and deploy only a monotonically advanced ref after green CI."
last_verified: "2026-08-29"
---

# ADR-0103: The target pulls a monotonic deployment ref

Status: accepted. Supersedes, for the permanent GitHub Actions runner, a
decision owned by private infrastructure and not published here. Refined by
`ADR-0109`: the public repository becomes the deployment source while this
record's transport remains unchanged.

## Context

The previous decision correctly reversed the transport: the production host
establishes the outbound connection, while CI receives no SSH key and does not
enter the server. However, the permanent Actions runner left a credential on
the production host that accepts executable workflows and made the GitHub
scheduler part of the runtime server—the last permanent Linux exception.

## Decision

After a green `check` of an exact push commit, a disposable release worker
performs only promotion: without force, it advances
`refs/heads/deploy/prod` to the verified SHA. A delayed old workflow cannot
roll the ref back.

The production host is no longer registered as a runner. A one-minute systemd
timer uses an outbound connection and a read-only deploy key to fetch the sole
ref. `deploy/pull-deploy.sh`:

- maintains a bare mirror and serializes execution with `flock`;
- rejects a non-fast-forward transition relative to the deployed SHA;
- extracts the exact commit into a content-addressed directory;
- writes the existing recovery marker before changing the tree;
- preserves host-owned `.env*`, `.deploy-env`, `.deploy-state`, and backups;
- invokes the unchanged `deploy/run.sh` and `deploy/verify.sh`.

GitHub receives write access only in the promotion job. The target has read-only
Contents access and cannot modify checks, workflows, or refs.

## Consequences

The Actions credential and runner service are removed from the production host
after the canary. Deployment is asynchronous relative to the promotion job; the
authoritative result is the exact identity in `.deploy-state/current`, the
systemd journal, and external `verify_public.py`. Manual exact-SHA deployment
and rollback continue to work.
