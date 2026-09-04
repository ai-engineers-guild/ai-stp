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
