---
description: "Decision to store public documents and policies as revisions with repository import."
last_verified: "2026-08-08"
---

# ADR-0070: Versioned Public Documents and Policies

Status: accepted.

## Context

The site needs technical documents for people and agents, as well as privacy, cookie,
service, and author-content/license policies. Repository files are the best source
of technical documentation, but the website must be able to serve an immutable
localized revision through the API and store policy texts separately from deploys.

## Alternatives

1. Render `docs/**` using the Next.js file system. No API, version history,
   locale lifecycle, or policy draft/publish.
2. Create a free-form CMS. Expands the attack/authoring surface without an MVP need.
3. Introduce platform-owned immutable PublicDocument revisions, imported from
   permitted pinned repository sources or published by a service process.

## Decision

Alternative 3 is accepted per SPEC-031. Technical docs remain canonical in Git;
CI import records the exact source commit/path/digest in the platform revision. Policies
have staff-controlled drafts/publishing/supersession. The public web/API reads only
published localized revisions through a shared safe Markdown renderer.

## Consequences

- Document/revision storage, an API, an import job, a public cache policy,
  an operator workflow, and migration/archive tests are required.
- The web does not fetch Markdown from an arbitrary URL and is not a Git client.
- Future mandatory policy acceptance will require a separate ADR and an auditable
  account acceptance record.
- The global 500 page and 404 are part of the public shell, not a policy CMS fallback.

## Reconsideration Conditions

The decision will be reconsidered if multi-repository docs federation,
enterprise legal tenancy, or mandatory electronic consent to a policy is introduced.
