# Onboard

User intents: set me up locally, developer passport, device passport.

Resolve from machine help: `ai-stp config init`, `ai-stp config show`,
`ai-stp config set`, `ai-stp config validate`, `ai-stp passport developer init`,
`ai-stp passport developer show`, `ai-stp device init`, `ai-stp device show`,
`ai-stp passport device show`, `ai-stp passport device refresh`.

Read `ai-stp doctor` and `ai-stp config show` before mutating. Do not put
secrets in the config. Verify with `ai-stp doctor` and the matching `show`
command.

A missing config file is valid when defaults are complete. On a fresh install,
registry and device identity may be reported as not created yet; the relevant
initialization command creates them. Initialize the developer passport and
refresh the device passport when composition needs them, then repeat the
corresponding show commands. Keep observed facts and existing choices; do not
invent personal facts merely to make a readiness check green.
