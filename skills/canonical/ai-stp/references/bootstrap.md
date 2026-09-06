# Bootstrap

User intents: first message after install, “is ai-stp installed?”, version,
“set me up”, which projects to index.

Resolve from machine help: `ai-stp doctor`, `ai-stp help`, `ai-stp capabilities`,
`ai-stp version`, `ai-stp skill install`, `ai-stp project discover`,
`ai-stp project index`, `ai-stp component inventory`, `ai-stp component adopt`.

Run `ai-stp doctor --json`, then `ai-stp help --agent --json`. Treat envelope
`ok` and installation state as the picture. Call only commands that help
returned. Do not invent a missing command.

After those two reads, if this is a first run or the user asked to set up:

1. Ask which project directories to index. That question names their trees; it
   is not a remaining stop in `decisions.md`.
2. For each named root, resolve `project discover` and `project index` from
   machine help. Treat a partial index as partial; do not call it complete.
3. Resolve `component inventory` on the same roots. Adopt each reported
   component through `component adopt`. A second adopt of the same source is a
   no-op.
4. If doctor shows this Skill is not installed in the harness they are using,
   resolve `skill install` from machine help.

Do not scan the home directory. Do not invent roots. Do not write a harness
target.
