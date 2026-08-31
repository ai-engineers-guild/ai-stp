---
description: "Runbook: uninstall purge."
last_verified: "2026-08-03"
---

# Uninstall and full purge

A regular uninstall shows the application-owned executable and tooling paths, removes the CLI, providers, toolchain, Skill projections, and credentials, preserves the registry, passports, artifacts, targets, and backups, and provides the reinstall command.

A full purge uses a separate plan, lists user data, clarifies local and cloud scope, deletes only exact owned paths, and verifies their absence and the log.

Targets and backups are purged only by a separate command.
