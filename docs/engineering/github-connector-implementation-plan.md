---
description: "Implementation and verification sequence for GitHub Connector issues 181 through 186."
last_verified: "2026-09-08"
---

# GitHub Connector implementation plan

## Objective and baseline

Finish issues 181 through 186 on branch
`codex/issues-181-186-mainline-20260908`. The implementation baseline is commit
`766ef302`, recovered from GitWork3 and applied on remote `main` commit `61828fb4`.
SPEC-072 and ADR-0173 are normative. This document replaces the ignored local note
`plans/plan_github_connector_181_186_20260908.md` as the tracked execution plan.

Issue 185 remains in SPEC-072 because issue 182 includes repository-management
actions. A delivery limited to the user's current 181, 182, 183, 184 and 186 set may
leave invitations unshipped, but it must not weaken the shared administration
boundary or break the already recovered invitation code.

## Fixed architecture

- GitHub sign-in proves identity only.
- One GitHub App is used for both source and repository-management operations. Its
  selected-repository installation requests metadata/contents read and
  administration write. No new GitHub Actions workflow is required by these issues.
- Source access and administration remain separate consent records and separate
  durable plans. Product policy, not a second App, prevents ordinary source work from
  mutating GitHub.
- Private repository coordinates remain in a server-only source binding. Published
  passport bytes keep `source=null` for a private source.
- Component promotion changes distribution policy and projections only. It never
  rewrites or copies the version, passport, digest, provenance or artifact bytes.

## Recovered implementation inventory

| Area | Present at `766ef302` | Required proof before done |
| --- | --- | --- |
| Connector persistence and crypto | Connector, OAuth-flow, source-binding and repository-action models; account/purpose-bound token encryption | Expiry, replay, account/session and redaction matrix |
| Connector API | Connect, callback, status, disconnect, selected sources and repository action routes | Personal and organization flows, pending approval, revoke/suspend and safe upstream errors |
| Private source preparation | Exact repository ID, commit and subpath; archive validation and canonical packing | API publication path, unsafe archive matrix and no-coordinate-leak assertions |
| Publication binding | Publication plan accepts and rechecks `source_binding_id` | Exact passport comparison, idempotent confirm, revoked connector and worker-path tests |
| Component promotion | Durable visibility plan, public eligibility checks and projection update without object copy | Positive and every-negative-precondition PostgreSQL tests; immutable byte/location/access assertions |
| Repository actions | Durable invite and make-public plans, scoped-token exchange, typed name and reconciliation | Success, refusal, concurrency, timeout/unknown and audit tests; no real repository mutation in local tests |
| Web and CLI | Account Connector UI, RU/EN messages, CLI status/source preparation and publication binding | Generated-client drift, focused component tests, responsive/manual smoke and CLI contract tests |
| Operations | One App settings exist | [Operations runbook](github-connector-operations.md), callback/rotation/rollback procedure and live evidence ledger |

## Ordered implementation packets

Each packet must leave its focused tests green and must not refactor unrelated code.
A model takes one packet at a time and records the exact command and result before
moving to the next packet.

### P0 — restore a green backend baseline

1. Add the `ai-stp:github-request:v1` domain to the foundation digest registry and
   prove the generic registry still rejects unknown domains.
2. Replace the removed CLI `CliPrivateVersionResponse` import with the current
   access-version contract; do not add another response type.
3. Regenerate OpenAPI and generated clients from contract sources; never edit
   generated files by hand.
4. Fix the remaining Pyright unknown types in the connector API tests.
5. Run the focused unit, API and contract tests below on PostgreSQL.

Exit: focused connector/publication tests, Pyright and OpenAPI drift test pass.

### P1 — issue 183 Connector lifecycle

1. Verify state is one-use, expiring and bound to account, session, purpose and the
   linked GitHub subject before token exchange or storage.
2. Verify both consent purposes independently while using one App configuration:
   source reads never mutate; management requires live administration permission.
3. Cover personal install, organization install, pending organization approval,
   selected/unselected repository, suspension, revocation, expiry and disconnect.
4. Add `Cache-Control: no-store` to credential-derived account responses if the
   shared API middleware does not already provide it.
5. Assert browser responses, audit events and logs contain no token or private
   repository coordinates.

Exit: lifecycle and authorization matrix passes with mocked GitHub only at the
external HTTP boundary and real PostgreSQL for persistence.

### P2 — issue 184 private source publication

1. Compare the full immutable publication passport and binding, not only a revision
   string, when reusing an idempotency key.
2. Recheck linked identity, installation, selected repository ID, exact commit and
   contents permission at preparation and confirmation.
3. Exercise ref substitution, rename/ID mismatch, redirect host, traversal, duplicate
   archive members, links, special files, secret-like paths, invalid text, limits,
   missing root and tracked-ignore semantics.
4. Prove the canonical bytes/digest/inventory are the ones stored and published.
5. Prove private coordinates occur only in the server-side binding and never in a
   passport, public projection, error, response or audit payload.

Exit: public-source behavior remains unchanged; private source succeeds only with a
live reader Connector and fails closed after disconnect or revocation.

### P3 — issue 181 immutable component promotion

1. Test owner-only plan creation, digest/device/expiry binding, confirmation replay
   and non-owner refusal.
2. Test every public prerequisite independently: publisher profile, license, tags,
   lifecycle, mandatory validation, safety, artifact integrity and public source
   eligibility. An empty mandatory suite is not a pass.
3. For a bound GitHub source, resolve the exact commit/subpath anonymously and compare
   canonical bytes with the stored artifact before exposure.
4. Assert failure changes neither visibility nor any public projection.
5. Assert success preserves version, passport bytes, provenance, artifact digest,
   object key/bucket and owner/grantee reads while enabling consistent anonymous
   catalog/detail/version/download reads.

Exit: PostgreSQL acceptance tests prove the one-way promotion and idempotent public
replay without an object-store copy.

### P4 — issues 182 and 186 repository management

1. Keep management authority separate from source authority and from component
   grants. The source path must never reach a mutation call, even though both paths
   use the same App credentials.
2. Bind the plan to actor, device, repository ID, owner ID, full name, prior
   visibility, expiry and digest.
3. Require the exact `owner/name` text plus a separate affirmative value; enforce
   both server-side.
4. Immediately before mutation, recheck linked identity, selected installation,
   repository ID/name/owner, current user admin authority and visibility.
5. Cover already-public replay, stale rename, non-admin, organization-policy refusal,
   rate limit, lost response, `unknown` reconciliation and concurrent confirmation.
6. Audit planned/applied/failed/unknown outcomes using opaque target identity only.

Exit: all mutations are mocked at GitHub's HTTP boundary; no local or CI test makes a
real repository public. Live mutation evidence uses a dedicated disposable repository.

### P5 — interface and operations closeout

1. Keep one account surface with two clearly labelled consent actions: source access
   and repository administration. They use one GitHub App; do not describe them as
   GitHub Actions or separate Apps.
2. Test the action form submitter so invite and make-public cannot select each other's
   operation. Cover typed-name, affirmative checkbox, personal-repository write
   warning, error/retry states and RU/EN parity.
3. Verify CLI status and source preparation use the same API authority and never
   accept a pasted GitHub token.
4. Add an operator runbook for one registration, permissions, callback URLs,
   selected repositories, pending approval, credential rotation, disconnect,
   feature disable and rollback. Never include filled secrets.
5. Record live personal and organization installation evidence separately from local
   tests. Record the exact deployed SHA and disposable repository identifiers.

Exit: docs and generated contracts are current; focused UI/CLI checks pass; live
evidence is recorded separately rather than assumed from mocks.

## Verification commands

Use an isolated PostgreSQL database through `AI_STP_TEST_DB_URL`. Do not run heavy
Jest suites for this closeout unless the owner later requests them.

```powershell
uv run --locked python -m pytest tests/unit/platform/test_github_connector.py -v --no-cov
uv run --locked python -m pytest tests/api/platform/test_github_connector.py tests/api/platform/test_publication_grants_reports.py -v --no-cov
uv run --locked python -m pytest tests/contract/test_openapi.py -v --no-cov
just docs-check
just back-static
just back-test
```

Run focused web type, component and browser checks through the repository's existing
`bun` recipes after P5; do not introduce a second test runner. Before final delivery,
inspect `just --show check`, run every applicable non-heavy gate, and review the exact
diff for unrelated or generated-only churn.

## Current status and completion rule

The implementation and local evidence are complete: one-App settings, connector
lifecycle, private-source binding, visibility promotion, repository action plans,
CLI/Web surfaces, generated contracts, fixture corpus and operator runbook are in
place. Docker/PostgreSQL-backed API tests, the full backend suite, static/docs gates,
web build/type/lint and i18n checks are the executable local evidence. Only live
GitHub installation/organization-approval/mutation evidence remains external to this
checkout; it must use a disposable repository and the exact deployed SHA.

An issue is done only when its SPEC-072 row has executable evidence on one SHA.
Mocks can prove deterministic error handling but cannot prove installation approval,
organization policy or a real GitHub mutation. Do not close issue 182 until the
component issues in its umbrella scope are either complete or explicitly split.
