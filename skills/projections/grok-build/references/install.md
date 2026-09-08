# Install, preserve and return

For a ready catalog setup, follow this route using the installed descriptors.
Carry identifiers and digests forward from each response; do not invent them.

1. Establish the harness, project root and intended native scope. If the user
   names an exact setup, resolve `ai-stp registry version`; otherwise use
   `ai-stp registry search` and `ai-stp registry show` to select an exact version
   matching that harness. A setup belongs to its harness.
2. Run `ai-stp registry acquire` for that exact setup. It closes component pins
   and verified artifact bytes for local compilation. A metadata read alone is
   insufficient. Public acquisition needs no sign-in.
3. If the harness program is needed, follow [provider](provider.md). Keep its
   executable prefix separate from the configuration target. Inspect existing
   configuration and preserve it when the task includes replacing it.
4. Run `ai-stp install plan` for the acquired setup, its project, target and
   supported scope. Alternatively pass a newly confirmed composition proposal
   from [compose](compose.md). These are alternative inputs, not cumulative ones.
5. Inspect the actual paths, conflicts, required authorization and recovery
   information. Within task authority, run `ai-stp install approve` with the
   returned operation identifier and plan digest, then `ai-stp install apply`
   with that same operation. Copy each parameter name from its descriptor.
6. Read `ai-stp install status` and `ai-stp target status`. Verify the exact
   setup and target, not only the process exit code. Treat
   `pending_authorization` as unfinished sign-in, not a reason to replay apply.

For an update use `ai-stp setup update plan` and `ai-stp setup update apply`.
For an interrupted operation use [recover](recover.md) before another write.
For a provider-owned rollback resolve `ai-stp target rollback` and the exact
backup reference from the operation's evidence.

To retain the current complete configuration, use `ai-stp setup preserve plan`,
then follow its returned operation route. List or inspect the saved identity
with `ai-stp setup preserved list` / `ai-stp setup preserved show`.
`ai-stp setup restore plan` selects that saved identity, preserves current edits
first, and must finish with fresh verification of the covered native state.
An offline saved record is not a fresh provider measurement. Use
`ai-stp setup import plan` when existing native state should become an editable
local setup rather than merely a restoration point.
