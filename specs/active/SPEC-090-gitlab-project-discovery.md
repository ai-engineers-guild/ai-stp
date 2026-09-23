---
description: "SPEC-090: Tenant-scoped GitLab repository observation over canonical project identity."
last_verified: "2026-09-22"
---

# SPEC-090: GitLab project discovery

## Purpose

List and retain GitLab repository observations without inferring corporate project
identity or creating a project link from names or URLs.

## Scope

The shipped GitLab.com and operator-allowlisted self-hosted read adapter, per-tenant
runtime connection, provider identity registration, refresh, disconnect, and their
HTTP contracts. SPEC-078 owns explicit project linking. SPEC-081 owns canonical
technology facts; the enrichment route hands mapped language observations to its
existing proposed-fact publication service.

## Terms

- `Provider observation` — a GitLab repository's immutable numeric identity and
  mutable metadata retained on `ProjectIdentity(namespace="provider")`.
- `Connected` — an observation with the configured GitLab installation marker;
  disconnected observations remain retained and cannot refresh.
- `Language enrichment` — a complete GitLab language API observation for one
  explicitly linked project and one immutable mapping snapshot.

## Requirements

- `REQ-9001`: The adapter accepts only the exact configured HTTPS GitLab authority,
  rejects URL credentials, paths, fragments, IP literals, unexpected ports and
  redirects, and bounds response bytes and pagination. It never requests a source
  archive or executes repository code.
- `REQ-9002`: Listing requires the caller's tenant `project.list` permission and
  returns at most 500 repositories with immutable numeric IDs, exact namespace,
  path, URL, default branch, and activity time. The runtime credential is not a
  request, response, audit, passport, or log field.
- `REQ-9003`: Register requires `project.create`; refresh and disconnect require
  `project.update`. Mutations check capability revision, expected identity revision,
  and idempotency key. They append a bounded audit record.
- `REQ-9004`: Provider observations use the canonical `ProjectIdentity` provider
  namespace. Host plus immutable repository ID is the external key. Renames update
  mutable metadata and preserve the provider project ID. The observed branch and
  revision are retained; no discovery route creates or changes `ProjectLink`.
- `REQ-9005`: An inaccessible, deleted, or private upstream repository leaves the
  retained observation intact and returns a non-enumerating error. Disconnect stops
  refresh by clearing the provider installation marker while retaining identity,
  metadata, and existing explicit links. Register with the current revision can
  reconnect the same immutable identity.
- `REQ-9006`: Language enrichment requires a current explicit project link,
  matching observed head revision, and an immutable tenant mapping snapshot.
  Mapped languages publish through the canonical scan service as proposed facts
  with source revision, confidence, detector and mapping versions. Unmapped
  language names never create technology IDs. A replay with the same scan ID and
  idempotency key returns the retained result without another upstream read.
- `REQ-9007`: Register and refresh update repository activity and source
  availability and advance the project revision on each successful observation
  for an explicitly linked corporate project only. The authorized project read
  projects the linked GitLab repository namespace, URL, default branch, and observed revision from
  the retained provider identity, bounded to 256 identities. An unlinked
  observation never creates a project or changes its activity/passport.

## States and errors

An observation is connected after register, disconnected after disconnect, and
connected again only through register with its current revision. A rename or
namespace transfer changes mutable fields during refresh, not the stable provider
project ID. Stale capability or identity revisions reject before mutation;
inaccessible repositories preserve prior metadata; an absent explicit link rejects
before language fetch. Unknown languages are omitted from proposed facts.

## Security and privacy

Tenant membership and permission checks precede access to per-tenant connection
settings. The connection is operator-configured. The adapter has no redirect path,
reads only bounded metadata endpoints, and never returns source contents. Audit
details contain repository IDs and revisions without credentials or API payloads.

## Compatibility and migration

Migration 0091 adds nullable default-branch and observed-revision fields to the
existing provider identity table. Older identity rows remain valid. Rolling back
the API disables discovery while retaining previously observed provider identities;
database downgrade drops only the two new metadata columns.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-9001` | GitLab client unit tests cover authority allowlisting, redirects, response limits, and safe read endpoints. |
| `REQ-9002` | API list and contract tests cover bounded output, tenant isolation, and forbidden credential fields. |
| `REQ-9003` | API mutation tests cover authorization, revision checks, replay, and audit persistence. |
| `REQ-9004` | API and migration tests cover register, rename refresh, exact identity retention, and absence of implicit links. |
| `REQ-9005` | API tests cover inaccessible refresh, disconnect retention, and refusal to refresh disconnected observations. |
| `REQ-9006` | API tests cover explicit-link enforcement, mapped proposed facts, evidence provenance, and network-free replay. |
| `REQ-9007` | API tests cover linked activity, source availability, and project read metadata without implicit link creation. |
