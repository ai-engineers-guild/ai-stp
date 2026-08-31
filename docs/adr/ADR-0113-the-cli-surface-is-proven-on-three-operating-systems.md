---
description: "Decision to prove the CLI surface on three operating systems and remove the Windows prohibition from passport vocabulary while retaining provider evidence."
last_verified: "2026-08-21"
---

# ADR-0113: The CLI surface is proven on three operating systems

Status: accepted. Clarifies `ADR-0062` without revoking its provider half.
Clarified by `ADR-0116` regarding which jobs run on which operating systems and
how many run concurrently.

## Context

`ADR-0062` described a state in which no macOS runner existed: "the owned macOS
runner is not active." Therefore macOS was called `not_verified`, while
`supported_os` in `SetupVersionPassport` was the closed vocabulary
`linux | macos`—Windows could not even be named.

Both facts changed, in different ways.

The public tree runs a three-operating-system matrix on standard GitHub runners
for every push. The matrix is not decorative: it found two real defects that a
Linux run could not see—a machine-output crash on a code page unable to encode
UTF-8, and a call to the system credential store on a headless machine that
never returned. Both are fixed and covered by tests.

Meanwhile, the Windows prohibition in the vocabulary did not do what was
expected. It did not prevent installing a setup on Windows—it prevented a
setup from **saying** that it supported Windows. Installation refusal already
exists in the right place: `install` compares this machine's operating system
with `supported_os` declared by provider capabilities and refuses there,
naming the provider as the reason.

## Decision

The CLI surface is considered proven on Linux, macOS, and Windows: discovery,
passports, selection, machine output, toolchain, and the process boundary run
in the public gate matrix on every push, and its green status is evidence, not
an assumption.

`supported_os` accepts `windows` alongside `linux` and `macos`. The vocabulary
stops judging in advance; the provider judges during installation according to
its declared capabilities.

Provider lifecycle evidence remains exactly what it was. The matrix runs
`tests/unit` and `tests/contract`: the CLI surface, not installation on a live
target through a signed provider release. Claiming from its green status that a
provider can write a macOS or Windows target would be precisely the substitution
that `ADR-0062` rejected in option 2: a fixture is not install evidence.

The following from `ADR-0062` remains unchanged: mandatory release records
record the release platform; adding an operating system to the **provider**
support matrix requires separate evidence rather than rewriting a past result;
and absence of network enforcement on non-Linux systems fails closed for an
action requiring `network_requirement=none`.

## Consequences

A Windows user no longer encounters a type refusal. If refused, the user
encounters a provider that says so itself and names itself as the reason. These
are different messages, and the latter can be fixed without changing the model.

CI must remain three-platform: removing a matrix leg returns it to
`not_verified`, but silently, and a silent regression here would cost exactly
the two defects for which the matrix was introduced.

## Reconsideration conditions

Reconsider if provider evidence appears for macOS or Windows—in which case the
provider support matrix also changes as a separate decision—or if the matrix
ceases to run on every push.
