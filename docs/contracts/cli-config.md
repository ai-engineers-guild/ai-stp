---
description: "Native CLI network configuration and explicit state location."
last_verified: "2026-10-14"
---

# Native CLI configuration

`apps/cli/src/config.rs` owns the accepted fields. The native CLI reads an
explicit YAML file when `--config` is supplied; otherwise it uses these defaults:

```yaml
schema_version: 1
catalog:
  enabled: true
  url: "https://ai-stp.aiguild.space"
sync:
  enabled: false
```

The document is bounded to 1 MiB, one YAML document and the parser's depth/event/
alias budgets. Unknown sections, unknown fields and invalid types are rejected.
Parser failures do not echo supplied content. Explicit command assignments take
precedence over file values, then defaults; `config show` records each source.

`catalog.url` is the origin without `/v1`; HTTP is restricted to explicit
loopback use by the network client. Disabling catalog or sync is enforced by
the corresponding service. Sign-in does not implicitly enable or start sync.
There are no telemetry, background-update or provider-path settings.

State location is separate: explicit `--state-dir`, otherwise `AI_STP_STATE_DIR`,
then `$XDG_DATA_HOME/ai-stp`, then `$HOME/.local/share/ai-stp`. `state path` is
read-only. `init` explicitly creates a new identity; existing Python state must
use the migration plan/apply boundary. No command silently adopts another owner.

Harness programs are observed through `program status`, never managed by config.
Provider releases, source pins and target roots belong to exact operation plans.
Secrets belong to the selected credential store and are not configuration fields.
