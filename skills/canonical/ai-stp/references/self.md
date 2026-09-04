# Self

User intents: install the ai-stp Skill into a harness, remove it.

Resolve from machine help: `ai-stp skill status`, `ai-stp skill install`,
`ai-stp skill remove`.

The destination is required until harness discovery exists. Install a directory
named `ai-stp` so the package `name` matches. This Skill is the control plane:
installing, updating, or removing a user setup must not delete it.

`foreign` means someone else wrote the file; do not overwrite it. `stale` means
it was edited after this installation wrote it; remove only with an explicit
request. Never remove this Skill as part of a setup switch.
