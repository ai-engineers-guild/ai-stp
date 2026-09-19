# Inspect

User intents: what harnesses do I have, what is on this project, what is
installed.

When the user asks what is wrong or what this CLI can do, start the `inspect`
intent. Do not call inspect as a prelude to every mutation. Do not dump the
full registry. Do not type `ai-stp capabilities` or `ai-stp version`.

Use structured ids from the previous response. Treat discovery as exhaustive
only when `complete: true`. Show `diagnostics` when it is not. Distinguish
`candidate_id` from a Component id. Do not assign `harness_id: null` to a
harness.

Further diagnosis of harnesses, providers, projects, and targets stays in
machine help.
