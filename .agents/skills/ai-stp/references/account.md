# Account

Public discovery and public setup acquisition are anonymous. Use this playbook
when the user says sign in, sign out, or explicitly sync, or when a mutating
intent blocks with `actor=external`.

Start the `account` intent. Do not type `ai-stp auth login`,
`ai-stp auth complete`, or `ai-stp auth logout`. Login never uploads and never
implies sync.

1. Pass `action` (`login`, `logout`, or `sync`) and `provider` when known.
2. Call `ai-stp task start` with intent `account` and execute continuation
   `argv` only when `actor` is `cli`. For `actor=external`, show the user code and verification
   URI once, then later call `ai-stp task continue`. Do not poll in a tight
   loop. Do not call `task answer` for that question.
3. Report `authenticated` and `login_uploaded=false`. A shown code is not a
   session. Envelope `ok` alone is not enough.

Never fabricate a session or expose passwords, tokens or device secrets in
argv, environment, logs or reports. Do not sign into someone else's account.
Existing-object visibility and access changes follow [decisions](decisions.md).

Explicit sync is `account` with `action=sync` and `scope` `push` or `pull`.
Push needs the absolute `project_root`. Linked project history is the
organization ledger, not account sync: after `ai-stp project passport`, expert
leaves `ai-stp project revision push`, `ai-stp project revision pull`,
`ai-stp project sync plan` and `ai-stp project sync apply` remain for moving
link pointers. A `local_to_remote` plan is unreachable until that revision is
in the ledger. The plan's `local_revision` is the ledger `revision_id` from
the push receipt, not the passport's own `revision_id`.

When pull reports `partial`, inspect `pending_version_count` and the returned
version coordinates. A device retaining those exact snapshots can send them
with an updated CLI; pull then materializes them without changing the draft.
Continue through nonempty pages. If an empty page still reports missing
snapshots, retain that result and continue unrelated authorized work instead of
polling an unchanged stream. Report which source data is needed; neither an
invented snapshot nor skipping history proves complete synchronization.
