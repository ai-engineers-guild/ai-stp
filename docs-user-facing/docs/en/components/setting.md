---
title: "setting"
description: "Setting components: parameters, modes and preferences, without secrets."
---

# `setting`

A `setting` is the configuration part of a setup: parameters, modes, feature
flags, preferences, thresholds and other values the harness or the provider
knows how to apply.

A setting must not hold secrets. If a value is a token, a password, a private
key or a credential, it goes through a supported secret store, not through a
component's passport.

## What may be stored

| May be | May not be |
| --- | --- |
| an execution mode | an API token |
| the interface language | a password |
| a policy flag | a private key |
| a limit or a threshold | the contents of `.env` |
| a path inside the target, if it is not secret | an OAuth refresh token |

## Why setting is a kind of its own

Without a kind of its own, parameters scatter across instructions, hooks and
commands, and then nobody can tell what actually changed the behaviour. A
setting makes configuration visible and comparable.

??? example "An example"
    "Turn on strict checking before installing" is better as a `setting`, if
    the provider or the CLI reads that value. "The agent should explain the
    plan to the user" is better left in an `instruction`.

## How `ai_stp` applies a setting

1. The passport describes the name, the type, the allowed values and
   compatibility.
2. The compiler checks for conflicts with other components of the setup.
3. The provider shows the configuration diff.
4. After confirmation, the setting is written to the harness's native surface.

!!! warning "The common mistake"
    Do not use a setting as a convenient place for everything. If a value
    starts an action, it is probably a `command` or a `hook`. If it explains a
    process, it is probably an `instruction` or a `skill`.
