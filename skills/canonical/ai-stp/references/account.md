# Account

User intents: sign in, logout, grants, sync, complain, open the site.

Resolve from machine help: `ai-stp auth login`, `ai-stp auth status`,
`ai-stp auth logout`, `ai-stp grant list`, `ai-stp owner objects`,
`ai-stp sync preview`, `ai-stp report preview`, `ai-stp link web`.

Never pass a password, token, or secret in argv, the environment, or logs.
In browser device flow, show the verification URL and user code; do not
complete the grant for the user.

Verify with `ai-stp auth status`.
