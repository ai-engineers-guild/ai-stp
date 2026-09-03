---
title: "Troubleshooting"
description: "Basic ai_stp diagnostics and safe recovery after an error."
---

# Troubleshooting

Start with:

```bash
ai-stp doctor --json
```

It reports the state of the CLI, the environment, the local registry, the
device, the credential store, and what this installation can do. `doctor`
exits 0 even when the install is not ready; the state is in the body.

Also useful:

```bash
ai-stp capabilities --json
ai-stp help --agent --json
```

If `help --agent` disagrees with a flag on this page, the CLI wins.

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

```bash
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

```bash
ai-stp registry show --kind component --id <stable_id> --json
ai-stp registry fetch --kind component --id <stable_id> --version 1.0 --json
ai-stp registry acquire --id <setup_id> --version 1.0 --offline --json
```

Read `checked_at` (or the equivalent freshness field in the envelope). Do
not treat a cache hit as a newly verified publication. `--offline` on
`acquire` uses only verified cached passports and artifacts; it refuses if
they are missing.

## Stale plan digest

Apply repeats the plan and refuses if the digest no longer matches. That is
the protection, not a bug. Do not force the old digest through.

```bash
ai-stp setup compose plan --manifest setup.json --root . --json
ai-stp install plan --setup <stable_id>@<X.Y> --json
```

Build a new plan, show it, pass the new `--expected-plan-digest` (or
`--plan-hash` / `--set-digest`). If you already approved an operation and
the bytes changed underneath, cancel if apply has not begun:

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

Stay on a primary harness (Claude Code, Codex, Grok Build), or import and
inspect locally without applying:

```bash
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

```bash
ai-stp consent list --json
ai-stp consent allow --scope publisher --target <publisher_id> --json
ai-stp consent allow --scope object_major --target <stable_id>@<major> --json
ai-stp registry search --kind component --query scanner --include-experimental --json
```

`--include-experimental` only changes that search. Installing still needs a
durable record. Revoke with `ai-stp consent revoke`. See
[Trust and safety](../trust-and-safety/index.md).
