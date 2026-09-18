# Daily

User intents: is anything drifted, selected vs installed.

When the user asks if anything drifted, start the `inspect` intent. Do not dump
`ai-stp target status` as a prelude to every session.

Distinguish `local_drift`, `catalog_drift`, and `pending_install`. Neither
drift auto-resolves. `local_drift` suggests the `switch` intent for the last
working user config, or a new version. `catalog_drift` suggests an update after
a new plan. Waiting for the selected version to install is not drift.

Further diagnosis: resolve `ai-stp target status`, `ai-stp target diff`, and
`ai-stp install status` from machine help.
