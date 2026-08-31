---
description: "Machine contract for local GitHub archive evidence and observation history."
last_verified: "2026-08-15"
---

# GitHub archive evidence

## Commands

`component source evidence refresh --id <stable_id> --version <X.Y>` obtains one
official observation. `show` and `history` read only the local registry. Exact
parameters and result schemas belong to the generated `help --agent`.

## Identity and state

The input coordinate comes from the immutable passport of the specified version.
The first observation uses `owner/repository`; subsequent observations use the
immutable GitHub repository id. Thus, rename and transfer change
`repository_full_name` but not identity. Each row contains the original source,
exact passport digest, `archived`, retrieval time, freshness period, and
attribution for the official REST contract.

`archived=true` produces only `proposal=deprecated`. `blocked`, lifecycle
changes, replacement, update, and target removal are not effects of these
commands.

## Freshness and failure

TTL is 24 hours. The latest observation is returned as `fresh` or `stale`; if
none exists, it is returned as `unavailable`. A conditional `304` creates a new
timestamped observation with the same state. History is append-only, so a later
unarchive does not erase the earlier fact.

The response is limited to one MiB and a closed allowlist model. Redirects are
not followed, and there is no credential surface. 403, 404, 429, server or
transport failure, invalid JSON, a private repository, and a changed repository
id fail closed and do not replace the latest good snapshot.

## Server and public catalog

Local CLI evidence remains the owner of this document. Server/Web delivery of
periodic archive observations has been removed: the public catalog no longer
carries `github_archive`, while detail reads on-demand `stars`/`archived` under
`SPEC-049` and `ADR-0096`.
