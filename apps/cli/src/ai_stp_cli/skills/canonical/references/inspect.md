# Inspect

User intents: what harnesses do I have, what is on this project, what is
installed.

Resolve from machine help: `ai-stp harness status`, `ai-stp toolchain profile`,
`ai-stp provider check`, `ai-stp provider trust`, `ai-stp provider conformance`,
`ai-stp project discover`, `ai-stp project index`, `ai-stp component discover`,
`ai-stp component find`, `ai-stp target status`, `ai-stp target diff`,
`ai-stp target backups`.

Use structured ids from the previous response. Treat discovery as exhaustive
only when `complete: true`. Show `diagnostics` when it is not. Distinguish
`candidate_id` from a Component id. Do not assign `harness_id: null` to a
harness.
