---
description: "SPEC-002: Accounts, OAuth, devices, and access."
last_verified: "2026-08-13"
---

# SPEC-002: Accounts, OAuth, Devices, and Access

## Purpose

The user securely links Google and GitHub identities, manages devices and their passports, and grants access to private objects without treating an account ID as a secret or authority.

## Scope

The scope includes the internal account, OAuth identities, device keys, device revocation, the device passport and its summary, `AccessGrant`, `GrantInvitation`, administrative authority, and auditing. Payment permissions, enterprise SSO, recipient-free link access, and automatic merging of populated accounts are out of scope.

## Terms

- `Account` — the platform's internal identity.
- `OAuthIdentity` — one verified Google or GitHub login.
- `Device` — a CLI installation with a distinct identifier and Ed25519 key pair.
- `DevicePassport` — a private, revisioned passport for one device's environment under `ADR-0025`; the closed set of fields and summary fields belongs to `docs/contracts/device-passport.md`.
- `AccessGrant` — a distinct server-side permission for an object or major line.
- `GrantInvitation` — an offer of access addressed to a normalized email address before a permission exists.

## Requirements

- `REQ-201`: The internal `Account` is separate from `OAuthIdentity`.
- `REQ-202`: A new OAuth identity with the same verified email may be linked to an existing account, but two accounts containing their own data are not merged silently.
- `REQ-203`: An identity with a different email is linked only from an already authorized account after renewed confirmation.
- `REQ-204`: Each device has a stable ID, Ed25519 public key, last-active timestamp, and revocation state.
- `REQ-205`: A revoked device cannot submit accepted sync events or attestations, but retains local read access.
- `REQ-206`: A private object is accessible to its owner, the recipient of an active `AccessGrant`, and an administrator subject to mandatory auditing.
- `REQ-207`: A user can revoke the current device; resuming cloud access requires a new sign-in and a new key.
- `REQ-208`: The owner can invite a recipient by normalized email address; an invitation is not an access permission and grants no read access before acceptance.
- `REQ-209`: The response to invitation creation is the same whether or not the address is registered.
- `REQ-210`: An invitation becomes an `AccessGrant` only after an account signs in with the same provider-verified address; matching the string without provider verification is insufficient.
- `REQ-211`: An invitation key is single-use and expires, while conversion into a permission is atomic and idempotent by key.
- `REQ-212`: The owner revokes an invitation and a granted permission separately; revocation does not delete bytes already received by the recipient, and the owner is informed of this.
- `REQ-213`: Each device maintains its own revisioned device passport of kind `device`; its observed OS, architecture, installed harnesses, and tool versions belong to it, not to the developer passport.
- `REQ-214`: Only the permitted summary from the closed set in `docs/contracts/device-passport.md` leaves the device; absolute user paths and environment variable values are excluded from a summary revision.
- `REQ-215`: The server stores each device's summary separately; device passports are not merged into a single cross-device environment, and revoking a device marks its summary as revoked without deleting the local passport.
- `REQ-216`: A permission addresses an exact object and one major line `X`: the recipient can read and install existing and future minor versions within `X`, while a new major line requires a new permission.
- `REQ-217`: A permission grants read, install, and fork capabilities; editing the original and granting the permission again remain exclusive to the owner, and a recipient's write to another owner's object is rejected.
- `REQ-218`: Revoking a permission stops future cloud reads and receipt of minor versions, but does not delete bytes already received, local forks, or installed targets; rebuilding with an inaccessible private dependency fails with a precise typed access error.
- `REQ-219`: Signing out ends both halves of the session: the client revokes it on the server and forgets the credentials locally. The local half completes even without a network connection, while an incomplete server-side revocation is returned as a warning in the envelope rather than as an exit code.

## States and errors

An OAuth link has the states `pending`, `linked`, `conflict`, and `revoked`. A Device has `active` and `revoked`. An invitation has the states `pending`, `accepted`, `expired`, and `revoked`. Errors distinguish an unverified email, an occupied provider identity, a conflict between two populated accounts, an expired session, a revoked device, and an expired or already-used invitation.

## Security and privacy

The device private key is stored only in secure local storage and is not synchronized. OAuth tokens and the invitation key do not appear in YAML, logs, traces, metrics, or Agent output. Knowledge of an account identifier or email address does not constitute authority. Administrative reads require a reason and create an immutable `AuditEvent`.

## Compatibility and migration

`Account` remains stable when an OAuth provider is added or removed. Changing the device key format requires parallel reads of the old and new formats, separate rotation, and the ability to revoke without deleting local data.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-201` | A model and migration test confirm the many-to-one relationship without storing the provider ID as the account ID. |
| `REQ-202` | An integration test covers a same-email link and blocks a silent merge of two populated accounts. |
| `REQ-203` | An auth test requires an active session and step-up confirmation for an identity with a different email. |
| `REQ-204` | A device registration test verifies the ID, public key, timestamps, and uniqueness. |
| `REQ-205` | A revocation test rejects sync/attestation and preserves offline read access. |
| `REQ-206` | An authorization matrix covers owner, grantee, outsider, and audited admin. |
| `REQ-207` | A test that revokes the current device requires a new login for the next cloud request. |
| `REQ-208` | An unaccepted invitation grants no read access to the private object. |
| `REQ-209` | Responses for known and unknown addresses are indistinguishable in body, code, and timing. |
| `REQ-210` | Signing in with a different verified address or with an unverified address does not create a permission. |
| `REQ-211` | Reusing a key returns the same permission, while expired and used keys produce typed errors. |
| `REQ-212` | Invitation revocation and permission revocation are verified independently, and the key does not appear in logs. |
| `REQ-213` | A two-device fixture stores different environments in two device passports and does not change the developer passport. |
| `REQ-214` | The synchronized summary rejects a field outside the closed set, an absolute path, and an environment variable value. |
| `REQ-215` | The summaries of two devices are read separately, no merged representation exists, and revocation marks the summary without deleting local data. |
| `REQ-216` | A permission fixture for `X.1` reads `X.2` and rejects `X+1.0` without a new permission. |
| `REQ-217` | An authority matrix permits the recipient to read, install, and fork, and rejects writes to the original and delegation of the permission. |
| `REQ-218` | After revocation, a fixture preserves local bytes, the fork, and the target, while rebuilding with a private dependency returns a typed access error containing the object name. |
| `REQ-219` | A logout test observes exactly one `POST /v1/auth/logout` with the held token; an unreachable server leaves a warning and a zero exit code after credentials are cleared, while an already invalid session produces no warning. |
