# Catalog

User intents: find a skill or setup, show this version, fetch bytes.

Resolve from machine help: `ai-stp registry search`, `ai-stp registry show`,
`ai-stp registry version`, `ai-stp registry fetch`, `ai-stp registry acquire`.

Pin an exact `id` and `X.Y`. Default to the `authoritative` line. Show
`experimental` only with explicit consent, in a separate section. An object key
is not authority to fetch; only the catalog command that closes offline
supplies bytes. Verify the returned identity before any later compose or
install step.
