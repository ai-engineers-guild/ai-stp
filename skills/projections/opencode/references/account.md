# Account

Public discovery and public setup acquisition are anonymous. Use this playbook
when the user says sign in, sign out, or explicitly sync, or when a question
carries a device-code / user_code. Do not open this playbook for
`provider-too-old`. If they are already signed in and did not ask to sign in,
sign out, or sync, do not type `ai-stp` and do not start `account`.

Start the `account` intent. Do not type `ai-stp auth login`,
`ai-stp auth complete`, or `ai-stp auth logout`. Login never uploads and never
implies sync.

1. Pass `action` (`login`, `logout`, or `sync`) and `provider` when known.
2. Call `ai-stp task start` with intent `account` and execute continuation
   `argv` only when `actor` is `cli`. For `actor=external`, show the user code and verification
   URI once and stop. Do not call `task continue` in that turn. Later
   `ai-stp task continue` only after the browser, never in a tight loop.
   Do not call `task answer` for that question.
3. Report `authenticated` and `login_uploaded=false`. A shown code is not a
   session. Envelope `ok` alone is not enough.

Never fabricate a session or expose passwords, tokens or device secrets in
argv, environment, logs or reports. Do not sign into someone else's account.
Existing-object visibility and access changes follow [decisions](decisions.md).

Explicit sync is `account` with `action=sync` and `scope` `push` or `pull`.
Do not type `sync push` or `sync pull`. Push needs the exact local `stable_id`
for a developer, component, setup, device summary, or consent. The task asks
`stable-id` if it is missing or unsupported; a `project_root` is not a sync entity.
Project passports and absolute local paths stay on the device. If sync is disabled,
use the returned configuration repair before starting a new sync task.
Linked project history is the organization ledger, not account sync.
Do not type `project passport`. Do not type `project revision push`.
Do not type `project revision pull`, `project sync plan`, or `project sync apply`.
A `local_to_remote` plan is
unreachable until that revision is in the ledger. The plan's `local_revision`
is the ledger `revision_id` from the push receipt, not the passport's own
`revision_id`.

Read `outcome.sync_result`, not envelope `ok`, for the actual sync receipt.
Rejected, conflicting, or superseded pushes do not satisfy the sync goal.
When pull reports `partial`, inspect its `pending_version_count` and returned
version coordinates. A device retaining those exact snapshots can send them
with an updated CLI; pull then materializes them without changing the draft.
Follow the same task's CLI continuations through progressing pages. If an empty page still reports missing
snapshots, retain that result and continue unrelated authorized work instead of
polling an unchanged stream. Report which source data is needed; neither an
invented snapshot nor skipping history proves complete synchronization.
