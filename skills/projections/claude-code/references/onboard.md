# Onboard

User intents: set me up locally, developer passport, device passport.

First-run harness discoverability is the `initialize` intent, not config init.
If the user asked what is broken, start `inspect`. Do not run `ai-stp doctor`
or `ai-stp config show` as a prelude to every mutation.

Config, device identity, and developer passport stay expert. Do not type
`ai-stp config init`. Start the `initialize` intent. Resolve `ai-stp config show`,
`ai-stp config set`, `ai-stp config validate`, `ai-stp passport developer init`,
`ai-stp passport developer show`, `ai-stp device init`, `ai-stp device show`,
`ai-stp passport device show`, `ai-stp passport device refresh` from machine
help. Do not put secrets in the config.

A missing config file is valid when defaults are complete. On a fresh install,
registry and device identity may be reported as not created yet; the relevant
initialization command creates them. Keep observed facts and existing choices;
do not invent personal facts merely to make a readiness check green.

`initialize` writes only through the bound provider. If the task blocks with
`question_id` `provider-too-old`, report that limitation and stop. Do not
start `account`. Do not loop `task continue`. Do not type `provider network`.
Bytes are not written until that provider declares the operation.
