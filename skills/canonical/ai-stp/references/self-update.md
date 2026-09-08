# Self-update this CLI

User intents: update ai-stp itself, PyPI wheel, CLI self-update, upgrade the
installed `ai-stp` command.

Resolve from machine help: `ai-stp update check`, `ai-stp update plan`,
`ai-stp update apply`, `ai-stp update status`, `ai-stp update recover`,
`ai-stp update rollback`.

This family replaces the `ai-stp-cli` wheel through the installer that owns
the installation. It does not update providers, harness programs, or setups.

Do not run `uv tool upgrade` when `update plan` exists: a pin in the uv receipt
will not move, and a moving latest is not the planned artifact. Apply the
stored plan digest. After apply, a new process must report the target version.

A TTY notice is not consent. `update apply` requires the plan digest. JSON and
pipes keep one envelope; they do not prompt.

If the journal is `recovery_required`, run `ai-stp update recover` or read
`ai-stp update status`. Do not repeat `update apply` to “sync”.
