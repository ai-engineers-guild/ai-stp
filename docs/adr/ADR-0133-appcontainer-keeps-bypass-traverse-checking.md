---
description: "Decision to build the Windows network-isolated launcher on AppContainer because measurement disproved the objection that parent DACLs must be modified."
last_verified: "2026-08-30"
---

# ADR-0133: AppContainer retains traverse-check bypass

Status: accepted. Resolves the part of the `ADR-0126` debt identified as `#51`.

## Context

On Linux, the provider's local phase runs through Bubblewrap, and `enforced` is
set only after a positive control. Windows has no isolation—a deliberate debt
under `ADR-0126`. `#51` requests a native launcher and names AppContainer as a
candidate with one objection:

> AppContainer blocks the network, but cannot reach an arbitrary target without
> modifying the DACLs of its parents.

The objection determines the architecture. If it is correct, the cost is one
ACE for every ancestor of the selected target, meaning permissions must be
changed in other directories up the tree. If it is incorrect, the cost is one
ACE on the target itself.

This is a claim about a token, not an argument, so it was measured.

**And it had already been measured.** The docstring of
`network_launcher.unisolated_local_phase` carries the result of run 33302576898
(`NDDev-OpenNetwork/claude-setup-system`): AppContainer read a target carrying
**only its own ACE**, with no ACE anywhere on a parent. That record states
directly that “one half of the original rationale was incorrect, and it was the
half that prevented anyone from looking.”

The measurement here was performed without looking at that docstring: `#51`
continued to carry the disproven objection, and the work proceeded from the
issue text rather than the code. Six runs were spent rediscovering a fact that
lay thirty lines from the edit. This is worth recording because the defense
against it is not diligence but habit: **before measuring a claim from an issue,
ask what the module says about it.**

What the measurements here add beyond that record is independent reproduction
on a different OS build and with a different probe—and the network half, which
is entirely absent there.

## Measurements

`release_scripts/windows_isolation_probe.py`, `windows-latest`
(Windows Server 2025), Python 3.14.7. The probe deliberately follows the Linux
form: loopback listeners, a positive control from the parent, then the same
connection from inside—`#51` requires proof by **the same class** of probe.

| Question | Answer |
|---|---|
| `CreateAppContainerProfile` | `0x0`, Package SID issued |
| `GetAppContainerFolderPath` | `0x0` |
| `CreateProcessW` + `PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES`, zero capabilities | process created |
| TCP to the parent's loopback, IPv4 and IPv6 | `denied` |
| Grandchild spawned inside | `denied` — restriction is inherited |
| UDP datagram sent from inside | **did not arrive** at the parent's socket |
| Directory with an ACE for the Package SID, **parents without permissions** | **read** |
| Directory without any ACE | `PermissionError`, winerror 5 |

The last two rows answer `#51`: traverse-check bypass
(`SeChangeNotifyPrivilege`, granted to Everyone by default) survives in the
AppContainer token, so the full path reaches the leaf without permissions on
its ancestors. **The objection is incorrect**—and was disproved earlier; here
it was merely reproduced independently.

The four network rows are new. The earlier record measured target reachability
and said nothing about blocking the network; without these rows, `enforced` on
Windows would have no proof of its class.

## Decision

Build the launcher on AppContainer without capabilities. Permissions are
granted in exactly two places: the selected target and the runtime directory.
Ancestors, the host firewall, and global ACLs are not touched.

WFP enforces the network block through the `FWPM_CONDITION_ALE_PACKAGE_ID`
condition—that is, by mechanism rather than convention—which is what `#51`
requires.

## What the measurement does not say

Do not extend these results to claims broader than what was measured.

- **Administrator privileges.** The runner is elevated (`is_admin: true`), so
  whether an ordinary user can create a profile was **not measured**. The
  documentation says elevation is unnecessary; until independently verified,
  this remains a borrowed claim, and the launcher must fail closed if profile
  creation fails.
- **Timeout rather than refusal.** On Linux, the block appears immediately as
  `ECONNREFUSED`; here both TCP and UDP time out because AppContainer blocks at
  the receive layer. A timeout is weaker than a refusal: it is also consistent
  with a slow listener. The positive control is precisely what turns it into
  evidence, so `enforced` is not set if the control fails.
- **One OS version.** Measured on Windows Server 2025. Other builds were not
  tested.

## How this was measured, and why that is part of the decision

Of six runs, **four measured the probe rather than the platform**, and each
looked like a result:

1. the response was collected in a file the container could not create—silence
   with two explanations and no way to distinguish them;
2. the same through the container's own folder—silence again;
3. the negative control was contaminated: the root received an ACE with
   `(OI)(CI)`, which propagated to every descendant, and the “unauthorized”
   directory was read with the rest—a control incapable of failing;
4. UDP was judged by the return value of `sendto`, which succeeds even for a
   dropped datagram, making it a claim about the call rather than the network.

The fifth predates all of them: work began from the text of `#51`, not from the
code that had already disproved it. The stale rationale in the issue continues
to argue and consumes other people's time—six runs here.

The other four share one general form: a claim that nothing can contradict is
indistinguishable from one that has been confirmed. Hence the rule this record
leaves behind: **the result-collection channel must not depend on what is being
measured**—the response arrives through an inherited descriptor opened before
launch—and **every negative result must name a change that would make it
positive**.

## Consequences

- `#51` is implementable; `ADR-0126` ceases to be permanent debt.
- `provider network --json` will be able to return `enforced` on Windows, but
  only after a positive control, as on Linux.
- A new obligation appears: remove the ACE and profile after success, failure,
  timeout, and crash.
- The probe remains in `release_scripts/`; its workflow does not. `.github` is
  constrained by the manifest (`ADR-0108`): public workflows come from the
  overlay, so a one-off dispatch-only job broke the circular sync check. This is
  architecturally preferable: launcher checks should be a permanent job in the
  existing Windows `check` matrix, not a separate workflow nobody runs. The
  probe can be run manually on Windows or through a temporary job.
- This record is what remains of the probe if it is never run again.
