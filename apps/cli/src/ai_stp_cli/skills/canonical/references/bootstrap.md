# Bootstrap

If `ai-stp` is missing, use the supported PyPI installation path:
`uv tool install ai-stp-cli`. If uv itself is absent, use its official
installation instructions at <https://docs.astral.sh/uv/getting-started/installation/>.
Refresh the shell's executable lookup and verify that the selected ai-stp belongs
to that installation. A repository checkout or a provider binary is not the CLI.

Run `ai-stp doctor --json`, then `ai-stp help --agent --json`.
Resolve `ai-stp version`, `ai-stp capabilities` and `ai-stp config show`
when installation identity or local readiness needs explanation. Doctor is a
summary: an unrelated optional capability does not block the requested operation.

Use project roots already named in the conversation. Do not ask again.
For “this project”, inspect the current workspace and use its actual root.
Ask which directory only when no root is available or several materially
incompatible roots remain. Do not scan the home directory by default.

Resolve `ai-stp project discover` and `ai-stp project index` for the selected
project when its passport or index is needed. Use `ai-stp component inventory`
and `ai-stp component adopt` when the request is to preserve or reuse existing
configuration; do not adopt every discovered component merely to install a
ready catalog setup.

Public catalog discovery and acquisition work without an account. Sign in when
the requested private access, publication or synchronization requires it.
Continue with [install](install.md) for a ready setup, [compose](compose.md) for
custom composition, or [self](self.md) to deliver this Skill into another harness.
