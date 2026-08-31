---
description: "Decision to store the device key and cloud credentials in tiers with mandatory tier naming."
last_verified: "2026-08-06"
---

# ADR-0058: Device Key and Credential Storage

Status: accepted.

## Context

`SPEC-002` REQ-204 requires every device to have a stable identifier and an Ed25519 key pair, and REQ-207 requires resuming cloud access to require a new login and a new key. `ai_stp_assurance` already defines the signature format and explicitly defers key handling until device identity is implemented in the CLI. Issue #73 requires the private key and cloud credentials to be kept in the system secret store.

There is no system store in the product's primary environment. The agent typically operates over SSH and in containers—which is precisely why device-code flow was chosen for login instead of a loopback redirect. Measurements on the owner's machine showed that with a live session bus, `keyring` selects `SecretService` and the complete write-and-read cycle succeeds; without the bus, it selects `fail.Keyring` and the call produces a typed `NoKeyringError`.

A separate measurement proved even more important: **`keyring.get_keyring()` is not evidence that a protected store is available**. With the `keyrings.alt` package installed, `PlaintextKeyring` with priority 0.5 is selected, the write silently succeeds, and the secret ends up on disk in base64—even though the library reports success. A check for whether a keyring exists would mistake this for a protected store and misinform the user.

Public experience provides three documented defects of the same class. `gh` falls back to a file without reporting it, which has generated a stream of complaints (`cli/cli#10108`). Codex CLI (`openai/codex#14704`) has three documented at once: silent fallback visible only in the debug log; failure to remove the file copy after a successful write to the store, with the deletion error swallowed and the stale secret left on disk; and `0600` permissions applied only when the file is created—overwriting an existing file with weakened permissions writes the secret to a world-readable file.

The industry response to an environment without a store is an explicit environment-variable tier, as in the four-tier lookup used by Heroku CLI. **It is prohibited for us**: `SPEC-011` REQ-1108 does not permit passing a secret through the environment.

## Alternatives

1. System store only, otherwise a typed failure. Maximum protection and inoperability in precisely the environment for which device-code flow was chosen.
2. `0600` file only. Identical behavior everywhere and one fewer dependency, but on the owner's desktop this loses encryption at rest that is actually available there.
3. Tiers with mandatory tier naming. System store when one genuinely exists; otherwise a `0600` file; the tier used is always part of the response.
4. Tiers with an environment-variable tier for CI. Rejected: REQ-1108.

## Decision

Alternative 3 is accepted.

**Tier 1—the system store.** `keyring` is used, but the selected backend is accepted only if it belongs to a closed list of genuinely protected backends: Secret Service, macOS Keychain, Windows Credential Locker, KWallet. Any other backend—including `fail`, `chainer`, and everything from `keyrings.alt`—is treated as the **absence** of a store, not as a store. The list is checked by module and class name, not by priority: priority is assigned by a third-party package.

**Tier 2—a file in the user data directory** with `0600` permissions. The file is created with these permissions from the outset, using `O_CREAT|O_EXCL`, and installed by atomic replacement. An existing file is never opened for writing with truncation: this exact path in Codex CLI caused a secret to be written to a file with weakened permissions. On read, a file with permissions broader than owner-only is rejected with a typed error rather than used silently.

**The tier is always named.** Fallback is not a log event: it is included in the envelope's `warnings` field, so a machine invocation receives it in the same single object and the standard error stream remains empty. `device show` names the active store and the reason, and `doctor` includes the `credential_store` check.

**Promotion to a higher tier cleans up after itself.** If the secret can later be written to the system store, the file copy is deleted, and **a deletion failure is reported** rather than swallowed.

The device key uses Ed25519 via `cryptography`; the signature format is already defined in `ai_stp_assurance`. Identity is created on first launch, offline and without a cloud account, so it does not belong to the login command group.

Resetting identity generates a new `device_id` and a new key pair and marks the previous record as revoked locally; local data is preserved in accordance with REQ-205. Silent reuse of a revoked identity is impossible because reset reuses neither the identifier nor the key.

## Consequences

- `keyring` and `cryptography`, along with their transitive packages, enter the CLI dependency tree; the owner is the CLI track, and the removal path is a transition to a single tier that affects only the storage adapter;
- “where the secret is stored” becomes an observable fact of the machine contract rather than an implementation detail;
- checks can substitute an isolated store because the tier is selected by the adapter rather than by the library's global state;
- the list of protected backends requires maintenance: a new backend does not become trusted on its own.

## Reconsideration Conditions

The decision will be reconsidered if an environment emerges where the file tier is unacceptable under a user requirement—in that case, an explicit refusal to fall back will be needed, and its place will be the closed list of fields in `cli-config.md`. It will also be reconsidered if the refresh token from #75 turns out to require stronger protection than the device key: today both are stored identically, and this is deliberate because the device key proves origin, not execution integrity, under `ADR-0007`.
