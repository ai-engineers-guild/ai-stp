---
description: "SPEC-027: Web UI for owned objects, publication, rights, reports, and minimal moderation."
last_verified: "2026-08-08"
---

# SPEC-027: Web UI for owned objects, publication, rights, reports, and moderation

## Purpose

`apps/web` gives an account owner a safe authenticated surface for viewing
synchronized owned objects and their versions, confirming a server publication
plan, managing invitations and rights, and creating and tracking their own
reports; it gives platform staff a surface for minimal triage and audited
actions. Web displays server truth and invokes shared `/v1` scenarios; it does
not create a passport, index a project, compile a setup, run a check, or install
an object.

Server rules for publication, grants, reports, and staff belong to `SPEC-002`,
`SPEC-007`, `SPEC-016`, `SPEC-026`, and their contracts. This specification owns
web-client behavior and the `REQ-27xx` requirements.

## Scope

Included are protected pages for owned objects and exact versions; display of
publication-plan state and confirmation of the exact plan; owned invitations
and grants, including creation, acceptance, and revocation; report creation with
preview and a list of the user's own cases; a minimal staff worklist, triage,
lifecycle actions, and granting or revoking `author_verified`; bilingual UI,
accessibility, typed-error handling, protection of private data, and display of
operation identifiers.

Excluded are browser creation or modification of passports, arbitrary artifact
uploads, indexing, matching, compilation, checks, installation, forking,
synchronization as a client process, full RBAC, organizations, payments, public
discussion, automatic blocking based on report count, remote disabling of a
target, a setup editor, a separate BFF, and handwritten DTOs. Web does not show
a full device passport, secrets, a raw invitation token, raw attestations,
private bytes, or the reporter's identity outside the authorized staff surface.

Exact fields, parameters, routes, and response codes belong to
`packages/contracts` and generated `schemas/v1/openapi.json`; header, cursor,
idempotency, and concurrency semantics belong to `docs/contracts/http-api.md`.
Additional authenticated owner/staff read models required by this surface are
first introduced additively in the contract and API, after which the client is
regenerated. Web does not obtain them by assembling private state from `sync`
events, the public catalog, or a client store.

## Terms

- **Owner workspace** — the authenticated web surface for the current account,
  not the public catalog projection.
- **Owner read model** — a bounded server-side projection of owned objects,
  versions, and their available actions; it is not a passport and does not grant
  write access to an object.
- **Publication review** — display of an immutable `PublicationPlan`, its digest,
  effects, evidence, expiry, and state before separate confirmation.
- **Grant inbox** — the list of invitations and grants available to the current
  account under server authorization; it does not disclose the existence of
  other accounts.
- **Staff worklist** — the minimal authorized projection of pending cases and
  their context for an account in the server-side allowlist; it is not a client
  role.

## Requirements

### Access and reading owned objects

- `REQ-2701`: Every owner-workspace and staff-worklist route reads the server
  session before rendering. An unauthenticated user is redirected without
  including private data in HTML, the RSC payload, or the client bundle; client
  state is not proof of authority.
- `REQ-2702`: The owner workspace displays only the server-authorized owner read
  model for the current account: its own private/public drafts, objects, and
  exact versions. Receiving a grant does not make a user the owner or permit
  writing to the original. Pagination and ordering follow the opaque cursor API.
- `REQ-2703`: The card for an owned exact version displays available server facts
  about lifecycle, exact digest, publication, the two independent
  `author_verified` / `component_verified` axes, eligibility for new
  installations, and evidence. It distinguishes platform execution from
  `author_attested`, does not call a warning success, and does not infer safety
  from author verification.
- `REQ-2704`: For absence, hiding, grant revocation, or insufficient authority,
  web displays the single safe `not found` / permission denied result defined by
  the API, without disclosing the existence of another user's private object,
  case, or staff worklist. It does not replace the denial with data from an old
  client cache.

### Publication and its state

- `REQ-2705`: Publication review may begin only for an exact server-authorized
  version prepared by the CLI and available through the owner read model. Web
  sends only the contractual intent to the shared publication scenario and does
  not create, repair, or sign a passport, digest, evidence, or attestation.
- `REQ-2706`: Before confirm, web displays the `PublicationPlan`'s `plan_hash`,
  exact object/version/digest, policy version, effects, expiry, state, and
  available evidence. Confirmation requires an explicit user action; hidden
  submission during navigation, re-rendering, or automatic retry is prohibited.
- `REQ-2707`: Confirm sends a new idempotency key for one logical user action and
  reuses it only after an indeterminate transport result. Web displays the
  server-returned `operation_id` where provided but does not generate or
  simulate a successful result.
- `REQ-2708`: After confirm, publication remains in observable server state. Web
  rereads the plan through bounded waiting or explicit refresh and accurately
  displays `validating`, `publish_planned`, `published`, `failed`, `stale`,
  expiry, and cancellation. The client does not declare published before the
  server response or start a validation/publish job itself.
- `REQ-2709`: A `stale` or expired plan, changed digest, invalid evidence, or
  idempotency conflict requires a new or reread server plan. Web retains safe
  selection context for another review but does not carry prior consent to a
  different `plan_hash`.
- `REQ-2710`: Web clearly explains lifecycle and evidence consequences: loss of
  install eligibility blocks only new installations and updates and does not
  remotely disable an installed target. Only a server-side staff action may
  change `blocked` / `hidden` / restore; the publication button is not such an
  action.
- `REQ-2711`: Public and owner cards use one generated typed client and server
  read models. A page does not add separate visibility, trust, or eligibility
  policy and does not read an object-store key.

### Invitations and rights

- `REQ-2712`: An owner sees their invitations and grants in a server-authorized
  list with the object, major line, state, and permitted actions. Invitation
  creation uses a normalized email only as API input; the web UI does not add
  diagnostics, hints, or distinguishing timing to the identical success for a
  registered and unregistered address.
- `REQ-2713`: Creating and revoking an invitation and revoking a grant require
  explicit confirmation, a reason only in the permitted form, and an
  idempotency key. Before revocation, web states that bytes already obtained,
  local forks, and installed targets are not deleted; after success it updates
  the view from the server response, not an optimistic guess.
- `REQ-2714`: Invitation acceptance is available only to the authenticated
  recipient. The `Raw token` lives briefly in page memory and is sent only in a
  protected POST to the shared API; it is not placed in the path, query
  parameters, server HTML, `referrer`, logs, analytics, notifications,
  `audit payload`, browser storage, or history. Before `accept`, the invitation
  is not displayed as a grant and does not open the object.
- `REQ-2715`: The Web UI does not allow the recipient to modify the original
  object, grant a right to a third party, or treat a grant as access to the next
  major line. Acceptance, expiry, revocation, an unverified email, and a foreign
  token are displayed only through a typed safe API response.

### Reports and minimal moderation

- `REQ-2716`: A report from a public or owner version page creates the same
  `ReportCase` scenario as the CLI. The exact object/version/digest comes from
  the displayed server version; web does not accept an arbitrary object id as
  proof of access and does not create a public GitHub issue.
- `REQ-2717`: If the user adds diagnostics, the form limits them to the
  contractual size, redacts available paths to relative paths, displays a full
  preview of what will be sent, and requires separate consent after preview.
  Secrets, `.env`, source code, private bytes, OAuth/session/invitation tokens,
  and full home paths are not inserted automatically; the text is not stored in
  persistent browser storage.
- `REQ-2718`: After submit, web displays only the user's own `ReportCase` and its
  permitted state. A retry with the same idempotency key displays the same case;
  rate limiting, unavailability, and an indeterminate transport result do not
  create false success. A prepared but unsent form remains available in memory
  on the current screen until explicit cancellation or navigation away.
- `REQ-2719`: The staff worklist and case detail render only after server-side
  allowlist authorization. Presence or absence of staff navigation is not
  authority: `403` is not replaced by a client-side role, and non-staff receive
  no case count, identifiers, or contents.
- `REQ-2720`: Staff triage, lifecycle action (`block`, `hide`, `restore`), and
  granting or revoking `author_verified` require explicit confirmation, a
  non-empty reason, and a new idempotency key. The screen displays the
  server-returned result and `operation_id` / request id for audit verification;
  report count never suggests or initiates automatic blocking.
- `REQ-2721`: The staff view does not disclose the reporter's identity, email,
  diagnostics, or environment to the object author. `security_escalated` does
  not enter ordinary lists or disclose vulnerability details; web directs the
  user to a safe server-defined outcome without creating a public discussion.

### Web-client quality and compatibility

- `REQ-2722`: All new user-facing strings have equivalent `ru` and `en`
  messages. Forms, tabs, dialogs, waiting states, and errors are keyboard
  accessible, have visible focus and correct labels/roles, and announce state
  changes to assistive technologies.
- `REQ-2723`: Mutations are implemented as Server Actions with the CSRF
  transport from `ADR-0041` and update the RSC view from server truth. The sole
  transport exception is invitation `accept` under `REQ-2714`: a client
  component reads the token from the URL fragment and sends it in a direct
  same-origin POST with double-submit CSRF, without implementing a business rule
  in the browser.
- `REQ-2724`: The client uses only code generated from the current OpenAPI and
  thin boundary adapters without handwritten DTOs. A new field is first added
  as optional; an unsupported schema, unknown response field, and API/version
  mismatch are handled under the contract without an unsafe cast or hidden
  fallback.
- `REQ-2725`: Unit, component, contract, and browser tests cover the
  owner/grantee/outsider/staff matrix, all publication-plan states, the
  invitation fragment, data redaction, report preview, staff confirmation,
  locale parity, and a11y. Tests use no real OAuth, Resend, object storage, or
  browser secrets and record no tokens, emails, or private bytes in snapshots,
  traces, or fixtures.

## States and errors

The `publication plan`, `validation`, `invitation`, `grant`, `case`, and
`lifecycle` states belong to `packages/contracts`, `SPEC-002`, `SPEC-007`,
`SPEC-016`, and `SPEC-026`. Web displays them as server-provided values and does
not invent local transitions. `AI_STP_AUTH_REQUIRED` moves a protected screen to
logout; `AI_STP_DEVICE_REVOKED` prevents mutation of publication paths;
`AI_STP_PERMISSION_DENIED` and `AI_STP_NOT_FOUND` do not disclose a private
resource; `AI_STP_PLAN_STALE`, `AI_STP_PRECONDITION_FAILED`, `AI_STP_CONFLICT`,
`AI_STP_RATE_LIMITED`, and `AI_STP_DEPENDENCY_UNAVAILABLE` have distinct
observable messages and retry actions. Secret values do not enter the displayed
error.

## Security and privacy

`Server session`, API authorization, CSRF, and `transport cookie` are inherited
from `ADR-0041`; web stores no provider token or session token. Private RSC data
is not serialized into client props unless needed, and the protected view is
invalidated after logout, revocation, or an authority denial. Publication,
grant, report, and staff actions use server-issued IDs and idempotency; a raw
invitation token, attestation signature, secrets, emails outside the permitted
form, and private bytes do not enter URLs, browser storage, telemetry, logs,
audit, or localized messages.

## Compatibility and migration

Before owner/staff screens are implemented, the contract receives additive read
models and corresponding fixtures/OpenAPI. Existing public-catalog and CLI
clients remain compatible; private fields are not added to anonymous responses.
After the contract is updated, `api:generate` is run; the generated client is not
edited manually. If the server does not yet support the required read model, web
shows only explicit feature unavailability and does not substitute sync data.

## Acceptance criteria

| Requirement | Executable verification |
| --- | --- |
| `REQ-2701` | An RSC/browser test verifies redirect without protected HTML or client payload. |
| `REQ-2702` | A contract/API/browser matrix separates owner, grantee, and outsider in list/detail. |
| `REQ-2703` | A component golden distinguishes both verification axes, evidence source, and eligibility. |
| `REQ-2704` | A negative test does not disclose a private object/case through a route, cursor, or cache. |
| `REQ-2705` | A contract test rejects publication intent not formed from an owner version. |
| `REQ-2706` | A browser test requires explicit confirm after displaying digest, effects, and expiry. |
| `REQ-2707` | A lost-response test repeats one key and displays one server operation. |
| `REQ-2708` | A mock/API scenario covers every terminal and transitional plan state. |
| `REQ-2709` | A stale-plan test requires a fresh plan and does not carry prior consent. |
| `REQ-2710` | A UI test distinguishes an eligibility warning from a staff lifecycle action. |
| `REQ-2711` | A static/contract test excludes handwritten trust policy and storage-key access. |
| `REQ-2712` | Known/unknown email tests have indistinguishable web-visible results and timing budgets. |
| `REQ-2713` | Dialog and API tests verify the warning and server-truth refresh after revoke. |
| `REQ-2714` | A browser trace/history/source test finds the token nowhere outside the fragment and POST body. |
| `REQ-2715` | The authz matrix prohibits re-granting, writing to the original, and next-major access. |
| `REQ-2716` | A contract test proves the shared web/CLI report scenario without a GitHub issue. |
| `REQ-2717` | A form test requires preview/consent and finds no sensitive fixture text in storage. |
| `REQ-2718` | A retry/rate-limit test retains the draft in memory and does not display false success. |
| `REQ-2719` | A non-staff browser/API test receives no staff-route data, count, or case ID. |
| `REQ-2720` | The staff scenario requires reason/confirm and checks the audit correlation identifier. |
| `REQ-2721` | A redaction test hides reporter data and security-case details from the author/list. |
| `REQ-2722` | Locale and axe tests cover every route, form, and dialog in `ru` and `en`. |
| `REQ-2723` | An architecture test verifies Server Actions and the fragment-only accept exception. |
| `REQ-2724` | The generated-client gate and typecheck reject manual DTO/unsafe-cast drift. |
| `REQ-2725` | The CI inventory links every requirement to deterministic web/API test evidence. |
