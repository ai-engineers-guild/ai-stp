---
description: "SPEC-023: Web login, account profile and device management."
last_verified: "2026-08-17"
---

# SPEC-023: Web login, account and device profile

## Purpose

`apps/web` provides the authenticated Sprint-1 vertical slice: login and
logout via Google and GitHub on top of the shared OAuth API; viewing the account profile and
editing the minimum public profile and privacy fields allowed
canonical contract; a device list containing only the permitted summary; revoking
devices with explicit acknowledgment, stale state handling, and secure
feedback; distinguish between current session and device; protection of authenticated
routes and session expiration processing. Publication, synchronization, rights, complaints and
administration is not included in this section.

Wire contract frozen `#71`; OAuth mechanism, server session form and
device authentication belong to `ADR-0041`; stack and client spawning -
`ADR-0043`; ownership of interfaces and prohibition of second business logic - `ADR-0018`,
`SPEC-010` `REQ-1011`, `REQ-1012`; allowed device summary -
`SPEC-010` `REQ-1013` and `docs/contracts/device-passport.md`; public profile fields -
`docs/contracts/public-profile.md`; domain requirements of the account, device and
access - `SPEC-002`; header, idempotency and competition rules -
`docs/contracts/http-api.md`. This specification describes the behavior of the web behind
contract and owns the requirements of `REQ-23xx`.

## Scope

Includes: Google and GitHub login and logout UX on top of the shared OAuth API `#80`;
viewing your account profile and editing allowed public profile fields and
privacy; list of devices only with allowed summary; confirmation of new
CLI devices using a one-time code without revoking already active devices; device revocation with
confirmation, processing of obsolete `ETag`/revisions and secure feedback;
distinguish between current session and device; protecting authenticated routes and
session expiration processing; displaying action result identifiers where
they are issued by the API; parity `ru`/`en` and accessible forms and dialogs.

Not included: drafts, publishing, sync status, rights and invitations,
complaints and moderation; full display of the device passport; creation and editing
passports, project indexing and composition assembly in the browser; OAuth mechanism and sessions
(`ADR-0041`); linking identity and authority decisions (server, `SPEC-002`); wire-
circuits and `schemas/**` (`#71`).

## Terms

- `Login UX` - Google and GitHub two-way login flow on top of the `#80` OAuth API with
  equivalent behavior after login; the mechanism itself is `ADR-0041`.
- `Account profile view` - view the account and edit only those fields
  public profile and privacy, as permitted by the canonical contract.
- `Device summary` - closed resolved device summary from
  `docs/contracts/device-passport.md`: name, OS and architecture, harnesses with versions,
  tool profile version, last update time; full passport not
  is shown.
- `Revoke` - device revocation with explicit confirmation, `If-Match` according to `ETag`/revision and
  updating the view from server truth.
- `Current device/session` — device and session of the current request; revoking either
  produces an explicit logged-out state.
- `Protected route` is an authenticated route that redirects without leaking
  protected data for an unauthenticated user.

## Requirements

- `REQ-2301`: Unauthenticated user on a secure route
  redirected without disclosing protected data; protection reads the server session, and
  not just the client state; the assumption of permissions on the client is not
  provides access.
- `REQ-2302`: Login via Google and GitHub have equivalent behavior after login;
  the thread handles success, error, and provider cancellation with observable states;
  OAuth mechanism, `state`, PKCE and session belong to `ADR-0041` and are not implemented by the web
  again.
- `REQ-2303`: Account profile, public profile and web privacy fields exactly
  comply with the contract (`docs/contracts/public-profile.md` and
  `identity-account-profile` to `/v1`). The privacy page shows current
  `show_profile_publicly` and `allow_publisher_listing`, saves them only explicitly
  button via `PUT /v1/account/privacy` with double-submit CSRF and after success
  displays the status confirmed by the server. Public profile is edited
  via additive routes `SPEC-028`; Links are accepted only over HTTPS.
- `REQ-2304`: Device page shows only allowed summary from
  `docs/contracts/device-passport.md` (`REQ-1013`); full device passport,
  absolute paths, environment values, and private keys are neither rendered nor
  requested.
- `REQ-2305`: Device revocation requires explicit confirmation, uses `If-Match` by
  `ETag`/revision and updates the view from the server truth, not optimistically; outdated
  precondition and competitive change are different (`AI_STP_PRECONDITION_FAILED` and
  `AI_STP_CONFLICT`) and are processed by re-reading or explicit decision.
- `REQ-2306`: Revoking the current device or session gives an explicit logged-out state;
  the web distinguishes the current device and session from others and does not show
  valid revoked current context.
- `REQ-2307`: Browser storage does not contain long-lived provider tokens;
  web session is transferred `HttpOnly; Secure; SameSite=Lax` cookie, and insecure
  methods carry double-submit CSRF token by `ADR-0041`; token and session values are not
  end up in client code, browser logs and visible errors.
- `REQ-2308`: Session expiration or withdrawal is handled by an observable transition to
  exit status on next protected request; web doesn't continue to show
  Protected data from an outdated client session.
- `REQ-2309`: Action result identifier (`operation_id`/`X-Operation-Id`)
  displayed where the API issues it for user audit; the web doesn't make things up
  ID and does not show secrets in feedback.
- `REQ-2310`: Authenticated routes and `apps/web` components do not implement the second
  business logic: identity binding, permission decisions and recording are left to the API
  through the general script (`ADR-0018`, `REQ-1011`, `REQ-1012`); separate web route
  permitted only with a recorded safety reason (transport `ADR-0041`).
- `REQ-2311`: Russian and English locales provide equivalent information and behavior on
  authenticated surface; forms and dialogs are accessible from the keyboard and have a visible
  focus, correct roles and signatures and declare errors to assistive technologies.
- `REQ-2312`: One account supports several simultaneously active devices.
  The `/devices` page shows all linked devices and a confirmation form
  another one-time CLI code; successful pairing of a new device does not revoke and
  does not replace already active devices. Confirmation uses server script
  `POST /v1/auth/device/approve`, and the web does not implement its own linking logic.
- `REQ-2313`: Repeated OAuth login from the same browser profile reuses
  its active browser-device identity and creates a new session, not a new line
  devices. The browser device ID is stored separately from the session
  token in a long-lived `HttpOnly; Secure; SameSite=Lax` cookie, checked by account and status;
  a missing, foreign or revoked identity is replaced with a new one.
- `REQ-2314`: A browser device is labelled from its stored user agent with a safe
  generic fallback. The edge proxy replaces the client-address header passed to the API,
  which resolves approximate city and country against a local MMDB file. The
  platform stores neither the source IP nor precise coordinates and login remains
  available when the database is absent or unreadable. The web attributes the
  installed data source wherever it displays a resolved location.

## States and errors

Authenticated read succeeds with resource body, state
`AI_STP_AUTH_REQUIRED` for a missing or expired session (observed transition to
exit), state `AI_STP_PERMISSION_DENIED` with insufficient rights,
`AI_STP_PRECONDITION_FAILED` for a stale revocation `ETag` and `AI_STP_CONFLICT` for
competitive change. Feedback distinguishes between these two outcomes and behaves differently:
an obsolete precondition requires re-reading and repeating, a conflict requires an explicit
resolution. `AI_STP_DEVICE_REVOKED` for the revoked device returns `403`. Every response
carries `X-Request-Id`; changing operation - `operation_id`. Secrets and meanings of tokens
there are no errors.

## Security and privacy

Web does not render full device passport: private summary is limited to private
list `docs/contracts/device-passport.md`; absolute paths, environment values and
private keys are not issued by either the API or the web (`REQ-1013`). Long-lived tokens
providers are not saved in browser storage; the session is transferred by a protected cookie
by `ADR-0041`. No client permission assumption grants access:
the final rule checks the server by object and action (`REQ-1003`). Protected
data is not rendered to an unauthenticated user and does not remain visible to
outdated session. The values of OAuth tokens, sessions and `nonce` are not included in the client
code, browser logs, traces and visible errors (`ADR-0041`).

## Compatibility and migration

The `#71` contract is changed only additively and only by `#71` itself; profile fields,
privacy and device summaries are taken from the contract, and the discrepancy between prose and contract
is decided in favor of the contract. Session transport and CSRF are inherited from `ADR-0041` without
changes. The device's allowed summary only changes with
`docs/contracts/device-passport.md` and `SPEC-002`. The generated client is rebuilt
in case of additive change of the contract; manual DTO dialing is not entered.

## Acceptance criteria

| Requirement | Executable verification method                                                                                                                                                                                                                                                  |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `REQ-2301`  | The test confirms redirecting an unauthenticated user without leaking protected data and reading the server session.                                                                                                                                                            |
| `REQ-2302`  | Login tests cover Google and GitHub success, error, and cancellation and equivalent post-login behavior.                                                                                                                                                                        |
| `REQ-2303`  | The test confirms the exact compliance of the profile, public profile and privacy fields with the contract and the acceptance of links only via HTTPS.                                                                                                                          |
| `REQ-2304`  | The Golden test of the device response confirms only the allowed summary fields and the absence of the full passport, paths, environment values ​​and keys.                                                                                                                     |
| `REQ-2305`  | The revocation tests cover confirmation, obsolete `ETag` (`412`) and conflict (`409`) and view update from server truth.                                                                                                                                                        |
| `REQ-2306`  | The test confirms the explicit logged-out state when revoking the current device or session and distinguishes the current context.                                                                                                                                              |
| `REQ-2307`  | The storage inspection test confirms the absence of long-lived provider tokens and the transfer of the protected cookie session.                                                                                                                                                |
| `REQ-2308`  | The test confirms the transition to the exit state for an expired or revoked session and the lack of display of protected data for an expired session.                                                                                                                          |
| `REQ-2309`  | The test confirms that the `operation_id` displays where the API outputs it and that there are no secrets in the feedback.                                                                                                                                                      |
| `REQ-2310`  | Contract and negative checks confirm the absence of second business logic and recording through an inaccessible CLI web handler.                                                                                                                                                |
| `REQ-2311`  | Checks for locale parity and accessibility of forms and dialogs pass; browser smoke of login and revocation passes; `mobile-public-smoke.spec.ts` passes login and account basics at 360 and 430 px in `ru` and `en` without document-level overflow, if the fixtures allow it. |
| `REQ-2312`  | The Browser script shows two active devices, confirms the new CLI code on `/devices` and does not hide already linked devices; The API script confirms the independence of multiple account devices.                                                                            |
| `REQ-2313`  | The API script executes two browser OAuth callbacks with one device cookie, receives two different sessions and exactly one active browser-device line.                                                                                                                         |
| `REQ-2314`  | Unit and API tests cover browser/device labelling, edge-provided city and country, the generic fallback, and absence of an IP field.                                                                                                                                            |

Browser scripts `apps/web/tests/e2e/` close the executable layer for `REQ-2303` /
`REQ-2309` (`account-profile.spec.ts`) and `REQ-2311` / `REQ-2312`
(`locale-parity.spec.ts`, `login-devices.spec.ts`, `mobile-public-smoke.spec.ts`).
