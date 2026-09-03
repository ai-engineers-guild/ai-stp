---
title: "Device"
description: "Create, inspect, and reset this installation's device identity without touching local data."
---

# Device

A device identity is the local identity of this installation. It is
created offline, before any account exists, and it stays here if you
never sign in. The private key proves which device a later sync event
or attestation came from.

This is not the device passport and not the cloud session. The passport
describes the environment. The session may never exist at all. Folding
those three together would make “no account yet” and “no device
identity” look the same, and their next actions differ.

## Commands

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp device init` | `apply` | `none` | Create the identity of this installation, or return the existing one. |
| `ai-stp device show` | `read` | `none` | Show this device identity and where its key is kept. |
| `ai-stp device reset` | `destructive` | `explicit_flag` | Retire this device identity and create a new one. |

`device init` is idempotent: a second run returns the identity the first
one made. `device show` creates nothing. `device reset` is a different
command. It is destructive, needs `--confirm`, and is not a way to retry
`doctor`.

## Typical path

```bash
ai-stp device init --json
ai-stp device show --json
```

Local work does not need an account. It does need this identity, and it
needs a developer passport afterwards. See [Passports](passport.md).

The private key lives in the operating system's secret store. If that
store is unavailable the CLI says it fell back to a file and does not
hide the fact. `credential_store` is then `file` rather than
`os_keyring`, and `credential_store_detail` names why.

Do not run `device reset` because `doctor` reported no identity. The
fix for “never created” is `device init`. Reset is for retiring a key
you no longer want this machine to hold.

## `device init`

Create the identity of this installation, or return the existing one.

```bash
ai-stp device init --json
```

The first run needs no `sudo` and no account. If an identity already
exists, the command returns it. It does not rotate the key. It does not
register the device with the platform — that happens during
[Sign-in](auth.md).

If the secret store cannot hold the key, the envelope still succeeds
and a warning says so. Read `warnings`. Do not treat a file fallback as
silent.

## `device show`

Show this device identity and where its key is kept.

```bash
ai-stp device show --json
```

This is a read. If no identity exists, the command refuses with
`AI_STP_NOT_FOUND` and `next_actions` names `device init`. Observing
must not mint state.

The private key has no field in the envelope and cannot be printed by
construction. What you see is public material: the identifier, the
public key, a fingerprint, and where the secret is kept.

## `device reset`

Retire this device identity and create a new one.

```bash
ai-stp device reset --confirm --json
```

`--confirm` is required. Without it the command refuses with
`AI_STP_USER_DECISION_REQUIRED`. That is a decision, not a malformed
flag.

The retired private key is discarded and cannot be recovered. The
retired `device_id` is remembered so it cannot come back. Local data —
the registry, passports, cached catalog bytes, project indexes — is
untouched. Untouched is not the same as reversible: any cloud account
that trusted the old key must approve the new one, which means a new
sign-in.

Reset is not:

- a retry of `device init`;
- a way to “fix” `doctor`;
- a logout (see `auth logout`);
- a factory reset of the installation.

After a reset, `retired_device_ids` on the new identity includes the
old identifier. Cloud access does not resume by itself. You need a new
sign-in, and the account must approve the new key. Local passports,
the registry, and cached catalog bytes remain. They are now attached
to a different device identity; sync will treat that as a different
signer.

=== "Need an identity"
    ```bash
    ai-stp device init --json
    ai-stp device show --json
    ```

=== "Need to retire a key"
    ```bash
    ai-stp device reset --confirm --json
    ai-stp device show --json
    ```

    Only after a person has decided to discard the current key.

## What a successful envelope contains

All three commands return the same result shape in `data`:

| Field | What it is |
| --- | --- |
| `device_id` | this installation's device identifier |
| `public_key` | the public half of the device key |
| `key_fingerprint` | a short fingerprint of that key |
| `state` | `active` or `revoked` |
| `credential_store` | `os_keyring` or `file` |
| `credential_store_detail` | why that store was chosen |
| `created_at` | when this identity was created |
| `retired_device_ids` | identifiers this installation has retired |
| `schema_version` | the schema major of this report |

The envelope also carries `ok`, `warnings`, `next_actions`,
`request_id`, `operation_id`, and `schema_version`. After `init` or
`reset`, a warning about a file fallback is still a success.

## Device identity is not the device passport

| Object | Command group | What it holds |
| --- | --- | --- |
| Device identity | `device` | `device_id`, the key pair, revocation |
| Device passport | `passport device` | observed environment: OS, architecture, installed harnesses |
| Cloud session | `auth` | whether this device currently holds account credentials |

`device show` does not print operating system or harness versions.
Those belong to `passport device show`. `auth status` does not print
`device_id` as proof of a session: a device always exists after `init`,
a session may not.

## What these commands never do

- print or export the private key;
- put a secret into a passport, a log, or the configuration file;
- delete the local registry or cached catalog bytes;
- sign you in, or register the device with the platform by themselves;
- write a harness target.

## Typical refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `AI_STP_NOT_FOUND` on `device show` | identity was never created | `ai-stp device init --json` |
| `AI_STP_USER_DECISION_REQUIRED` on `device reset` | `--confirm` was missing | `ai-stp device reset --confirm --json` after an explicit decision |
| `credential_store` is `file` | the OS secret store was unavailable | read `credential_store_detail`; this is reported, not hidden |
| doctor reports no device | `device show` would refuse the same way | `device init`, not `device reset` |
| cloud calls fail after reset | the old key is retired | `auth login` then `auth complete` for the new identity |

## Related pages

| Page | Why |
| --- | --- |
| [Quickstart](../quickstart.md) | first-run identity in prose |
| [Observe](observe.md) | `doctor` reports `device_identity` |
| [Passports](passport.md) | device passport vs identity |
| [Sign-in](auth.md) | attaching this device to an account |
| [Sync](sync.md) | events signed by this device |
| [Web devices](../web/devices.md) | the same identity as the website shows it |
| [Troubleshooting](../troubleshooting/index.md) | secret-store and PATH failures |

!!! note "Flags from `ai-stp help --agent --json`"
    If `help --agent` disagrees with a flag on this page, the CLI wins.
    Optional flags are not listed here. Read them from the descriptor.
    `device reset` needs `--confirm`.
