# Daily

User intents: is anything drifted, selected vs installed.

Resolve from machine help: `ai-stp target status`, `ai-stp target diff`,
`ai-stp install status`.

Distinguish `local_drift`, `catalog_drift`, and `pending_install`. Neither
drift auto-resolves. `local_drift` suggests restore or a new version.
`catalog_drift` suggests an update after a new plan. Waiting for the selected
version to install is not drift.
