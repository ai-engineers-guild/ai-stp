---
description: "Decision to divide context among developer, device, and project passports."
last_verified: "2026-08-04"
---

# ADR-0025: Three context owners—developer, device, and project

Status: accepted.

## Context

`SPEC-003` required the developer passport to store both personal preferences and observed machine facts: the operating system, architecture, installed harnesses, and tool versions. At the same time, a device existed only as an identifier with a key.

A user has more than one device, and their environments can legitimately differ. While machine facts live in the developer passport, every rescan on another machine overwrites observations from the other device or creates a revision conflict for no reason. Cloud synchronization is forced to merge incomparable environments, selection input becomes ambiguous, and device pages on the web have no canonical source of environment data.

## Options

1. Retain a single developer passport. This requires no changes, but two devices are guaranteed to conflict over machine facts, and stable user preferences suffer from unrelated noise.
2. Maintain a separate copy of the developer passport on each device. This eliminates the conflict but splits personal preferences and decision history—the very things that must be shared.
3. Divide context among three passports with non-overlapping ownership: developer, device, and project.

## Decision

Option 3 is accepted.

**There are three context owners, and their fields do not overlap.**

```text
DeveloperPassport
  role, typical tasks, preferences, permissions and autonomy,
  preferred languages and harnesses, history of accepted and rejected
  decisions, stable cross-device user decisions

DevicePassport
  device_id, operating system, architecture, installed harnesses
  and their versions, tool and adapter versions,
  capabilities and observed facts of this device's environment

ProjectPassport
  project identity, stack and versions, commands, agent-facing surfaces,
  requirements, selected harness, and active setup
```

Observed operating system, architecture, installed harness and tool versions, and local capabilities are not part of the developer passport. Languages and harnesses remain in it only as preferences, not as installation facts.

**DevicePassport is private, revisioned, and owned by the device.** It maintains revisions under the common passport envelope. When synchronization is enabled, the server stores the permitted summary for each device separately; device passports are never merged into one cross-device environment.

**DeveloperPassport remains cross-device.** It is synchronized and merged under the existing revision model because, after the separation, it contains only facts shared across all of the user's devices.

**ProjectPassport remains local by default.** Only an explicitly permitted summary is sent to the cloud, as before.

**Selection input is assembled from four sources:** the developer passport, current-device passport, current-project passport, and selected harness—plus registry candidates. Sensitive absolute paths remain in local detector state and are not synchronized as profile data.

## Consequences

- the passport envelope gains a fifth `device` kind with revisions;
- `SPEC-002` gains requirements for device-passport ownership, revisions, privacy, and summary; `SPEC-003` no longer requires machine facts in the developer passport;
- `SPEC-009` establishes that device passports are synchronized separately and not merged; `SPEC-014` directs detector output into the device passport;
- device pages on the web display the permitted environment summary under `SPEC-010`; the public profile remains a separate object;
- the closed list of fields and summary belongs to `docs/contracts/device-passport.md`;
- the domain model gains `DevicePassport` and its revision as separate entities.

## Reconsideration conditions

The decision shall be reconsidered if a proven need emerges to merge environment facts across devices, or if user preferences begin systematically diverging between devices and require their own per-device model.
