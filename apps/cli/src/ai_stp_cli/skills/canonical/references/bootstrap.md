# Bootstrap

User intents: first message after install, “is ai-stp installed?”, version.

Resolve from machine help: `ai-stp doctor`, `ai-stp help`, `ai-stp capabilities`,
`ai-stp version`.

Run `ai-stp doctor --json`, then `ai-stp help --agent --json`. Treat envelope
`ok` and installation state as the picture. Call only commands that help
returned. Do not invent a missing command.
