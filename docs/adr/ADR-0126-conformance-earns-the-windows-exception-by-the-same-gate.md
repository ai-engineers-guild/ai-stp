---
description: "Decision to extend the Windows exception to provider conformance through the same trust signal, not because it is read-only."
last_verified: "2026-08-30"
---

# ADR-0126: Conformance earns the Windows exception through the same signal

Status: accepted. Clarifies the scope of `#416`.

## Context

`#416` allowed a local phase without network isolation on Windows and
**explicitly** limited its scope: "protocol v2, `target-status`/`diff`, and
other provider spawns outside the install plan do not receive the exception."
`ADR-0125` and the implementation complied with this.

The consequence surfaced in `#423`: on Windows, `provider conformance` does
not run at all. This is not "some cases are refused"—the command with which a
provider author checks a build is unavailable on an entire platform.

The refusal was correct, but the reason I gave for it was not. I said that an
installation has a plan, approval, and journal to rely on, while an
observational invocation has nothing with which to constrain a provider that
already has the target and network access.

**This does not withstand scrutiny.** A plan, approval, and journal do not stop
a process from using the network: during installation on Windows, the provider
runs without isolation in exactly the same way. Its ability to access the
network is **the same**, and it has more rights because it writes. Refusing the
strictly weaker capability while allowing the stronger one is inconsistent.

The real distinction is not where I said it was. It is **whose executable this
is**. `#416` grants the exception based on two trust signals:
`trusted_release` or `explicit_unverified_provider`. `provider conformance`
had **neither**—the command accepts an arbitrary `--executable` and verifies
nothing. The refusal protected against the absence of a signal, not against
reading the target.

## Options

**Leave it as is.** Windows remains without conformance. Rejected: this blocks
provider development on the entire platform, while the protected property
already does not hold for the adjacent, more powerful operation.

**Allow it because it is read-only.** Rejected: then `target-status` and
`diff` silently receive the exception, along with everything that may ever be
read-only. The fact that a command writes nothing says nothing about whose code
is running.

**Give conformance the same trust signal.** Accepted.

## Decision

`provider conformance` receives `--unverified-provider`. On Windows it
provides the same reason, `explicit_unverified_provider`, that `#416` already
accepted for installation.

Of the two signals, conformance can establish only this one: the command does
not read a release manifest and accepts the path it is given.
`trusted_release` cannot honestly be reached here, and it should not pretend
otherwise.

What **does not** change:

- without the flag, refusal is exactly as before. The default has not weakened;
- outside Windows the flag does nothing: `windows_unisolated` refuses to be
  constructed on any other system, and `invocation_v3.invoke` independently
  rechecks the platform because the value may arrive there but may act only on
  the system that needs the exception;
- `target-status`, `diff`, protocol v2, and everything else still receive no
  exception. The scope expands **by one command under the named signal**; it is
  not removed;
- `provider network --json` on Windows remains `unavailable`.

## Consequences

- A provider author can check a build on Windows while declaring it unverified.
  This is the same statement already made during installation.
- The signal becomes uniform: the exception is granted based on trust in the
  executable, not on whether the command reads or writes. One rule replaces
  two similar ones.
- The Windows debt neither shrinks nor grows: the unisolated phase remains the
  deliberate debt of `#416`, removed by the same consumer-controlled launcher.
- The cost, stated directly: a provider that the operator identifies as
  unverified can access the network during conformance while holding the named
  `--target`. It could not do so before because it did not run.

## Amendment of 2026-08-26: a rule instead of a list

The record above says the scope expands "by one command", while `target status`,
`target diff`, and protocol v2 do not receive the exception. The first claim
became stale on the same day, and replacing it with another list would be
wrong: a list that grows by commit is exactly what drifts.

**Rule.** The exception is granted to any command that launches a provider
named by the operator, and only under one of the two trust signals from `#416`.
Whether the command reads or writes is not part of the rule: that was the
incorrect signal rejected by the main record.

`target status` and `target diff` receive the same flag under the same
signal. They accept an arbitrary `--provider`, like conformance, and did not
run at all on Windows—the same platform gap closed above.

The argument is worth stating because it is not obvious: these commands inspect
a **live** target rather than a disposable one. But an unisolated phase on
Windows is already permitted for installation, which **modifies** that same
live target. The risk is accepted for a strictly more dangerous case, so
refusing the less dangerous one under the same signal is inconsistent—the
argument with which this record begins.

Protocol v2 does not and cannot receive the exception:
`invocation_v2.invoke` accepts no permission at all, so refusal remains a
consequence of construction rather than intent. This is the only part of the
list worth preserving, and it is preserved by making it unnecessary to
remember.

## Amendment of 2026-08-26: the exception belongs to platforms without a launcher, not to Windows

Both versions above say "Windows", and that proved to be a name rather than a
decision. `#416` described Windows because that is where the problem was
encountered; the check was written as `os_name != "windows"` and stopped
there.

Measured by running on three systems:

```text
Linux    launcher=yes   enforced      exception refused      (correct)
Darwin   launcher=none  unavailable   exception refused      (gap)
Windows  launcher=none  unavailable   exception available
```

**No provider v3 operation ran on macOS.** `discover_bubblewrap` returns
"unavailable" on everything other than Linux, while the exception refused to
be constructed on everything other than Windows. Meanwhile, `attested_bind`
knows the targets `macos/x86_64` and `macos/arm64`, providers declare
`supported_os: ["linux", "macos"]`, and the gate matrix runs `macos-latest`.
In other words, we download and attest a provider that we cannot execute.

No document excluded macOS. This was a consequence of the name.

**Rule.** The exception belongs to a system that **has no launcher with which
the ordinary CLI can deny network access**—the closed
`UNISOLATED_PLATFORMS` set. Linux is intentionally absent: missing `bwrap`
there is a missing dependency, not a missing system capability, and bypassing
an existing capability is not the same as conceding a nonexistent one.

Names stop naming Windows: `unisolated_local_phase`, `UNISOLATED_REASONS`,
`UNISOLATED_PLATFORMS`. The trust signals did not change—there are still two.

The debt did not grow: it existed for Windows and turned out to have existed
for macOS all along, only as complete refusal rather than an explicit
concession. The same consumer-controlled launcher will remove it; for macOS,
the candidate is `sandbox-exec`, and until something proves it **on the
platform itself**, it must not be written: an unverified launcher is a green
guard over nothing.

## Review conditions

- The appearance of a launcher that denies network access on Windows without
  system preparation makes this entire record and `#416` unnecessary at once.
  **One alleged obstacle has been measured and was not an obstacle.** `#416`
  recorded that an arbitrary target requires DACL traversal and therefore
  preparation of its parent or disk root. A run on `windows-latest`
  (`NDDev-OpenNetwork/claude-setup-system`, run 33302576898) showed that an
  AppContainer read a target carrying **only its own ACE** while the parent's
  DACL remained untouched—bypass traverse is granted broadly by default. The
  probe enumerated the parent's ACEs for this SID and printed none, proving
  that the control ran rather than being assumed. This does not remove the
  debt: the launcher must still be built and proven on the platform itself. It
  removes the recorded reason it was considered impossible to build.
- If any command receives the exception without one of the two trust signals,
  the rule's uniformity is broken and must be restored here, not in the caller.
