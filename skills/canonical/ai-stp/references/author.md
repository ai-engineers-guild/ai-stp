# Author

User intents: scaffold a skill, adopt a tree, publish a component or setup.

Resolve from machine help: `ai-stp component scaffold plan`,
`ai-stp component scaffold apply`, `ai-stp component template render`,
`ai-stp component source parse`, `ai-stp component adopt`,
`ai-stp component passport validate`, `ai-stp component skill validate`,
`ai-stp component version release`, `ai-stp component publish`,
`ai-stp publication plan`, `ai-stp publication confirm`,
`ai-stp setup publish plan`, `ai-stp attestation sign`.

Replace every scaffold draft marker before compose or release. Run
`ai-stp component skill validate` on the package directory (the directory with
`SKILL.md` at its root), not the whole authoring tree. Publicity and access
are a separate user decision.

New releases and uploads default to private distribution. Invite recipients
through the grant commands in machine help. To open an existing exact version,
resolve `ai-stp publication visibility plan`, `ai-stp publication visibility
status` and `ai-stp publication visibility confirm`; obtain the owner's explicit
decision for the reviewed access effect. Preserve the version and passport
digest. An unsupported server is a dependency failure, not permission to use
public publication as a fallback.

`setup compose` creates a private local setup and can resolve exact granted
catalog pins through authenticated private access after an anonymous public miss.
Review its plan digest before apply; public exposure remains a separate owner decision.
