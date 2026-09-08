# Self-update this CLI

User intents: update ai-stp itself, PyPI wheel, CLI self-update, upgrade the
installed `ai-stp` command.

Resolve from machine help: `ai-stp update check`, `ai-stp update plan`,
`ai-stp update apply`, `ai-stp update status`, `ai-stp update recover`,
`ai-stp update rollback`.

This family replaces the `ai-stp-cli` wheel through the installer that owns
the installation. It does not update providers, harness programs, or setups.

Prefer the built-in updater when its plan command works: a pin in the uv receipt
will not move, and a moving latest is not the planned artifact. Apply the
stored plan digest. After apply, a new process must report the target version.

A TTY notice is not consent. `update apply` requires the plan digest. JSON and
pipes keep one envelope; they do not prompt.

If the journal is `recovery_required`, run `ai-stp update recover` or read
`ai-stp update status`. Do not repeat `update apply` to “sync”.

If rollback reports that the previous CLI cannot read the current registry
schema, keep the compatible CLI. The refusal preserves the current data;
restoring a pre-update data backup would discard later work and is not part of
binary rollback.

If this old CLI cannot start or read a registry created by a newer version,
preserve the registry and use its owning installer to install an exact published
compatible version. Never downgrade or rewrite the registry to fit an old
reader. A pinned uv installation may stay unchanged after a generic upgrade;
verify the version in a new process. Re-read machine help and refresh the owned
control Skill after updating.
