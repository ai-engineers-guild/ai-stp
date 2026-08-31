---
description: "Runbook: bootstrap."
last_verified: "2026-08-03"
---

# Initial installation

## Preliminary check

1. Record the system, architecture, user, home directories according to OS rules, and existing installations.
2. Check the availability of the published `uv` command, free space, network, and organizational restrictions.
3. Perform read-only discovery and save the diagnostic report.

## Plan

1. Build a plan for directories, the CLI, providers, the toolset, the control skill, and possible user actions.
2. Show every path to be created, source, and artifact hash.
3. If a system action is required, stop with `needs_user_action`; the agent does not receive the password.

## Application

1. Install the CLI in the user environment.
2. Create data, state, and cache directories with restrictive permissions.
3. Install verified provider releases and the full `mvp-full` profile toolset in new versioned directories.
4. Install the native projection of the control skill outside the replaceable setup.
5. Create a device identifier and key; login remains optional for local mode.

## Verification

1. Run diagnostics for the CLI, each installed provider, and each tool adapter.
2. Have the agent assemble a developer passport from discovered facts, or import an existing one.
3. Disconnect the network and confirm that the declared offline operations under `docs/contracts/offline-capability.md` continue to work.
4. Build a regular uninstall plan and verify that user data and targets are not included.

## Partial result

If a failure occurs after a write, do not blindly rerun the installation. Use the operation log, the last confirmed state, and the recovery action. An inactive incomplete directory is deleted only after verifying that the current pointer does not reference it.
