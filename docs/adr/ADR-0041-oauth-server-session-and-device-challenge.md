---
description: "Decision on the OAuth sign-in mechanism, server-side session form, and Ed25519 device authentication."
last_verified: "2026-08-06"
---

# ADR-0041: OAuth Mechanism, Server-Side Session, and Device Challenge

Status: accepted.

## Context

`#80` implements the authenticated account and device path for the web and CLI. `SPEC-002` (`REQ-201..207`, `REQ-213..215`) and `SPEC-010` (`REQ-1002`, `REQ-1003`, `REQ-1005`, `REQ-1010`) establish the requirements: separate `Account` and `OAuthIdentity`, secure linking by verified email without silent merging, revocation, a server-side session, and devices with a stable ID and Ed25519 key pair. The storage schema for `account`, `oauth_identity`, `device`, `session`, and `audit_event` was already created in `#79`; the vertical-slice skeleton and shared core were created in `#78` under `ADR-0037`.

The requirements describe *what* the system does, but do not establish the *mechanism*. None of the accepted ADRs selects an OAuth library, the form of the application session (an opaque server-side record versus a stateless token), or the device authentication method. Without such a decision, the `auth` and `devices` slices would diverge into incompatible implementations. The `#80` acceptance criteria emphasize immediate revocation, replay safety, and keeping token values out of logs, audit records, and server errors visible to the browser, which directly affects the choice of mechanism.

## Options

Application session form:

1. Opaque server-side session. A `session` row with `FK account_id`, `FK device_id`, and an expiration time; the client holds an opaque identifier. Immediate revocation through a record or flag, simple logout, a natural connection to device revocation, and a value that carries no data and is not a claim in logs. The cost is a session read on every request, mitigated by an index and a short TTL.
2. JWT access + refresh. Stateless validation without a database lookup, but revocation requires a denylist, which brings state back to the server and complicates replay safety and observable logout. It fits the `#80` revocation criteria less well.

OAuth library:

1. Authlib `StarletteIntegration`. Supports Google and GitHub, PKCE `S256`, `state` protection under `RFC 6749 §10.12`, and is actively maintained. Requires version `>= 1.6.6`, which fixes CSRF when `state` is stored in a cache without being bound to the initiating session.
2. A custom flow using `httpx`. Provides more control, but independently implementing `state`, PKCE, and `nonce` increases security risk without a concrete benefit.

Device authentication:

1. Ed25519 challenge-response. The server issues a one-time `nonce`, the device signs it with its private key, and the server verifies it with the public key. The private key never leaves protected local storage.
2. A server-side secret or device API key. Requires storing a secret on the server and aligns less well with the privacy requirements of `SPEC-002`.

## Decision

An opaque server-side session, Authlib `StarletteIntegration`, and Ed25519 challenge-response are accepted.

Libraries (exact versions are pinned in the lockfile; additions follow `dependency-policy.md`):

- `authlib>=1.6.6` - OAuth and OpenID Connect client for Google and GitHub through `StarletteIntegration`, with PKCE `S256` and `state` protection under `RFC 6749 §10.12`; version `>= 1.6.6` fixes CSRF when `state` is cached without being bound to the session.
- `cryptography` - verifies the device's Ed25519 signature (`ed25519.Ed25519PublicKey`); the server only verifies, and the private key is not sent to the server.
- `itsdangerous` - signs the transient handshake cookie (`SessionMiddleware`) and the stateless device challenge; it is already required by Starlette's `SessionMiddleware`.

Session and token form:

- Application authentication uses an opaque server-side session in the `account_session` table (already created in `#79`). The client receives a raw `secrets.token_urlsafe` token; the server stores only `sha256(token)` as the row's primary key. The raw token is not stored in the database, so a database leak does not expose active sessions. The schema does not change.
- Request validation performs a single indexed lookup by primary key; logout and revocation set `revoked_at`; reuse of an old token is rejected. JWT is not used in the MVP.
- The session-validation dependency is encapsulated in the shared core and allows a cache to be substituted transparently (Redis is outside the MVP under `SPEC-010`) without changing the contract.

Transport (one scenario under `SPEC-010` `REQ-1011`, differing only at the boundary):

- The CLI sends the token in the `Authorization: Bearer` header and stores it in protected local OS storage.
- The web receives the token in an `HttpOnly; Secure; SameSite=Lax` cookie and sends a double-submit CSRF token in a header for unsafe methods; this is the only web-specific hardening and the documented security rationale for `REQ-1011`, not a separate route.

Device and handshake:

- Transient OAuth state (`state`, `code_verifier`, `nonce`, `redirect_uri`) lives in a signed cookie and is separate from the application session.
- The device challenge is stateless: the server issues an `itsdangerous`-signed `nonce` with a TTL, the device signs it with its private key, and the server verifies freshness and the Ed25519 signature. A separate challenge table and its cleanup are unnecessary.
- Registration is idempotent by the `(account_id, public key)` pair (the constraint already exists in the schema) and does not bind a key to another account without authorization; revocation sets `device.state` and the associated `account_session.revoked_at` without deleting local data.
- OAuth token, session, and `nonce` values do not enter YAML, logs, traces, metrics, audit payloads, or server errors visible to the browser.

## Consequences

- New dependencies are introduced: `authlib>=1.6.6`, `cryptography`, and `itsdangerous`; none is present in the current lockfile, while Starlette's `SessionMiddleware` requires `itsdangerous` anyway. Adding them requires entries in `docs/engineering/dependency-policy.md` and `docs/engineering/tech-stack.md` before implementation.
- The session form requires no migration: it uses the existing `account_session`, where `id` becomes the `sha256` of the raw token; changing the token form in the future does not break the schema.
- The `auth` and `devices` slices in `apps/api` follow `ADR-0037`; the shared core gains a session-validation dependency shared by the slices.
- The `secret_key` for `SessionMiddleware` comes from the environment and is not a secret embedded in code.
- Device revocation closes cloud sessions transitively; local and offline data are not affected (`SPEC-002` `REQ-205`, `REQ-207`).
- Required tests: OAuth callback, linking and conflict, replay, CSRF/`state`/PKCE validation, device idempotency and revocation, and log and audit redaction.
- Rollback: the session mechanism is encapsulated in the shared core; switching to signed tokens requires a new ADR and is not performed in place.

## Reconsideration Conditions

The decision will be reconsidered if stateless scaling across multiple regions without a shared session database becomes a requirement, or if a demonstrated need for inter-service token delegation arises; signed tokens with a denylist and separate rotation would then be considered.
