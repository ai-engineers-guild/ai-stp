# Install

User intents: install this, update, roll back.

Resolve from machine help: `ai-stp install plan`, `ai-stp install approve`,
`ai-stp install apply`, `ai-stp install cancel`, `ai-stp setup update plan`,
`ai-stp setup update apply`, `ai-stp setup import plan`,
`ai-stp registry acquire`, `ai-stp target status`, `ai-stp target rollback`.

Show `required_authorization` from the plan. Apply only the digest that plan
returned. After apply, call `ai-stp target status` with the same provider and
trust `pending_authorization`; do not infer readiness from a successful apply
or repeat apply to finish sign-in.

For preservation and return, resolve `ai-stp setup preserve plan`,
`ai-stp setup preserved list`, `ai-stp setup preserved show` and
`ai-stp setup restore plan`. Select the saved setup identity, not a guessed
backup reference. Verify coverage and available recovery evidence. A return
preserves current edits first and verifies the full covered native state.
Recorded evidence from an offline list is not a fresh provider measurement.
