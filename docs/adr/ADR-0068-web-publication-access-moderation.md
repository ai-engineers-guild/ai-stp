---
description: "Decision on web owner-read models and secure publication, permissions, and moderation flows."
last_verified: "2026-08-08"
---

# ADR-0068: Web for owned objects, publication, permissions, and moderation

Status: accepted.

## Context

`ADR-0018` assigned account management and publication to the web, but left passport
creation, indexing, building, checks, and installation to the CLI and agent.
`ADR-0043` selected RSC, Server Actions, and the generated OpenAPI client, while
`ADR-0041` established server sessions and double-submit CSRF. `#181` materialized
the server scenarios for publication, grants, reports, and staff actions according
to `ADR-0067`.

After that, `apps/web` already has a landing page, public catalog, sign-in, account,
and devices, but no owner workspace. In addition, the existing API write paths do
not form a sufficient and secure read surface: the anonymous catalog intentionally
does not expose private objects, `sync` is a revision ledger for the CLI client,
and the staff routes do not provide a work queue. Attempting to assemble a screen
in the browser from these sources would duplicate the visibility policy, expose
private metadata, and turn Zustand into an incorrect source of truth.

Invitation acceptance poses a separate threat: the wire contract requires a
single-use token, but the query/path, server-rendered page, referrer, browser
history, and telemetry must not receive it. A regular Server Action accepts form
data on the server, so it is not suitable as an unconditional transport for the
raw invitation token.

## Alternatives

1. Build the screens on the public catalog, local `sync` ledger, and existing
   write routes. This is fast, but private owner data is incomplete, policy is
   duplicated on the client, and sync takes on the role of a web read model that
   does not belong to it.
2. Add a separate BFF/GraphQL layer to `apps/web` that aggregates the database and
   API. This provides convenient screens, but introduces a second authorization
   mechanism, a second DTO contract, and a second application layer contrary to
   `ADR-0018` and `ADR-0043`.
3. Extend `/v1` with minimal account-scoped owner/staff read models in
   `packages/contracts`, use RSC and Server Actions for regular mutations, and
   transmit the invitation token only via fragment-to-same-origin POST.

## Decision

Alternative 3 is accepted.

### 1. The owner workspace reads dedicated server read models

`#183` introduces a web owner workspace for owned objects and exact versions,
publication plans, invitations/grants, the owner's reports, and minimal staff
cases. The required owner/staff read models are designed first in
`packages/contracts`, fixtures, and OpenAPI, then implemented as vertical API
slices according to `ADR-0037`, and only then included in the generated client
for `apps/web`.

Each server read model checks the owner, an active grant, or the staff allowlist
on the server. It returns only the information required by the screen, not the
complete passport, revision ledger, storage key, original attestation, or private
bytes. Public catalog, grant, and owner views may refer to the same exact version,
but they are not interchangeable and are not merged by the client.

The exact routes, fields, cursor, and errors are not established by this record:
they are owned by `packages/contracts`, `schemas/v1/openapi.json`, and
`docs/contracts/http-api.md`. The change remains additive within the supported
major API version.

### 2. One API and server truth

RSC reads owner/staff data on the server after checking the server session. Regular
mutations—creating and confirming a publication plan, issuing and revoking an
invitation, submitting a report, and performing a staff action—go through thin
Next Server Actions using the existing CSRF transport; after the response, they
invalidate and reread the server view. Zustand stores only short-lived UI state,
not permission, lifecycle, grant, or publication truth.

The client does not calculate installation eligibility, the trust line, lifecycle
transitions, access to a private object, or staff authorization. It displays the
typed result of the shared `/v1` scenario, which is also available to the CLI, and
shows the returned request/operation IDs. This preserves the prohibition against
a second business-logic implementation from `ADR-0018`.

### 3. Invitation token: fragment and direct POST

The email links to a localized invitation page with the invitation identifier and
the raw token only in the URL fragment. The fragment is not sent to the HTTP
server, is not included in the referrer, and is not stored in history as a
query/path. A focused client component reads the fragment, keeps the token only
in memory, and sends it in a direct same-origin `POST /v1` with credentials and a
double-submit CSRF header. After sending it, the component removes the fragment
using `history.replaceState` and displays the server outcome.

This exception to the preference for Server Actions is a documented transport
security reason under `SPEC-010` `REQ-1011`. The component does not validate the
token, email, expiry, or grant; these remain part of the single API scenario. The
token is never passed into RSC props, a Server Action, the path, query parameters,
logs, analytics, a notification, audit, or persistent browser storage.

### 4. Minimal moderation is not a client-side role

Staff navigation is permitted as a convenience, but it is not an access boundary.
The API returns the staff work queue, case card, and mutations only to an account
on the server allowlist from `SPEC-026`; the web does not maintain a staff list
and does not attempt to distinguish a nonexistent case from a private case for a
non-staff user. The work queue is limited to triage, lifecycle actions, and
`author_verified`; full RBAC, search across all accounts, organizations, and a
universal audit explorer are not introduced.

Every staff action requires explicit confirmation and a reason, and the server
writes append-only audit records. The UI displays a safe action correlation, but
does not copy audit data into independent client-side storage. Reporter identity
and security details remain within the boundaries of `SPEC-016` / `ADR-0031`.

## Consequences

- `SPEC-027` is introduced with web-layer requirements and executable criteria;
  the product rules in `SPEC-002`, `SPEC-007`, and `SPEC-016`, and the server
  materialization in `SPEC-026`, are not rewritten.
- Additive owner/staff read models, fixtures, OpenAPI, and the generated client are
  added before the screens; `apps/web` does not gain manual DTOs, a BFF, or
  database access.
- New pages are placed in the existing locale-aware App Router and inherit
  `ru`/`en`, the RSC privacy boundary, Server Actions, and the UI kit from
  `ADR-0043`.
- Invitations receive a dedicated fragment-only web transport; a browser test is
  required to verify the absence of the token from the URL, referrer, HTML,
  history, storage, and trace.
- Matrix tests are required for owner/grantee/outsider/staff, redaction,
  publication states, idempotency, locale/a11y, and the absence of a second
  business-logic implementation.
- If an API read model is absent, the screen does not construct it from sync or
  the public catalog: the feature remains explicitly unavailable until a
  contract-first implementation is provided.

## Reconsideration Conditions

The decision is reconsidered if a demonstrated need for a browser editor emerges,
if the required owner read model cannot be expressed through an additive `/v1`
contract, if invitation acceptance cannot be performed securely through a
same-origin fragment POST, or if the staff allowlist outgrows the minimal surface
and requires a full-fledged role and delegation model.
