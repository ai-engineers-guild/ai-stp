---
description: "Discovery, version checking, updating, and reinstalling a setup-system provider."
last_verified: "2026-08-29"
---

# Setup-system provider lifecycle

The requirements owner is `#452`. A provider is the only thing that writes the final
harness state, so which copy will run now, which version it is, and whether a newer one
exists are facts the user must be shown.

Replacing a provider changes one executable file and nothing else. What that provider
then does to the target harness remains its own operation, with its own
plan and confirmation.

## Where the path comes from

The order is fixed, and every response names its source:

```text
explicit --executable
    ↓
config: provider.paths.<harness_id>
    ↓
selection recorded in the registry
    ↓
discovery in ~/.local/share/ai-stp/providers/<harness>/<tag>/
```

“Provider found” and “provider selected” are different facts, and only the
latter is a decision. Therefore, `provider check` records an **observation**, not a selection:
a row with source `discovered` does not resolve the question, and if a second
provider later appears on the machine, discovery runs again and reports
ambiguity. `provider update` and `provider reinstall` record the selection.

The registry is where the answer is stored, not the source from which it came. The word
`registry` is not returned as a source: when it was, discovery on the
next run was overwritten as a selection, and a second provider became
invisible forever.

Multiple candidates are the `ambiguous` state, not an error. Two copies on the
machine are normal; silently selecting and overwriting one is not.

## Check

```bash
ai-stp provider check --json                     # all harnesses
ai-stp provider check --harness codex --json     # one
ai-stp provider check --offline --json           # do not query the release source
```

States: `up_to_date`, `update_available`, `unknown_version`,
`source_unavailable`, `unsupported_platform`, `unmanaged`, `missing`,
`ambiguous`. Each is an outcome, not silence: an unavailable release source yields
`source_unavailable`, not “no updates.”

Versions are compared numerically, not as text: `0.0.10` is newer than `0.0.9`. A version
the parser does not understand is never declared outdated—the honest answer is
“cannot determine what is newer,” not a guess.

## Update

```bash
ai-stp provider update plan --harness codex --json
ai-stp provider update apply --harness codex \
  --expected-plan-digest <digest> --confirm --json
```

Planning and applying are two commands, as with `install plan` and `install apply`.
A single command that sometimes returns a plan and sometimes a result exposes two
different schemas under one declaration, and the agent validating the response checks it
against the wrong one.

A plan without confirmation installs nothing and—more importantly—changes
nothing: downloaded bytes go to a temporary directory, not the discovery
directory. When they went there, the plan itself created a second installation, after
which the machine became ambiguous and the newly planned update
refused to run.

`apply` recomputes the plan and checks the digest. A stale plan is rejected instead of
installing something that was not in it.

It is idempotent by digest: if the required bytes are already in place, the response is
`unchanged` and no backup is created. An interrupted run can be repeated—the
second run will not become a second installation.

Replacement is atomic: the file is written beside the target and renamed over it, so
an interruption leaves either the old executable or the new one, never a
partially written executable that can still run. The replaced bytes remain beside it
under a name containing their digest.

## Reinstallation

```bash
ai-stp provider reinstall plan --harness codex --version 0.0.32 --json
ai-stp provider reinstall apply --harness codex --version 0.0.32 \
  --expected-plan-digest <digest> --confirm --json
```

Without `--version`, the currently installed version is reinstalled. Moving to the
newest version is `update`, a separate action: only one of the two may surprise
the person who ran it.

## Externally managed provider

An executable not placed by `ai-stp` is not silently overwritten.
The operation is rejected and names the flag:

```bash
ai-stp provider update plan --harness codex --adopt --json
```

## Forgetting the selection

`update` and `reinstall` record a decision, and a decision that cannot be undone
leaves the machine bound to the path from which it originated:

```bash
ai-stp provider forget --harness codex --json   # one harness
ai-stp provider forget --json                   # all
```

Afterward, configuration and discovery decide—as before the first update.

## Recovery

The backup is stored beside the replaced file and named by the digest of the previous
bytes, not by time: two runs replacing the same bytes write the same
copy, so repeating an update cannot overwrite the one needed for rollback.

```bash
cp <path>.<digest>.backup <path>
ai-stp provider check --harness <harness> --json
```
