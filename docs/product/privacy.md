---
description: "What leaves the user's machine, what never leaves it, and how to answer questions about telemetry."
last_verified: "2026-09-01"
---

# CLI privacy

This page answers the question for a person deciding whether to consent.
The machine boundary — the list of fields, their sources, and sending rules — is owned by
[`cli-telemetry.md`](../contracts/cli-telemetry.md); the requirements belong to
`SPEC-013`, and the decision to [`ADR-0112`](../adr/ADR-0112-client-egress-is-one-consented-ping.md).
None of it is repeated here: a divergent copy is worse than no copy.

## Short answer

`ai_stp` sends nothing until you consent. There is no consent by default;
installation, updates, or signing in do not create it, and it
cannot be granted by editing the settings file.

If you consent, one anonymous request leaves the machine for each
installed component. It says that “a particular publicly named component
of a particular version was installed on a particular harness on a particular OS.” It does not say who
did it.

## What never leaves

No response or setting ever sends local paths, private repositories, the account
identifier, device key, email, project name, target path, environment variables,
file contents, or MCP server parameters. A component that cannot be named publicly
is not described approximately — it is simply not mentioned.

The anonymous identifier exists for exactly one purpose: to distinguish one CLI installation
from another. It is not the device key, is not linked to an account, and is not combined
with public catalog counters.

## How to respond

```bash
ai-stp telemetry show --json
```

Prints the current state, collector address, and list of fields — including `anon`
by name. The command does not print the identifier value: showing it would make
an ordinary state read the very place from which it could be copied.

```bash
ai-stp telemetry consent --accept --confirm --json
ai-stp telemetry consent --decline --confirm --json
```

Exactly one response is required, and it requires `--confirm`. A flag passed
without review is insufficient: consent obtained that way is not consent, while
an accidental refusal would be recorded as the response and nothing would ask again.

## How to change your mind

```bash
ai-stp config set --set telemetry.enabled=false
```

Disables sending and deletes the anonymous identifier. The recorded response is
retained: being disabled and having been asked and declined are different things, and
the question does not return.

The reverse command cannot enable it — `telemetry.enabled=true` is rejected with
a typed error. Consent is an event, not a value: enabling it
by editing a file would leave “enabled” where nobody can say who
consented or when.

Consenting again after declining creates a **different** identifier. The previous one is not
restored — otherwise disabling and enabling would link the two periods, which
is precisely what the person who disabled it sought to avoid.

## If the collector is unavailable

Nothing happens. A network error, timeout, or any non-2xx response
is silently swallowed, the installation remains `verified`, and there is no batch retry.
The installation result is a property of your target, not of someone else's service.
