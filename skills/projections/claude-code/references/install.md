# Install, preserve and return

For a ready catalog setup, start the `install` intent. Do not type the install group with no leaf, and do not type `ai-stp install plan`, `ai-stp install approve`, or `ai-stp install apply`.
The task engine drains those in-process.

1. Establish the harness and absolute project root from the conversation.
   If the user names an exact setup, pass `setup_id` and `setup_version`.
   Otherwise the engine picks one first-party `baseline` pin for that harness.
   It will not quiz the catalog. A missing project, developer, or device
   passport is minted in-process. Do not type `project passport`.
   A typed isolation failure has empty `continuations` and
   `error.details.state=failed`. Stop. Do not type `provider network`.
   Do not invent `task get`.
2. Call `ai-stp task start` with intent `install` and execute continuation
   `argv` only when `actor` is `cli`. Relay one blocked question through `ai-stp task answer`.
3. Report payload verification: setup identity, operation id, and whether
   native state is `verified`. Envelope `ok` alone is not enough.
   `pending_authorization` is unfinished sign-in, not a reason to replay apply.

To return the last working user config, start the `switch` intent. Do not
type `ai-stp setup restore plan` or `ai-stp setup preserve plan`. The engine
restores the newest user `preserved_setup` for that target, never an upstream
catalog pin. It captures current drift as a leftover first.

1. Pass `harness_id` and the absolute `project_root` when known. An explicit
   `preserved_setup_id` selects that snapshot; otherwise the newest saved
   user config for the target is used. A missing snapshot is `not found`,
   not a catalog quiz. Do not answer `project-root` with a harness config
   directory.
2. Call `ai-stp task start` with intent `switch` and execute continuation
   `argv` only when `actor` is `cli`. Relay `reload-session` through `ai-stp task answer`
   after the human reloads the harness session. Do not kill the caller.
3. Report the restored identity, leftover id, operation id, and that
   `session_loaded` is false. Files may already be written while the task is
   still `blocked`. Envelope `ok` alone is not enough.

Public acquisition needs no sign-in. If the harness program itself is missing,
follow [provider](provider.md). Keep its executable prefix separate from the
configuration target.

For an interrupted operation use [recover](recover.md) before another write.
Expert recovery still uses `ai-stp install recover` and `ai-stp install status`
on demand; do not dump the full registry.

List or inspect a saved identity from machine help. An offline saved record is
not a fresh provider measurement. Existing native state that should become an
editable local setup is expert import, not a restoration point; do not type
`setup restore plan`.
