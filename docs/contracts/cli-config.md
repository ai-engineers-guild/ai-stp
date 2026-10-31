---
description: "Native CLI network configuration and explicit state location."
last_verified: "2026-10-30"
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

## Foreground corporate heartbeat

Company heartbeat policy and local consent are separate. Reporting starts disabled.
For an explicitly retained corporate context, `corporate heartbeat consent plan
--context CONTEXT` reviews the current company policy and the original enrollment.
Save the returned `plan` object and review its `plan_digest`, then use
`corporate heartbeat consent apply --plan FILE --plan-digest DIGEST`. Plans expire
after ten minutes and cannot silently follow a different context, session or policy.
Replaying an already applied plan never re-enables later disabled consent.

`corporate heartbeat delivery --context CONTEXT` reads only local delivery state.
`corporate heartbeat flush --context CONTEXT` performs one foreground pass when
consent is enabled and the company cadence permits it. Desktop performs these
passes only while focused, for the selected corporate context. CLI users invoke
the pass explicitly. Neither client installs a startup service or daemon.
`corporate heartbeat disable --context CONTEXT` stops local reporting and retires
that context's pending payload, including offline or after logout.

One signed observation per context retains its original timestamp and bytes across
retries and process restarts. Retry delays follow company policy; payload expiry
is bounded to four minutes. A later server observation is marked superseded,
not confirmation of the queued observation. Policy changes require renewed consent;
revoked authorization stops delivery. Temporary authorization outages are paced.
`corporate heartbeat maintain` retires expired owned payload bytes locally on the
next foreground pass, including while a personal context is selected. No erasure
while the application is closed is claimed.

The payload contains account/device IDs, CLI version, the fixed
`cli.foreground-liveness` capability, active CLI state, observation timestamp,
policy version and device signature. `last_sync_at` is null. This reports CLI
liveness only: harness activity remains unknown and no installation inventory,
source, prompts, environment contents or model usage are collected by this sender.
The `corporate heartbeat policy` and `status` reads alone never enable delivery.
