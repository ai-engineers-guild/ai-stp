---
description: "Decision to deploy production from the public repository through anonymous fetch without credentials."
last_verified: "2026-08-21"
---

# ADR-0109: The deployment source is the public repository

Status: accepted. Clarifies the transport in `ADR-0103` without superseding it.
Continued by `ADR-0111`: the release candidate is built where it will be
published.

## Context

`ADR-0103` removed the runner from the production host: a green `check` advances
`refs/heads/deploy/prod`, and a one-minute timer on the host fetches that ref
over an outbound connection. The transport was SSH through
`ssh.github.com:443` with a read-only deploy key because the source was a
private repository.

The public `ai-stp` tree (`ADR-0108`) made that assumption unnecessary. The
published paths contain all code that deployment builds and runs: `apps`,
`packages`, `migrations`, `deploy`, `docker-compose.prod.yml`, `Dockerfile*`,
`alembic.ini`, `uv.lock`. None of the withheld material—private fleet
decisions, internal reports, agent memory, `.github`—is read during deployment.

While both repositories were advanced, `deploy/prod` existed in two places and
meant different things. This is not a divergence someone would notice: the host
would silently deploy whichever one it found first.

## Options

**Keep the private source.** Change nothing. This preserves the deploy key, SSH
configuration, and the obligation to keep it aligned with GitHub host keys. It
also leaves the `git_commit` in `/v1/system/version` unresolvable by anyone
without access to the private repository.

**Public source, still over SSH.** This removes ref ambiguity but preserves a
credential that no longer protects anything: the content is anonymously
available.

**Public source, anonymous HTTPS.** This removes both ref ambiguity and the
credential.

## Decision

By default, `deploy/pull-deploy.sh` fetches
`https://github.com/ai-engineers-guild/ai-stp.git`. Fetching is anonymous: the
host has no deploy key, no SSH configuration, and no secret to rotate.

Only this repository advances the ref. The private repository no longer
contains a deployment workflow.

The script resets the mirror remote to `${AI_STP_PULL_REPOSITORY}` on every
run, not only at creation. The previous form set the remote once, so changing
the source changed nothing—the mirror continued using the old address.

## Consequences

The deployed identity becomes publicly verifiable: the `git_commit` returned
by `/v1/system/version` resolves to a commit in the open repository, and proof
of deployment no longer requires access.

Changing the source is a one-time history discontinuity. The two repositories
have no common ancestor, so rollback protection fails, correctly: it does
exactly what it was written to do. The transition requires a deliberate
baseline reset—deleting the mirror and the recorded `git_commit`—and the order
is documented in the runbook. Rollback protection continues unchanged within
the public history.

Application secrets are unaffected: they live in `.env.prod` on the host,
which no workflow reads or writes. No credential moves to the public
repository; everything CI needs remains in GitHub secrets.

`AI_STP_DEPLOY_SSH_KEY`, `AI_STP_DEPLOY_HOST`, `AI_STP_DEPLOY_USER`, and
`AI_STP_DEPLOY_KNOWN_HOSTS` are read by nothing and are removed.

## Reconsideration conditions

Reconsider if the public tree ceases to contain everything deployment builds,
or if a second deployed environment needs its own ref.
