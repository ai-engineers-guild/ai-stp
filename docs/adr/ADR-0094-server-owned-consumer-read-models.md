---
description: "Server-owned read models for external evidence and account-scoped selection impact without changing domain trust."
last_verified: "2026-08-15"
---

# ADR-0094: Server-owned consumer read models

Status: accepted. The GitHub archive read-model and account blast-radius
delivery parts are superseded by `ADR-0096`. Canonical copy, deep-link, and the
other consumer decisions in this ADR remain in force.
The superseded parts are continued by `ADR-0096`.

## Context

`SPEC-030`, `SPEC-043`, and `SPEC-044` already have working shared/CLI sides,
but web and server do not yet project them fully:

- web duplicates CLI copy templates and already diverges from the canonical parser;
- the catalog does not show the GitHub archived observation;
- account/org-wide selection impact and blast radius are absent from API/web;
- a local CLI report must not be represented as server-wide completeness;
- a public catalog request must not become a proxy for the GitHub API.

Existing decisions remain in force: `ADR-0064` owns the pure deep-link grammar,
`ADR-0082` separates the external GitHub fact from lifecycle, and `SPEC-043`
prohibits sending private content to an external tokenizer. Only the new
boundary must be established: where server observations live, who builds the
account projection, and how web receives it without a second domain model.

## Decision

### 1. Server owns only the server read model

Server stores bounded observation history for public GitHub metadata and an
account-scoped projection for synced entities. This does not become a new source
of truth for the passport, lifecycle, or trust.

The latest observation and append-only history are logically separate from
`RepositoryMetric`: stars and archive state have different semantics, TTL,
error policy, and consumer contracts.

### 2. External evidence remains an observation

The worker makes a public, conditional, bounded GitHub request. Catalog/API reads
the latest stored result. `archived=true` creates only a visible
warning/deprecation proposal. API, web, and worker do not set `deprecated`,
`blocked`, or `component_verified`, and do not delete a target automatically.

Rate limiting, failure, an invalid response, a private repository, and a change
in `repository identity` neither replace the latest `good observation` nor turn
into `archived`.

### 3. Account impact receives a new server-contract version

Local v1 schemas retain `freshness=local_snapshot` and
`authority_boundary=local_registry`. Server does not reuse these values for
account-wide data.

The server projection receives a separate versioned response family with explicit:

- `authority_boundary=account`;
- source revision / snapshot timestamp;
- `freshness=account_snapshot`, `stale`, or `unavailable`;
- read-only `action=none`;
- exact/estimated/unavailable measurement states.

This lets CLI and web present the same meaning without falsely claiming that the
local registry equals the account-wide registry.

### 4. API remains the sole web/backend boundary

Web does not read PostgreSQL, GitHub, or the local CLI registry. It uses the
generated API client and shared parser/corpus. The public catalog receives an
optional safe archive summary; impact/blast-radius resources require
authentication and account-ownership checks.

The public `catalog` route performs no network refresh. `Refresh` is a bounded
worker task with an idempotent key based on `repository identity` and the
`freshness window`.

### 5. Canonical copy and deep-link grammar are not duplicated

Python contracts remain the source of CLI copy templates and deep-link grammar.
Web receives a generated projection or a build-time drift-checked artifact. Any
manual string copy of a command, URL path, locale, or report fragment is a
contract defect.

### 6. UI shows provenance and uncertainty

Archive status is a separate external-evidence warning, not a trust badge. The
impact panel shows baseline, authority, freshness, exact/estimated/unavailable,
and capability delta. No card collapses these facts into one score or offers a
destructive action.

The visual implementation remains in the current ai_stp design system: semantic
tokens, existing card/detail/menu primitives, RU/EN parity, keyboard/focus
support, reduced motion, and responsive Operate behavior. The `$impeccable`
shape brief and acceptance checklist are part of the delivery plan but do not
replace the contract.

## Considered options

1. **Query GitHub from the catalog request.** Rejected: it creates unstable
   TTFB, rate-limit coupling, and nondeterministic public results.
2. **Show the CLI local registry in web.** Rejected: web cannot access the local
   file, and this mixes authority boundaries.
3. **Put archive state in `RepositoryMetric`.** Rejected: stars and lifecycle
   evidence have different TTL, history, and error semantics.
4. **Change the v1 impact schema in place.** Rejected: the old CLI contract
   would cease to describe `local_snapshot` honestly.
5. **Create web-only command strings and URLs.** Rejected: this has already
   caused drift and breaks `REQ-3009`/`REQ-3706`.
6. **One shared risk score for impact/archive.** Rejected: capability, external
   evidence, and lifecycle policy belong to different axes.

## Consequences

Benefits:

- web, CLI, and API receive one verifiable meaning without copy-paste contracts;
- the public catalog remains fast and independent of GitHub availability;
- stale/unavailable evidence is visible and does not become false trust;
- the account-wide report has an honest authority boundary;
- migration/rollback do not change immutable catalog bytes.

Costs:

- server observation storage, a migration, and a worker job are added;
- the impact report needs a separate server-response variant and API test matrix;
- generated web artifacts become a required part of `web-check`;
- UI must support more states than only ready/error.

## Rollout and recovery

1. First add contracts, schemas, negative fixtures, and generated outputs.
2. Apply the nullable observation migration; an empty table means `unavailable`.
3. Start worker refresh for public GitHub coordinates with bounded retry.
4. Enable the additive catalog field and web warning.
5. Enable the impact v2 endpoint after account read-model tests.
6. On a worker failure, disable the refresh job while retaining the latest good
   snapshot. On a projection failure, return explicit `unavailable` without
   hiding the catalog object.
7. On a deployment failure, roll back the application using the normal runbook;
   observation history must not be deleted.

## Reconsideration conditions

The decision is reconsidered when adding a second forge, credentialed/private
observation, org-wide roles, an auto-lifecycle workflow, an external tokenizer,
or a public report resource. Each such change requires a separate ADR and a new
version of the affected machine contract.
