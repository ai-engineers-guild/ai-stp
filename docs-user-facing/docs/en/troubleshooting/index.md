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
device, and what this installation can do.

## Command not found

Check the installation:

```bash
uv tool list
```

If `ai-stp-cli` is installed but the command is unavailable, check that the
`uv` tools directory is on `PATH`.

## No account

An account is not needed for local work or for reading the public catalog
anonymously. Signing in is needed for private objects, synchronisation,
publication, devices and grants.

## No network

Local mode should keep working after the initial setup. The public catalog may
be answered from cache if the object was already confirmed by the platform.

## An install failed

Do not delete the target or the backups by hand. Check the plan, the operation
journal and the provider's state, then use the ordinary recovery path.
