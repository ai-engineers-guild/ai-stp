---
description: "Device passport fields, privacy, and the permitted summary for the server and web."
last_verified: "2026-08-04"
---

# Device passport

The requirements owner is `SPEC-002`; the context-separation decision belongs to `ADR-0025`. This document defines the machine boundary: which fields belong to the device passport, which of them leave the device, and in what form.

A device passport is a mutable, revisioned passport of kind `device` under `passport-envelope.md`. It describes the environment of one CLI installation and belongs to that device. Its facts follow the common origin and confirmation axes defined by `ADR-0021`.

## Ownership separation

| Fact | Owner |
|---|---|
| Role, typical tasks, preferences, autonomy | `DeveloperPassport` |
| Preferred languages and harnesses, decision history | `DeveloperPassport` |
| Operating system and architecture | `DevicePassport` |
| Installed harnesses and their exact versions | `DevicePassport` |
| Toolset and adapter versions | `DevicePassport` |
| Environment capabilities and observed facts | `DevicePassport` |
| Project stack, versions, commands, and requirements | `ProjectPassport` |
| Selected harness and active project setup | `ProjectPassport` |

A field covered by two rows in the table is a model error: every fact has exactly one owner. An observed installation fact is never written to the developer passport, even as a "default preference": a preference is declared by the user, not silently inferred from the environment.

## Fields

The device passport contains:

- `device_id` — the device identifier from `SPEC-002`;
- the user-defined display name of the device;
- the operating system and architecture;
- discovered harnesses with exact versions and states under `SPEC-014`;
- versions of installed `mvp-full` profile tools and adapters;
- environment capabilities: available runtimes and their versions;
- observed environment facts with origin and confirmation.

Observation-source paths are stored in the detector's local state. Absolute paths to user directories are not included in synchronized device-passport revisions.

## Privacy and synchronization

The device passport is private and belongs to the device. When synchronization is enabled, the server stores a separate permitted summary for each device; full device passports are not merged, and no cross-device "shared environment" exists.

The permitted device summary has a closed field set:

- device display name;
- operating system and architecture;
- list of discovered harnesses with versions;
- toolset profile version;
- time of the summary's last update.

Secret values, environment-variable values, and absolute paths are not included in the summary. Device pages on the web show only this summary; the public profile remains a separate object under `ADR-0023` and receives no device data.

## Use in selection

Selection input is assembled from the developer passport, the current device passport, the current project passport, and the selected harness. Selection requirements belong to `SPEC-006`; this contract only establishes that environment facts come from the device passport, not the developer passport.

## Device identity and device passport

These are different objects and must not be confused. Identity consists of `device_id`, an Ed25519 key pair, and revocation state: it is created on the first CLI launch, offline, before an account exists, and its machine form is published as `cli-device-identity`. The device passport describes the environment and appears with the local registry.

The private key is stored under `ADR-0058`: in the system secret store when the machine actually has a trusted backend, and in an owner-only file otherwise. The tier used is included in the response and in the `doctor` check; there is no silent fallback. The public half is stored in an ordinary file because it must be displayed; no field in any repository model corresponds to the private half, so there is no mechanism to print it.

## Device revocation

Revoking a device stops acceptance of its synchronization events under `SPEC-002` and does not delete the local device passport: local reads remain available, while the server summary is marked revoked together with the device.

A local identity reset reuses neither the identifier nor the key under `SPEC-002` REQ-207 and records the retired identifier: a revoked device can be kept from reuse only by remembering it. The reset does not touch local data.
