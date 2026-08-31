---
description: "Decision to limit all CLI outbound traffic to one anonymous GET after explicit consent and state everything it is not."
last_verified: "2026-08-21"
---

# ADR-0112: Client egress is one GET after consent

Status: accepted.

## Context

The product question is simple: where people install components. The operating
system, harness and its version, what exactly was installed, and the `ai_stp`
version. One line such as "Serena MCP was installed on Windows in Codex
0.140.1."

The MVP plan blocked telemetry until a boundary existed, correctly: without a
boundary, "a little telemetry" expands silently. Hence the decision is not to
permit collection, but to **name exactly one channel** and declare everything
else outside it.

Today the CLI reaches outside only for the catalog and provider releases, and
both routes are declared. There is no client analytics egress at all.

## Options

**Collect nothing.** Inexpensive and honest, but leaves the product decision on
harness support without a single fact: which combinations actually occur can
only be guessed.

**Events through `/v1`.** Authentication, schemas, and storage already exist.
That is precisely why this is wrong: a channel capable of carrying an account
will eventually carry it, while `REQ-1315` keeps catalog counters unlinkable to
a person. An authenticated event stream is a user profile deferred by one
iteration.

**OpenTelemetry or a web analytics SDK.** Both carry an open-ended field set
and their own transport. A boundary that cannot be enumerated is not a boundary.

**One anonymous GET to a configurable address.** An enumerable query set, no
body, and no credentials of any kind.

## Decision

All client telemetry egress is one unauthenticated `GET` with a closed set of
query fields, over HTTPS, with a short timeout, no body, no cookie, no catalog
token, and no GitHub authorization.

**Disabled by default.** Until consent exists, there are zero requests. Refusal
and "not asked yet" behave identically—one observable behavior, not two states
with different network activity.

Consent is given through a separate command, not an interactive prompt: the CLI
does not render a terminal dialog because its primary consumer is an agent, and
an agent prompted on stdin hangs. The command prints a screen and accepts
`--accept` or `--decline` together with `--confirm`.

Writing `telemetry.enabled=true` while bypassing the consent command is
rejected. Consent is an event, not a value: otherwise "enabled" could appear
through a file edit and the origin of consent would be unknown.

**What is sent is enumerable and closed:** operating system, harness and its
version, `ai_stp` version, component kind, name, source (`platform` or
`github`), identifier (platform stable id **or** public GitHub URL), exact
component version, and a random local anonymous identifier.

**What is never sent:** local paths, private repositories, account, device key,
email, project name, target path, environment variables, or file contents. If
nothing can be named publicly, no request is made.

The anonymous identifier exists only to distinguish one CLI installation from
another. It is created only upon consent, stored in the local data directory
rather than configuration, is not a `device_id`, and is not linked to an
account. Refusal and disabling delete it; renewed consent creates a new one. It
is not combined with catalog counters—`REQ-1315` is not weakened.

**When:** after a **verified** `install apply` with the `install` or `update`
action, one request per component actually installed. Not for `backup`,
`rollback`, `remove`, or reads.

**Fail-open.** A network error, timeout, and any non-2xx response are silently
swallowed. Installation does not fail because of telemetry and does not retry
the request in a batch: the installation result is a property of the target,
not the network.

Offline mode and tests make no requests, and `just check` does not contact a
live collector.

## Consequences

The first previously absent client egress appears, and it is declared in full:
fields are listed in `docs/contracts/`, behavior in `SPEC-013`, and
configuration in `SPEC-011` `REQ-1114` and `docs/contracts/cli-config.md`.

The canonical Skill and `doctor` direct the user to the consent screen once
when the status is `not_asked`, and do not block work while no answer exists.

What this decision is **not** is stated to prevent silent expansion: it is not
a web panel, event storage in `apps/api`, a user profile, sending on every run,
an interactive prompt, or a weakening of the prohibition on cookies and web
analytics.

## Reconsideration conditions

Reconsider if a field outside the enumerated set is needed, if the ping must be
linked to an account—which would be a different decision and a different
channel—or if fail-open ceases to be acceptable.
