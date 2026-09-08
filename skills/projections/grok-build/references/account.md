# Account

Public discovery and public setup acquisition are anonymous. Use this playbook
when the requested operation needs private access, publication or account sync.
Resolve `ai-stp auth login`, `ai-stp auth complete`, `ai-stp auth status`,
`ai-stp auth logout`, `ai-stp grant list`, `ai-stp owner objects`,
`ai-stp sync preview`, `ai-stp sync pull`, `ai-stp sync push`, `ai-stp report preview` and `ai-stp link web` from help.

1. Inspect auth status; reuse a valid account session.
2. If sign-in is required, start login and use its exact verification URL and
   user code. Complete the real browser flow for the user's own account within
   the available browser permissions. If it needs the user's interaction or an
   unresolved account choice, show that exact step and keep unrelated work going.
3. Run auth complete after browser approval, then verify auth status. A shown
   code or an opened browser is not an authenticated CLI session.

Never fabricate a session or expose passwords, tokens or device secrets in
argv, environment, logs or reports. Do not sign into someone else's account.
Existing-object visibility and access changes follow [decisions](decisions.md).
For synchronization inspect the preview and the actual receipt; an accepted
command envelope may still contain a conflict. A named missing revision is a
recovery problem, not permission to skip unknown account history.

When pull reports `partial`, inspect `pending_version_count` and the returned
version coordinates. A device retaining those exact snapshots can send them
with an updated CLI; pull then materializes them without changing the draft.
Continue through nonempty pages. If an empty page still reports missing
snapshots, retain that result and continue unrelated authorized work instead of
polling an unchanged stream. Report which source data is needed; neither an
invented snapshot nor skipping history proves complete synchronization.
