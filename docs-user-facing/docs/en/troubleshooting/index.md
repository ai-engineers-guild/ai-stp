---
title: "Troubleshooting"
description: "Basic ai_stp diagnostics and safe recovery after an error."
---

# Troubleshooting

Everyday recovery for an agent:

```bash
ai-stp task intents --json
```

Follow continuation `argv`. Do not dump the full registry as a prelude.

Expert health, when the user asked what is broken:

```bash
ai-stp doctor --json
```

It reports the state of the CLI, the environment, the local registry, the
device, the credential store, and what this installation can do. `doctor`
exits 0 even when the install is not ready; the state is in the body.

Expert orientation and full registry:

```text
ai-stp capabilities --json
ai-stp help --agent --json
```

If `help --agent` disagrees with a flag on this page, the CLI wins. An
unscoped dump still continues at `task intents`.

## PATH / command not found

Check the installation:

```bash
uv tool list
uv tool install ai-stp-cli
ai-stp version --json
```

The executable is `ai-stp`. The PyPI package is `ai-stp-cli`. If the package
is listed but the command is missing, the `uv` tools directory is not on
`PATH`. Add it, then run `ai-stp version --json` again.

## No account

An account is not needed for local work or for reading the public catalog
anonymously. Signing in is needed for private objects, synchronisation,
publication, devices bound to the cloud session, and grants.

```text
ai-stp auth status --json
ai-stp registry search --kind setup --query frontend --json
ai-stp device init --json
ai-stp passport developer init --json
```

`auth status` reports local-only, authenticated, expired, or revoked. Do not
run `auth login` to "fix" a local compose.

## Offline cache

Local mode should keep working after the initial setup. Public catalog reads
may be answered from cache if the object was already confirmed.

```text
ai-stp registry show --kind component --id <stable_id> --json
ai-stp registry fetch --kind component --id <stable_id> --version 1.0 --json
ai-stp registry acquire --id <setup_id> --version 1.0 --offline --json
```

Read `checked_at` (or the equivalent freshness field in the envelope). Do
not treat a cache hit as a newly verified publication. `--offline` on
`acquire` uses only verified cached passports and artifacts; it refuses if
they are missing.

## Stale plan digest

If you are inside an `install` task, continue that task. The engine
replans. Do not type `install plan` to force a new digest.

Expert: apply of a named leaf repeats the plan and refuses if the digest
no longer matches. That is the protection, not a bug. Do not force the
old digest through.

```bash
ai-stp task continue --json
```

If you already hold an expert operation and the bytes changed underneath,
cancel if apply has not begun:

```bash
ai-stp install cancel --operation <id> --json
```

## Partial apply

Do not delete the target or the backups by hand.

```bash
ai-stp install status --json
ai-stp install recover --operation <id> --json
ai-stp target status --project <id> --harness <id> --json
```

`install recover` reports what the stopped operation left and what may be
done. It recovers nothing itself.

## Install recover / resume

If apply was interrupted after the provider started, finish the result check
without applying again:

```bash
ai-stp install resume --operation <id> --provider <exe> --json
```

`resume` applies nothing. It asks the provider what actually landed. Then:

```bash
ai-stp target status --project <id> --harness <id> --json
ai-stp target backups --project <id> --harness <id> --json
```

Command details: [Install](../cli/install.md), [Target](../cli/target.md).

## Undefined harness

Automatic installation is not considered safe when the harness is
`undefined`.

```bash
ai-stp toolchain harnesses --json
ai-stp toolchain harness-capabilities --json
ai-stp doctor --json
```

Pick any of the seven shipped harnesses, or import and
inspect locally without applying:

```text
ai-stp setup import inspect --root <dir> --harness <id> --json
```

See [Harnesses](../harnesses.md).

## Missing secret store

The device key lives in the OS secret store when a trusted backend is
present, otherwise in an owner-only file. `doctor` names the tier. A file
tier is a supported configuration (SSH, containers), not a hidden failure.

```bash
ai-stp doctor --json
ai-stp device show --json
```

Look at the `credential_store` check and the device identity fields. If
`device init` has never been run, that is `needs_user_action`, not a missing
store:

```bash
ai-stp device init --json
```

`device reset` is destructive and needs `--confirm`. It is not a retry of
`doctor`.

## Experimental without consent

Unverified objects do not join automatic installation without explicit
consent. There is no "include all unverified forever" setting.

```text
ai-stp consent list --json
ai-stp consent allow --scope publisher --target <publisher_id> --json
ai-stp consent allow --scope object_major --target <stable_id>@<major> --json
ai-stp registry search --kind component --query scanner --include-experimental --json
```

`--include-experimental` only changes that search. Installing still needs a
durable record. Revoke with `ai-stp consent revoke`. See
[Trust and safety](../trust-and-safety/index.md).

## Related pages

- [Observe](../cli/observe.md) — `doctor`, `capabilities`, `help --agent`.
- [Quickstart for people](../quickstart/human.md) — `PATH` and first identity.
- [Quickstart for agents](../quickstart/agent.md) — what to do with a refusal.
- [Install](../cli/install.md) — recover, resume, cancel.
- [Target](../cli/target.md) — backups and named rollback.
- [Harnesses](../harnesses.md) — `undefined` is not auto-install.
- [Consent](../cli/consent.md) — experimental objects.
