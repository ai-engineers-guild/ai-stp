# Bootstrap

If `ai-stp` is missing, use the supported PyPI installation path:
`uv tool install ai-stp-cli`. If uv itself is absent, use its official
installation instructions at <https://docs.astral.sh/uv/getting-started/installation/>.
Refresh the shell's executable lookup and verify that the selected ai-stp belongs
to that installation. A repository checkout or a provider binary is not the CLI.

Run `ai-stp task intents --json` and start the matching shipped intent. Use
`ai-stp doctor` only when the user asked what is broken. `ai-stp version`
explains the running build when that is the question.
Do not type `ai-stp capabilities`. It lists every command path. Installation
identity is the `inspect` intent.

Use project roots already named in the conversation. Do not ask again.
For “this project”, inspect the current workspace and use its actual root.
Ask which directory only when no root is available or several materially
incompatible roots remain. Do not scan the home directory by default.

Resolve `ai-stp project discover` and `ai-stp project index` for the selected
project when its passport or index is needed. `ai-stp component inventory` is
expert discovery. Do not type `ai-stp component adopt` to install a ready
catalog setup; register a directory with the `author` intent.

Public catalog discovery and acquisition work without an account. Sign in when
the requested private access, publication or synchronization requires it.
Continue with [install](install.md) for a ready setup, [compose](compose.md) for
custom composition, or [self](self.md) to deliver this Skill into another harness.
First-run harness discoverability is the `initialize` intent, not a paste of
this file into a project instruction.
